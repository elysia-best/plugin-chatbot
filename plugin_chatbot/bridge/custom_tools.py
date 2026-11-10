"""Administrator-defined tools: validation, storage and sandboxed execution.

Tools are created exclusively through the console API. Nothing here scans a
plugin directory: a script file that has no matching row in
``bridge-state.json`` is never loaded and gets pruned at startup.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent.tool import Tool, ToolContext

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

SCOPES: tuple[str, ...] = ("admin", "private", "all", "manual")
DEFAULT_SCOPE = "admin"
ALLOWED_GROUP_KEYS: tuple[str, ...] = ("platform", "bot_id", "group_id")
MAX_ALLOWED_GROUPS = 200
MAX_TOOLS = 40
MAX_SOURCE_CHARS = 32_768
MAX_SOURCE_LINES = 2_000
MAX_SCHEMA_CHARS = 16_384
MAX_SCHEMA_DEPTH = 8
MAX_DESCRIPTION_CHARS = 1_024
MIN_TIMEOUT = 1.0
MAX_TIMEOUT = 300.0
DEFAULT_TIMEOUT = 30.0
MAX_OUTPUT_CHARS = 20_000
MAX_STDOUT_BYTES = 1_048_576
MAX_STDERR_BYTES = 262_144
MAX_COMMANDS = 50
CHUNK_BYTES = 65_536
RUN_ARGS = 2
TIMEOUT_GRACE = 1.0
KILL_GRACE = 2.0

_NAME_RE = re.compile(r"^custom_[a-z0-9_]{1,49}$")
_ID_RE = re.compile(r"^[0-9a-f]{16}$")

_POSIX_ENV = frozenset(
    {"PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR", "USER", "SHELL"}
)
_WINDOWS_ENV = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "COMMONPROGRAMFILES",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "OS",
        "COMPUTERNAME",
        "USERNAME",
        "USERDOMAIN",
    }
)


class CustomToolError(ValueError):
    """Rejected tool definition; ``status`` is the HTTP code to answer with."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def source_digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _normalize_source(source: str) -> str:
    return source.replace("\r\n", "\n").replace("\r", "\n")


def _schema_depth(value: object, depth: int = 0) -> int:
    if depth > MAX_SCHEMA_DEPTH:
        return depth
    if isinstance(value, dict):
        return max(
            (_schema_depth(item, depth + 1) for item in value.values()),
            default=depth + 1,
        )
    if isinstance(value, list):
        return max(
            (_schema_depth(item, depth + 1) for item in value),
            default=depth + 1,
        )
    return depth


def _validate_schema(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        message = "input_schema 必须是 JSON 对象"
        raise CustomToolError(message)
    schema = dict(raw)
    if schema.get("type", "object") != "object":
        message = "input_schema.type 必须是 object"
        raise CustomToolError(message)
    schema["type"] = "object"
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        message = "input_schema.properties 必须是对象"
        raise CustomToolError(message)
    for key, value in properties.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            message = f"input_schema.properties.{key} 必须是对象"
            raise CustomToolError(message)
    schema["properties"] = properties
    required = schema.get("required") or []
    if not isinstance(required, list) or any(
        not isinstance(item, str) for item in required
    ):
        message = "input_schema.required 必须是字符串数组"
        raise CustomToolError(message)
    missing = [item for item in required if item not in properties]
    if missing:
        message = f"input_schema.required 引用了未声明的参数：{', '.join(missing)}"
        raise CustomToolError(message)
    schema["required"] = required
    if _schema_depth(schema) > MAX_SCHEMA_DEPTH:
        message = "input_schema 嵌套层级过深"
        raise CustomToolError(message)
    if len(json.dumps(schema, ensure_ascii=False)) > MAX_SCHEMA_CHARS:
        message = "input_schema 超过体积上限"
        raise CustomToolError(message)
    return schema


def _validate_source(raw: object) -> str:  # noqa: C901
    if not isinstance(raw, str) or not raw.strip():
        message = "脚本内容不能为空"
        raise CustomToolError(message)
    source = _normalize_source(raw)
    if len(source) > MAX_SOURCE_CHARS:
        message = f"脚本超过 {MAX_SOURCE_CHARS} 字符上限"
        raise CustomToolError(message)
    if source.count("\n") + 1 > MAX_SOURCE_LINES:
        message = f"脚本超过 {MAX_SOURCE_LINES} 行上限"
        raise CustomToolError(message)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        message = f"脚本语法错误（第 {exc.lineno} 行）：{exc.msg}"
        raise CustomToolError(message) from exc
    defined = False
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "run":
            continue
        if isinstance(node, ast.AsyncFunctionDef):
            message = "run 必须是同步函数（不支持 async def）"
            raise CustomToolError(message)
        defined = True
        count = len(node.args.posonlyargs) + len(node.args.args)
        if count < RUN_ARGS and node.args.vararg is None:
            message = "run 必须接收 args 与 ctx 两个参数"
            raise CustomToolError(message)
    if not defined:
        message = "脚本必须定义顶层函数 run(args, ctx)"
        raise CustomToolError(message)
    return source


def validate_definition(  # noqa: C901, PLR0912, PLR0915
    body: dict[str, Any],
    *,
    existing: list[dict[str, Any]],
    current_id: str = "",
) -> dict[str, Any]:
    """Validate one editor payload and return its normalized fields."""
    if not isinstance(body, dict):
        message = "请求体必须是 JSON 对象"
        raise CustomToolError(message)

    raw_name = body.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        message = "名称不能为空"
        raise CustomToolError(message)
    name = raw_name.strip().lower()
    if not name.startswith("custom_"):
        name = f"custom_{name}"
    if not _NAME_RE.fullmatch(name):
        message = "名称只允许小写字母、数字与下划线，总长度不超过 56 个字符"
        raise CustomToolError(message)

    for row in existing:
        if current_id and str(row.get("id")) == current_id:
            continue
        if str(row.get("name")) == name:
            message = f"工具名 {name} 已存在"
            raise CustomToolError(message, 409)

    description = body.get("description") or ""
    if not isinstance(description, str):
        message = "描述必须是文本"
        raise CustomToolError(message)
    description = description.strip()
    if not description:
        message = "描述不能为空，模型依赖它判断何时调用"
        raise CustomToolError(message)
    if len(description) > MAX_DESCRIPTION_CHARS:
        message = f"描述超过 {MAX_DESCRIPTION_CHARS} 字符上限"
        raise CustomToolError(message)

    try:
        timeout = float(body.get("timeout", DEFAULT_TIMEOUT))
    except (TypeError, ValueError) as exc:
        message = "超时必须是数字"
        raise CustomToolError(message) from exc
    if not math.isfinite(timeout) or not MIN_TIMEOUT <= timeout <= MAX_TIMEOUT:
        message = f"超时必须在 {MIN_TIMEOUT:g} 到 {MAX_TIMEOUT:g} 秒之间"
        raise CustomToolError(message)

    scope = body.get("scope") or DEFAULT_SCOPE
    if scope not in SCOPES:
        message = f"scope 必须是 {', '.join(SCOPES)} 之一"
        raise CustomToolError(message)
    allowed_groups = _normalize_allowed_groups(
        body.get("allowed_groups") if scope == "manual" else None
    )
    if scope == "manual" and not allowed_groups:
        message = "手动范围至少要指定一个群聊"
        raise CustomToolError(message)

    enabled = body.get("enabled", True)
    if not isinstance(enabled, bool):
        enabled = True

    if not current_id and len(existing) >= MAX_TOOLS:
        message = f"最多只能保存 {MAX_TOOLS} 个自定义工具"
        raise CustomToolError(message)

    raw_schema = body.get("input_schema")
    if raw_schema is None:
        raw_schema = {}
    return {
        "name": name,
        "description": description,
        "input_schema": _validate_schema(raw_schema),
        "source": _validate_source(body.get("source")),
        "scope": scope,
        "timeout": round(timeout, 3),
        "enabled": enabled,
        "allowed_groups": allowed_groups,
    }


def _as_number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return time.time()


def _row_allowed_groups(row: dict[str, Any]) -> list[dict[str, str]]:
    """Read a stored row's allowlist, coercing unusable values to ``[]``.

    Unlike :func:`_normalize_allowed_groups`, this never raises: a stored row
    with a corrupted ``allowed_groups`` field is repaired instead of rejected.
    """
    with contextlib.suppress(CustomToolError):
        return _normalize_allowed_groups(row.get("allowed_groups"))
    return []


def _normalize_allowed_groups(raw: object) -> list[dict[str, str]]:
    """Normalize a manual-scope allowlist into unique group triples.

    Args:
        raw: ``None`` or a list of mappings carrying ``platform``, ``bot_id``
            and ``group_id`` string fields. Entries missing any of the three
            non-empty fields are dropped.

    Returns:
        At most ``MAX_ALLOWED_GROUPS`` entries, each shaped as
        ``{"platform": str, "bot_id": str, "group_id": str}`` and deduplicated
        by the full triple in insertion order.

    Raises:
        CustomToolError: 当 ``raw`` 不是 None 也不是列表时。
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        message = "allowed_groups 必须是对象数组"
        raise CustomToolError(message)
    groups: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        triple = tuple(str(item.get(key) or "").strip() for key in ALLOWED_GROUP_KEYS)
        if not all(triple) or triple in seen:
            continue
        seen.add(triple)  # type: ignore[arg-type]
        groups.append(dict(zip(ALLOWED_GROUP_KEYS, triple, strict=True)))
        if len(groups) >= MAX_ALLOWED_GROUPS:
            break
    return groups


def normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Repair a stored row; return ``None`` when it is unusable."""
    tool_id = row.get("id")
    name = row.get("name")
    if not isinstance(tool_id, str) or not _ID_RE.fullmatch(tool_id):
        return None
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        return None
    scope = row.get("scope")
    if scope not in SCOPES:
        scope = DEFAULT_SCOPE
    timeout = _as_number(row.get("timeout", DEFAULT_TIMEOUT))
    timeout = min(max(timeout, MIN_TIMEOUT), MAX_TIMEOUT)
    schema = row.get("input_schema")
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}
    description = row.get("description")
    return {
        "id": tool_id,
        "name": name,
        "description": (description if isinstance(description, str) else "")[
            :MAX_DESCRIPTION_CHARS
        ],
        "input_schema": schema,
        "scope": scope,
        "timeout": timeout,
        "enabled": bool(row.get("enabled", True)),
        "allowed_groups": _row_allowed_groups(row),
        "source_sha256": str(row.get("source_sha256") or ""),
        "created_at": _as_number(row.get("created_at")),
        "updated_at": _as_number(row.get("updated_at")),
    }


class CustomToolStore:
    """File store for tool sources; only ids registered in state are valid."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, tool_id: str) -> Path:
        if not _ID_RE.fullmatch(tool_id):
            message = "无效的工具 ID"
            raise CustomToolError(message, 404)
        target = (self.root / f"{tool_id}.py").resolve()
        if target.parent != self.root:
            message = "无效的工具 ID"
            raise CustomToolError(message, 404)
        return target

    def read(self, tool_id: str) -> str:
        return self.path(tool_id).read_text(encoding="utf-8")

    def write(self, tool_id: str, source: str) -> str:
        target = self.path(tool_id)
        temp = target.with_name(f"{target.name}.tmp")
        temp.write_text(source, encoding="utf-8", newline="\n")
        temp.replace(target)
        return source_digest(source)

    def delete(self, tool_id: str) -> None:
        with contextlib.suppress(FileNotFoundError, OSError):
            self.path(tool_id).unlink()

    def prune(self, valid_ids: set[str]) -> int:
        """Delete script files that no state row refers to."""
        removed = 0
        for path in self.root.glob("*.py"):
            if path.stem in valid_ids:
                continue
            with contextlib.suppress(OSError):
                path.unlink()
                removed += 1
        return removed


def _child_env() -> dict[str, str]:
    """Whitelisted environment for tool scripts and the commands they run."""
    keep = _WINDOWS_ENV if os.name == "nt" else _POSIX_ENV
    env = {key: value for key, value in os.environ.items() if key.upper() in keep}
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _taskkill(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True,
        check=False,
    )


def _signal_group(process: asyncio.subprocess.Process, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(process.pid, sig)


async def _terminate(
    process: asyncio.subprocess.Process, grace: float = KILL_GRACE
) -> None:
    if process.returncode is not None:
        return
    if os.name == "nt":
        await asyncio.to_thread(_taskkill, process.pid)
    else:
        _signal_group(process, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), grace)
        except asyncio.TimeoutError:
            _signal_group(process, signal.SIGKILL)
        else:
            return
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(process.wait(), grace)


async def _read_capped(
    stream: asyncio.StreamReader | None, cap: int
) -> tuple[bytes, bool]:
    if stream is None:
        return b"", False
    buffer = bytearray()
    truncated = False
    while True:
        chunk = await stream.read(CHUNK_BYTES)
        if not chunk:
            break
        room = cap - len(buffer)
        if room > 0:
            buffer.extend(chunk[:room])
        if len(chunk) > room:
            truncated = True
    return bytes(buffer), truncated


def _envelope(  # noqa: PLR0913
    started: float,
    *,
    ok: bool,
    output: str = "",
    error: str = "",
    traceback_text: str = "",
    logs: list[str] | None = None,
    commands: int = 0,
    truncated: bool = False,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "output": output,
        "error": error,
        "traceback": traceback_text,
        "logs": logs or [],
        "commands": commands,
        "truncated": truncated,
        "elapsed_ms": int((time.monotonic() - started) * 1_000),
    }


def _subprocess_options(workspace: Path) -> dict[str, Any]:
    options: dict[str, Any] = {
        "stdin": asyncio.subprocess.PIPE,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "cwd": str(workspace),
        "env": _child_env(),
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    return options


async def execute(  # noqa: PLR0913
    *,
    runner: Path,
    workspace: Path,
    source: str,
    name: str,
    args: dict[str, Any],
    timeout: float,
    max_output_chars: int = MAX_OUTPUT_CHARS,
) -> dict[str, Any]:
    """Run one tool script in an isolated child process."""
    started = time.monotonic()
    payload = {
        "source": source,
        "name": name,
        "args": args,
        "context": {
            "workspace": str(workspace),
            "timeout": timeout,
            "max_output_chars": max_output_chars,
            "max_commands": MAX_COMMANDS,
        },
    }
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-X",
            "utf8",
            str(runner),
            **_subprocess_options(workspace),
        )
    except (OSError, ValueError) as exc:
        message = f"无法启动脚本进程：{exc}"
        return _envelope(started, ok=False, error=message)

    if process.stdin is not None:
        try:
            process.stdin.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            await asyncio.wait_for(process.stdin.drain(), timeout=5.0)
        except (BrokenPipeError, ConnectionResetError, asyncio.TimeoutError):
            pass
        finally:
            with contextlib.suppress(OSError, RuntimeError):
                process.stdin.close()

    try:
        (stdout, cut_out), (stderr, cut_err) = await asyncio.wait_for(
            asyncio.gather(
                _read_capped(process.stdout, MAX_STDOUT_BYTES),
                _read_capped(process.stderr, MAX_STDERR_BYTES),
            ),
            timeout=timeout + TIMEOUT_GRACE,
        )
    except asyncio.TimeoutError:
        await _terminate(process)
        message = f"执行超时（{timeout:g} 秒）"
        return _envelope(started, ok=False, error=message)
    except (OSError, ValueError) as exc:
        await _terminate(process)
        message = f"读取脚本输出失败：{exc}"
        return _envelope(started, ok=False, error=message)
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(process.wait(), TIMEOUT_GRACE)

    return _parse_response(
        stdout,
        stderr,
        started=started,
        max_chars=max_output_chars,
        cut_out=cut_out,
        cut_err=cut_err,
    )


def _parse_response(  # noqa: PLR0913
    stdout: bytes,
    stderr: bytes,
    *,
    started: float,
    max_chars: int,
    cut_out: bool,
    cut_err: bool,
) -> dict[str, Any]:
    text = stdout.decode("utf-8", "replace").strip()
    stderr_text = stderr.decode("utf-8", "replace").strip()
    if not text:
        detail = stderr_text[-MAX_OUTPUT_CHARS:] or "脚本进程没有返回结果"
        return _envelope(
            started,
            ok=False,
            error="脚本进程异常退出",
            traceback_text=detail,
        )
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _envelope(
            started,
            ok=False,
            error="脚本进程返回了非 JSON 内容",
            traceback_text=text[-MAX_OUTPUT_CHARS:],
        )
    if not isinstance(data, dict):
        return _envelope(started, ok=False, error="脚本进程返回格式无效")

    logs = [str(item) for item in data.get("logs") or [] if isinstance(item, str)]
    commands = data.get("commands")
    if not isinstance(commands, int):
        commands = 0
    if not data.get("ok"):
        error = str(data.get("error") or "脚本执行失败")
        trace = str(data.get("traceback") or "")
        return _envelope(
            started,
            ok=False,
            error=error,
            traceback_text=trace,
            logs=logs,
            commands=commands,
        )
    output = str(data.get("output") or "")
    if len(output) > max_chars:
        output = output[:max_chars]
        cut_out = True
    return _envelope(
        started,
        ok=True,
        output=output,
        logs=logs,
        commands=commands,
        truncated=bool(data.get("truncated")) or cut_out or cut_err,
    )


def build_tool(
    row: dict[str, Any],
    invoke: Callable[[dict[str, Any], ToolContext], Awaitable[dict[str, Any]]],
) -> Tool:
    """Wrap one stored script into the agent's ``Tool`` interface.

    ``invoke`` owns the subprocess call so the caller can apply concurrency
    limits and auditing; it returns the envelope produced by :func:`execute`.
    """
    name = str(row["name"])
    schema = row.get("input_schema")
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}

    async def handler(args: dict[str, Any], ctx: ToolContext) -> str:
        result = await invoke(args, ctx)
        if not result.get("ok"):
            detail = str(result.get("error") or "执行失败")
            trace = str(result.get("traceback") or "").strip()
            message = f"Error: {name} 执行失败：{detail}"
            return f"{message}\n{trace}" if trace else message
        output = str(result.get("output") or "").strip()
        return output or "(no output)"

    return Tool(
        name=name,
        description=str(row.get("description") or name),
        input_schema=schema,
        handler=handler,
        category="exec",
        path_field="",
        command_field="",
    )
