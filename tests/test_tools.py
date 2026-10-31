"""工具单元测试（可直接运行）。"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.tool import ToolContext
from agent.tools import builtin_tools

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name}")


async def run_tool(name, args, ctx):
    tools = {t.name: t for t in builtin_tools()}
    t = tools[name]
    return await t.call(args, ctx)


def main():
    with tempfile.TemporaryDirectory() as ws:
        ctx = ToolContext(workspace=ws, timeout=10)

        # Write
        res = asyncio.run(
            run_tool("Write", {"file_path": "a.txt", "content": "hello world"}, ctx)
        )
        check("write_creates", os.path.exists(os.path.join(ws, "a.txt")))
        check("write_ok", res.startswith("Wrote"))

        # Read
        res = asyncio.run(run_tool("Read", {"file_path": "a.txt"}, ctx))
        check("read_content", "hello world" in res)
        check("read_numbered", "\t" in res)

        # Read missing
        res = asyncio.run(run_tool("Read", {"file_path": "nope.txt"}, ctx))
        check("read_missing_error", res.startswith("Error:"))

        # Edit
        res = asyncio.run(
            run_tool(
                "Edit",
                {"file_path": "a.txt", "old_string": "world", "new_string": "python"},
                ctx,
            )
        )
        check("edit_ok", res.startswith("Edited"))
        res = asyncio.run(run_tool("Read", {"file_path": "a.txt"}, ctx))
        check("edit_applied", "python" in res and "world" not in res)

        # Edit missing old
        res = asyncio.run(
            run_tool(
                "Edit",
                {"file_path": "a.txt", "old_string": "zzz", "new_string": "x"},
                ctx,
            )
        )
        check("edit_missing_error", res.startswith("Error:"))

        # Glob
        asyncio.run(
            run_tool("Write", {"file_path": "src/x.py", "content": "print(1)"}, ctx)
        )
        asyncio.run(run_tool("Write", {"file_path": "src/y.md", "content": "md"}, ctx))
        res = asyncio.run(run_tool("Glob", {"pattern": "**/*.py"}, ctx))
        check("glob_py", "src/x.py" in res)
        res = asyncio.run(run_tool("Glob", {"pattern": "*.md"}, ctx))
        check("glob_no_match", "(no matches)" in res)

        # Grep
        asyncio.run(
            run_tool(
                "Write",
                {"file_path": "searchme.txt", "content": "alpha\nbeta\nalpha again"},
                ctx,
            )
        )
        res = asyncio.run(run_tool("Grep", {"pattern": "alpha", "path": "."}, ctx))
        check("grep_hits", "alpha" in res)
        res = asyncio.run(run_tool("Grep", {"pattern": "zzz_none", "path": "."}, ctx))
        check("grep_none", "(no matches)" in res)

        # Bash
        res = asyncio.run(run_tool("Bash", {"command": "echo hello-bash"}, ctx))
        check("bash_ok", "hello-bash" in res)

        # WebFetch (no network in test) - just check error path
        res = asyncio.run(run_tool("WebFetch", {"url": "http://127.0.0.1:1/none"}, ctx))
        check("webfetch_error", res.startswith("Error:"))

        # WebSearch not configured
        res = asyncio.run(run_tool("WebSearch", {"query": "test"}, ctx))
        check("websearch_not_configured", "not configured" in res)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
