"""对话集成测试：mock LLM 验证工具往返 / max_turns / 权限拒绝 / abort。"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.core import Agent
from agent.llm import LLMClient, LLMResponse
from agent.messages import ToolCall
from agent.permissions import PermissionRule

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


class ScriptedLLM:
    """按调用次数返回预设响应序列。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.last_messages: list = []

    async def complete(self, messages, tools=None, system_prompt=None):
        self.calls += 1
        self.last_messages = list(messages)
        idx = min(self.calls - 1, len(self.responses) - 1)
        return self.responses[idx]


def make_toolcall(name, args, call_id="call_1"):
    return ToolCall(id=call_id, name=name, arguments=args)


async def _false() -> bool:
    return False


def make_response(content="", tool_calls=None):
    return LLMResponse(content=content, tool_calls=tool_calls or [])


async def test_tool_roundtrip():
    """模型调用 Write 工具 → 工具结果回填 → 模型给出最终回复。"""
    with tempfile.TemporaryDirectory() as ws:
        llm = ScriptedLLM(
            [
                # 第一轮：调用 Write
                make_response(
                    tool_calls=[
                        make_toolcall(
                            "Write", {"file_path": "out.txt", "content": "hi"}, "call_1"
                        )
                    ]
                ),
                # 第二轮：给出最终文本
                make_response(content="done"),
            ]
        )
        agent = Agent(
            model="test",
            workspace=ws,
            permissions=[PermissionRule(tool="Write", behavior="allow")],
            llm_client=LLMClient(model="test", client=None),
        )
        # 注入 mock llm
        agent._llm = llm
        result = await agent.run("write a file")
        check("roundtrip_status", result.status == "completed")
        check("roundtrip_text", result.text == "done")
        check("roundtrip_tool_count", len(result.tool_calls) == 1)
        check("roundtrip_tool_name", result.tool_calls[0].name == "Write")
        check("roundtrip_file_written", os.path.exists(os.path.join(ws, "out.txt")))
        # 第二轮的 messages 应包含 tool 结果回填
        msgs = llm.last_messages
        check(
            "roundtrip_tool_result_backfilled",
            any(
                m.role == "tool"
                and m.tool_call_id == "call_1"
                and "Wrote" in (m.content or "")
                for m in msgs
            ),
        )


async def test_max_turns():
    """模型持续调用工具直到 max_turns。"""
    with tempfile.TemporaryDirectory() as ws:
        llm = ScriptedLLM(
            [
                make_response(
                    tool_calls=[
                        make_toolcall("Bash", {"command": "echo x"}, f"call_{i}")
                    ]
                )
                for i in range(5)
            ]
        )
        agent = Agent(
            model="test",
            workspace=ws,
            max_turns=2,
            permissions=[PermissionRule(tool="Bash", behavior="allow")],
            llm_client=LLMClient(model="test", client=None),
        )
        agent._llm = llm
        result = await agent.run("loop")
        check("maxturns_status", result.status == "max_turns")
        check("maxturns_tool_count", len(result.tool_calls) == 2)


async def test_permission_denied():
    """权限 deny 时工具结果标记为错误并回填。"""
    with tempfile.TemporaryDirectory() as ws:
        llm = ScriptedLLM(
            [
                make_response(
                    tool_calls=[
                        make_toolcall(
                            "Write", {"file_path": "x.txt", "content": "h"}, "call_1"
                        )
                    ]
                ),
                make_response(content="done"),
            ]
        )
        agent = Agent(
            model="test",
            workspace=ws,
            permissions=[PermissionRule(tool="Write", behavior="deny")],
            llm_client=LLMClient(model="test", client=None),
        )
        agent._llm = llm
        result = await agent.run("write")
        check("denied_tool_is_error", result.tool_calls[0].is_error is True)
        check("denied_tool_allowed_false", result.tool_calls[0].allowed is False)
        check("denied_no_file", not os.path.exists(os.path.join(ws, "x.txt")))
        msgs = llm.last_messages
        check(
            "denied_backfilled",
            any(m.role == "tool" and "denied" in (m.content or "") for m in msgs),
        )


async def test_ask_denied_via_callback():
    """ask 回调返回 False 时拒绝。"""
    with tempfile.TemporaryDirectory() as ws:
        llm = ScriptedLLM(
            [
                make_response(
                    tool_calls=[
                        make_toolcall("Bash", {"command": "rm -rf x"}, "call_1")
                    ]
                ),
                make_response(content="done"),
            ]
        )
        agent = Agent(
            model="test",
            workspace=ws,
            permissions=[],
            ask_callback=lambda q: _false(),
            llm_client=LLMClient(model="test", client=None),
        )
        agent._llm = llm
        result = await agent.run("rm")
        check("ask_denied_error", result.tool_calls[0].is_error is True)
        check("ask_denied_allowed_false", result.tool_calls[0].allowed is False)


async def test_abort():
    """abort 中断对话。"""
    with tempfile.TemporaryDirectory() as ws:
        llm = ScriptedLLM(
            [
                make_response(content="partial"),
            ]
        )
        agent = Agent(
            model="test",
            workspace=ws,
            llm_client=LLMClient(model="test", client=None),
        )
        agent._llm = llm
        agent.abort()
        result = await agent.run("hi")
        check("abort_status", result.status == "aborted")


async def main():
    await test_tool_roundtrip()
    await test_max_turns()
    await test_permission_denied()
    await test_ask_denied_via_callback()
    await test_abort()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
