"""内置工具集合：文件 + Shell + 网络。

提供 Bash / Read / Write / Edit / Glob / Grep / WebFetch / WebSearch。
所有 handler 为异步，路径基于 workspace 解析。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from agent.tool import Tool, ToolContext

# 用 openai 依赖的 httpx2；若不可用则回退 httpx
try:
    import httpx2 as httpx  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    import httpx  # type: ignore[import-untyped]


def _resolve(ctx: ToolContext, p: str) -> Path:
    """把相对路径解析到 workspace 下；绝对路径原样返回。"""
    path = Path(p).expanduser()
    if path.is_absolute():
        return path
    return (Path(ctx.workspace) / path).resolve()


def _safe_relative(ctx: ToolContext, p: str) -> str:
    try:
        return str(_resolve(ctx, p).relative_to(Path(ctx.workspace).resolve()))
    except ValueError:
        return str(_resolve(ctx, p))


async def _read(args: dict[str, Any], ctx: ToolContext) -> str:
    path = _resolve(ctx, str(args.get("file_path", "")))
    limit = int(args.get("limit", 0)) or None
    offset = int(args.get("offset", 1)) or 1
    return await asyncio.to_thread(_read_sync, path, offset, limit)


def _read_sync(path: Path, offset: int, limit: int | None) -> str:
    if not path.exists():
        return f"Error: file not found: {path}"
    if path.is_dir():
        return f"Error: path is a directory: {path}"
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return f"Error: binary file (size={len(data)} bytes), use Bash to inspect."
    lines = text.splitlines(keepends=True)
    lines = lines[offset - 1 : offset - 1 + limit] if limit else lines[offset - 1 :]
    numbered = [f"{i:>6}\t{ln}" for i, ln in enumerate(lines, start=offset)]
    return "".join(numbered) if numbered else "(empty)"


async def _write(args: dict[str, Any], ctx: ToolContext) -> str:
    path = _resolve(ctx, str(args.get("file_path", "")))
    content = str(args.get("content", ""))
    return await asyncio.to_thread(_write_sync, path, content)


def _write_sync(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {path}"


async def _edit(args: dict[str, Any], ctx: ToolContext) -> str:
    path = _resolve(ctx, str(args.get("file_path", "")))
    old = str(args.get("old_string", ""))
    new = str(args.get("new_string", ""))
    return await asyncio.to_thread(_edit_sync, path, old, new)


def _edit_sync(path: Path, old: str, new: str) -> str:
    if not path.exists():
        return f"Error: file not found: {path}"
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return f"Error: old_string not found in {path}"
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    return f"Edited {path}"


async def _glob(args: dict[str, Any], ctx: ToolContext) -> str:
    pattern = str(args.get("pattern", ""))
    if not pattern:
        return "Error: pattern is required"
    base = Path(ctx.workspace)
    results = await asyncio.to_thread(_glob_sync, base, pattern)
    return "\n".join(sorted(results)) if results else "(no matches)"


def _glob_sync(base: Path, pattern: str) -> list[str]:
    return [
        str(p.relative_to(base)).replace(os.sep, "/")
        for p in base.glob(pattern)
        if p.is_file() or p.is_dir()
    ]


async def _grep(args: dict[str, Any], ctx: ToolContext) -> str:
    pattern = str(args.get("pattern", ""))
    path_s = str(args.get("path", "."))
    base = _resolve(ctx, path_s)
    if not pattern:
        return "Error: pattern is required"
    # 优先用 rg
    try:
        proc = await asyncio.create_subprocess_exec(
            "rg",
            "--line-number",
            "--color",
            "never",
            pattern,
            str(base),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode not in (0, 1):
            return f"Error: rg failed: {err.decode(errors='replace')}"
        return out.decode(errors="replace") or "(no matches)"
    except FileNotFoundError:
        pass
    # 回退：python 扫描（在线程中执行，避免阻塞事件循环）
    hits = await asyncio.to_thread(_grep_sync, base, pattern)
    return "\n".join(hits) if hits else "(no matches)"


def _grep_sync(base: Path, pattern: str) -> list[str]:
    hits: list[str] = []
    root = base if base.is_dir() else base.parent
    for p in root.rglob("*"):
        if p.is_file():
            try:
                for i, line in enumerate(
                    p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
                ):
                    if pattern in line:
                        hits.append(f"{p}:{i}:{line}")
            except OSError:
                continue
    return hits


async def _bash(args: dict[str, Any], ctx: ToolContext) -> str:
    command = str(args.get("command", ""))
    if not command:
        return "Error: command is empty"
    timeout = float(args.get("timeout", ctx.timeout))
    shell = args.get("shell")
    if shell is None:
        shell = "powershell" if os.name == "nt" else "bash"
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(Path(ctx.workspace)),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return f"Error: command timed out after {timeout}s"
        stdout = out.decode(errors="replace")
        stderr = err.decode(errors="replace")
        parts = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(f"[stderr]\n{stderr}")
        if proc.returncode != 0:
            parts.append(f"[exit code {proc.returncode}]")
        return "\n".join(parts) if parts else "(no output)"
    except Exception as e:  # noqa: BLE001
        return f"Error: {e}"


async def _web_fetch(args: dict[str, Any], _ctx: ToolContext) -> str:
    url = str(args.get("url", ""))
    if not url:
        return "Error: url is required"
    max_bytes = int(args.get("max_bytes", 2_000_000))
    timeout = float(args.get("timeout", 30.0))
    try:
        async with (
            httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client,
            client.stream("GET", url) as resp,
        ):
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk
                if len(body) > max_bytes:
                    return f"Error: content exceeds {max_bytes} bytes"
            text = body.decode("utf-8", errors="replace")
            # 简单提取正文（html 去标签）
            if "html" in content_type.lower():
                import re

                text = re.sub(
                    r"<script.*?</script>",
                    "",
                    text,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                text = re.sub(
                    r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE
                )
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
            return text[:max_bytes] if text else "(empty)"
    except Exception as e:  # noqa: BLE001
        return f"Error: fetch failed: {e}"


async def _web_search(args: dict[str, Any], ctx: ToolContext) -> str:
    query = str(args.get("query", ""))
    if not query:
        return "Error: query is required"
    if ctx.search_callback:
        try:
            return await ctx.search_callback(query)
        except Exception as e:  # noqa: BLE001
            return f"Error: search failed: {e}"
    api_key = os.getenv("BRAVE_API_KEY")
    if api_key:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query},
                    headers={
                        "X-Subscription-Token": api_key,
                        "Accept": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                results = [
                    f"{item.get('title')}\n{item.get('url')}\n{item.get('description')}"
                    for item in data.get("web", {}).get("results", [])[:10]
                ]
                return "\n\n".join(results) if results else "(no results)"
        except Exception as e:  # noqa: BLE001
            return f"Error: search failed: {e}"
    return "Error: WebSearch not configured. Set BRAVE_API_KEY or pass search_callback."


def builtin_tools() -> list[Tool]:
    """返回默认内置工具集。"""
    return [
        Tool(
            name="Bash",
            description="Run a shell command in the workspace (build/test/git).",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run",
                    },
                    "timeout": {"type": "number", "description": "Timeout in seconds"},
                },
                "required": ["command"],
            },
            handler=_bash,
            category="exec",
            command_field="command",
        ),
        Tool(
            name="Read",
            description="Read a text file, optionally with line numbers.",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute or workspace-relative path",
                    },
                    "offset": {
                        "type": "number",
                        "description": "1-based line to start",
                    },
                    "limit": {"type": "number", "description": "Max lines to read"},
                },
                "required": ["file_path"],
            },
            handler=_read,
            category="read",
            path_field="file_path",
        ),
        Tool(
            name="Write",
            description="Write text content to a file (creates parent dirs).",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to write"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["file_path", "content"],
            },
            handler=_write,
            category="write",
            path_field="file_path",
        ),
        Tool(
            name="Edit",
            description="Replace one occurrence of old_string with new_string.",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to edit"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["file_path", "old_string", "new_string"],
            },
            handler=_edit,
            category="write",
            path_field="file_path",
        ),
        Tool(
            name="Glob",
            description="Find files matching a glob pattern under the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern e.g. **/*.py",
                    },
                },
                "required": ["pattern"],
            },
            handler=_glob,
            category="read",
        ),
        Tool(
            name="Grep",
            description="Search text in files under the workspace using ripgrep.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {
                        "type": "string",
                        "description": "Path to search (default .)",
                    },
                },
                "required": ["pattern"],
            },
            handler=_grep,
            category="read",
            path_field="path",
        ),
        Tool(
            name="WebFetch",
            description="Fetch a URL and return text content.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_bytes": {"type": "number"},
                    "timeout": {"type": "number"},
                },
                "required": ["url"],
            },
            handler=_web_fetch,
            category="net",
        ),
        Tool(
            name="WebSearch",
            description="Search the web. Requires BRAVE_API_KEY or search_callback.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
            handler=_web_search,
            category="net",
        ),
    ]
