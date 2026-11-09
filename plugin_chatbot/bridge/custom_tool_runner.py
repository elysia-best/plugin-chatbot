"""Standalone runner for administrator-defined custom tools.

The bot launches this file as a child process::

    python -I -X utf8 <package>/bridge/custom_tool_runner.py

It must stay self-contained: ``-I`` implies ``-P``, so neither the script
directory nor ``PYTHONPATH`` ends up on ``sys.path`` and the bot package is
not importable from here on purpose.

Protocol: one JSON request on stdin, one JSON result on stdout.
The tool script itself never touches stdout -- anything it prints is
redirected to stderr so the JSON channel stays intact.
"""

from __future__ import annotations

import contextlib
import inspect
import json
import locale
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, NoReturn, cast

MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_RESULT_CHARS = 20_000
MAX_TRACEBACK_CHARS = 4_000
MAX_STREAM_BYTES = 65_536
MAX_LOGS = 200
DEFAULT_TIMEOUT = 30.0
DEFAULT_COMMANDS = 50
MIN_SLICE_SECONDS = 0.1

_OUT = sys.stdout.buffer
_ACTIVE: list[subprocess.Popen[bytes]] = []


class _RequestError(Exception):
    """Malformed or oversized request payload."""


class _ToolFailure(Exception):  # noqa: N818
    """A deliberate failure produced by the runner, not by user code."""

    def __init__(self, error: str, tb: str) -> None:
        super().__init__(error)
        self.error = error
        self.tb = tb


def _emit(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    _OUT.write(text.encode("utf-8", "replace"))
    _OUT.flush()


def _as_float(value: object, fallback: float) -> float:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    return result if result > 0 else fallback


def _as_int(value: object, fallback: int) -> int:
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    return result if result > 0 else fallback


def _read_request() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if not raw:
        raise _RequestError("empty request")  # noqa: TRY003
    if len(raw) > MAX_INPUT_BYTES:
        raise _RequestError("request too large")  # noqa: TRY003
    data = json.loads(raw.decode("utf-8", "replace"))
    if not isinstance(data, dict):
        raise _RequestError("request must be a JSON object")  # noqa: TRY003
    return data


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    """Kill a command together with everything it spawned."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()


def _decode(data: bytes) -> tuple[str, bool]:
    truncated = len(data) > MAX_STREAM_BYTES
    if truncated:
        data = data[:MAX_STREAM_BYTES]
    try:
        return data.decode("utf-8"), truncated
    except UnicodeDecodeError:
        encoding = locale.getpreferredencoding(do_setlocale=False) or "utf-8"
        return data.decode(encoding, errors="replace"), truncated


def _normalize_result(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(value)


class _Budget:
    """Shared wall-clock and command-count budget for one tool call."""

    def __init__(self, seconds: float, commands: int) -> None:
        self.deadline = time.monotonic() + max(0.5, seconds)
        self.limit = max(1, commands)
        self.used = 0

    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def take(self) -> None:
        if self.used >= self.limit:
            raise CommandBudgetError(self.limit)
        self.used += 1


class CommandBudgetError(RuntimeError):
    """Raised when a script tries to run more commands than allowed."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"命令数量超过上限（{limit}）")
        self.limit = limit


def _fail(error: str, tb: str = "") -> NoReturn:
    raise _ToolFailure(error, tb)


def main() -> int:  # noqa: C901, PLR0915
    try:
        request = _read_request()
    except (OSError, _RequestError, json.JSONDecodeError) as exc:
        _emit(
            {
                "ok": False,
                "error": f"请求无效：{exc}",
                "traceback": "",
                "logs": [],
                "commands": 0,
                "truncated": False,
            }
        )
        return 2

    source = str(request.get("source") or "")
    name = str(request.get("name") or "custom_tool")
    raw_args = request.get("args")
    args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
    raw_context = request.get("context")
    context: dict[str, Any] = raw_context if isinstance(raw_context, dict) else {}
    workspace = str(context.get("workspace") or Path.cwd())
    timeout = _as_float(context.get("timeout"), DEFAULT_TIMEOUT)
    max_chars = _as_int(context.get("max_output_chars"), MAX_RESULT_CHARS)
    budget = _Budget(timeout, _as_int(context.get("max_commands"), DEFAULT_COMMANDS))
    logs: list[str] = []

    def log(message: object) -> None:
        text = str(message)[:500]
        if len(logs) < MAX_LOGS:
            logs.append(text)
        sys.stderr.write(text + "\n")
        sys.stderr.flush()

    def run_cmd(
        command: str | list[str],
        cwd: str | None = None,
        timeout: float | None = None,
        input: str | None = None,  # noqa: A002
    ) -> dict[str, Any]:
        budget.take()
        left = budget.remaining()
        if left <= MIN_SLICE_SECONDS:
            raise TimeoutError("工具执行时间已用尽")
        limit = left if timeout is None else min(left, float(timeout))
        if limit <= MIN_SLICE_SECONDS:
            raise TimeoutError("剩余时间不足")
        shell = isinstance(command, str)
        kwargs: dict[str, Any] = {
            "cwd": cwd or workspace,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.PIPE if input is not None else subprocess.DEVNULL,
            "shell": shell,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        payload = input.encode("utf-8") if input is not None else None
        process = cast("subprocess.Popen[bytes]", subprocess.Popen(command, **kwargs))
        _ACTIVE.append(process)
        timed_out = False
        try:
            out, err = process.communicate(payload, timeout=limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(process)
            try:
                out, err = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                out, err = b"", b""
        finally:
            if process in _ACTIVE:
                _ACTIVE.remove(process)
        stdout, cut_out = _decode(out or b"")
        stderr, cut_err = _decode(err or b"")
        code = process.returncode
        return {
            "ok": code == 0 and not timed_out,
            "code": code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "truncated": cut_out or cut_err,
        }

    ctx = {
        "workspace": workspace,
        "name": name,
        "timeout": timeout,
        "commands": 0,
    }

    # Keep the JSON channel clean: everything the script prints goes to stderr.
    sys.stdout = sys.stderr

    try:
        code = compile(source, f"<custom_tool:{name}>", "exec")
        namespace: dict[str, Any] = {
            "__name__": "__custom_tool__",
            "run_cmd": run_cmd,
            "log": log,
            "workspace": workspace,
            "args": args,
            "ctx": ctx,
        }
        exec(code, namespace)
        handler = namespace.get("run")
        if not callable(handler):
            _fail("脚本必须定义 run(args, ctx) 函数")
        value = handler(args, ctx)
        if inspect.isawaitable(value):
            close = getattr(value, "close", None)
            if callable(close):
                close()
            _fail("run 必须是同步函数，不支持 async def")
        output = _normalize_result(value)
    except _ToolFailure as exc:
        _emit(
            {
                "ok": False,
                "error": exc.error,
                "traceback": exc.tb,
                "logs": logs,
                "commands": budget.used,
                "truncated": False,
            }
        )
        return 1
    except SyntaxError as exc:
        detail = f"语法错误（第 {exc.lineno} 行）：{exc.msg}"
        _emit(
            {
                "ok": False,
                "error": detail,
                "traceback": "",
                "logs": logs,
                "commands": budget.used,
                "truncated": False,
            }
        )
        return 1
    except BaseException as exc:  # noqa: BLE001
        tb = exc.__traceback__
        trimmed = tb.tb_next if tb is not None and tb.tb_next is not None else tb
        text = "".join(traceback.format_exception(type(exc), exc, trimmed))
        _emit(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:500],
                "traceback": text[-MAX_TRACEBACK_CHARS:],
                "logs": logs,
                "commands": budget.used,
                "truncated": False,
            }
        )
        return 1

    truncated = len(output) > max_chars
    if truncated:
        output = output[:max_chars]
    _emit(
        {
            "ok": True,
            "output": output,
            "logs": logs,
            "commands": budget.used,
            "truncated": truncated,
        }
    )
    return 0


def _install_signal_handlers() -> None:
    def _shutdown(signum: int, _frame: object) -> None:
        for process in _ACTIVE:
            _kill_tree(process)
        os._exit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(OSError, ValueError):
            signal.signal(sig, _shutdown)


if __name__ == "__main__":
    _install_signal_handlers()
    sys.exit(main())
