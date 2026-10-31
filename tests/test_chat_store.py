"""多 chat + 持久化集成测试（mock LLM，可直接运行）。"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import Agent, LLMResponse, PermissionRule
from agent.messages import ToolCall

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


class StatefulLLM:
    """按调用次数返回预设序列；记录收到的 messages。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.received = []

    async def complete(self, messages, tools=None, system_prompt=None):
        self.calls += 1
        self.received.append(list(messages))
        idx = min(self.calls - 1, len(self.responses) - 1)
        return self.responses[idx]


def tool_response(name, args, cid="call_1"):
    return LLMResponse(tool_calls=[ToolCall(id=cid, name=name, arguments=args)])


async def test_new_chat_run_persist():
    """new_chat -> run() 两轮工具往返 -> 落盘 -> 重新加载历史完整。"""
    with tempfile.TemporaryDirectory() as ws:
        store_root = os.path.join(ws, ".agent", "sessions")
        llm = StatefulLLM(
            [
                tool_response("Write", {"file_path": "out.txt", "content": "hi"}),
                LLMResponse(content="done"),
            ]
        )
        agent = Agent(
            model="m",
            workspace=ws,
            store_root=store_root,
            permissions=[PermissionRule(tool="Write", behavior="allow")],
        )
        agent._llm = llm
        cid = agent.new_chat(alias="test1")
        result = await agent.run("write a file")
        check("persist_status", result.status == "completed")
        check("persist_file_written", os.path.exists(os.path.join(ws, "out.txt")))
        check(
            "persist_jsonl_exists",
            os.path.exists(os.path.join(store_root, f"{cid}.jsonl")),
        )

        # 重新加载历史
        agent2 = Agent(model="m", workspace=ws, store_root=store_root)
        rec = agent2.load_chat(cid)
        hist = agent2.history()
        check("reload_rec", rec.chat_id == cid)
        check(
            "reload_history_count", len(hist) == 4
        )  # user + assistant(tool) + tool + assistant(text)
        check("reload_history_user", hist[0].content == "write a file")
        check(
            "reload_history_tool",
            any(m.role == "tool" and "Wrote" in (m.content or "") for m in hist),
        )


async def test_load_chat_continues():
    """load_chat 后 run() 发送给 LLM 的 messages 含首轮历史。"""
    with tempfile.TemporaryDirectory() as ws:
        store_root = os.path.join(ws, ".agent", "sessions")
        llm = StatefulLLM(
            [
                tool_response("Write", {"file_path": "out.txt", "content": "hi"}),
                LLMResponse(content="done"),
            ]
        )
        agent = Agent(
            model="m",
            workspace=ws,
            store_root=store_root,
            permissions=[PermissionRule(tool="Write", behavior="allow")],
        )
        agent._llm = llm
        cid = agent.new_chat()
        await agent.run("first message")

        # 新 agent 加载同一 chat，续接
        llm2 = StatefulLLM([LLMResponse(content="second reply")])
        agent2 = Agent(model="m", workspace=ws, store_root=store_root)
        agent2._llm = llm2
        agent2.load_chat(cid)
        await agent2.run("second message")
        # 发给 LLM 的 messages 应含首轮历史
        sent = llm2.received[0]
        check(
            "continue_includes_prior",
            any(m.role == "user" and m.content == "first message" for m in sent),
        )
        check(
            "continue_includes_new",
            any(m.role == "user" and m.content == "second message" for m in sent),
        )
        check("continue_has_tool_result", any(m.role == "tool" for m in sent))


async def test_multi_chat_isolation():
    """多 chat 并存互不污染。"""
    with tempfile.TemporaryDirectory() as ws:
        store_root = os.path.join(ws, ".agent", "sessions")
        llm = StatefulLLM([LLMResponse(content="reply")])
        agent = Agent(
            model="m",
            workspace=ws,
            store_root=store_root,
            permissions=[PermissionRule(tool="Bash", behavior="allow")],
        )
        agent._llm = llm
        a = agent.new_chat(alias="a")
        b = agent.new_chat(alias="b")
        check("current_is_b", agent.current_chat() == b)
        await agent.run("msg to b")
        agent.use_chat(a)
        check("switched_to_a", agent.current_chat() == a)
        await agent.run("msg to a")
        check("a_history_len", len(agent.history()) == 2)
        agent.use_chat(b)
        check("b_history_len", len(agent.history()) == 2)
        check("a_not_b", agent.history()[0].content == "msg to b")
        # list_chats
        check("list_two", len(agent.list_chats()) == 2)


async def test_autosave_false():
    """autosave=False 时 run() 不写盘，显式 save() 才写。"""
    with tempfile.TemporaryDirectory() as ws:
        store_root = os.path.join(ws, ".agent", "sessions")
        llm = StatefulLLM([LLMResponse(content="done")])
        agent = Agent(model="m", workspace=ws, store_root=store_root, autosave=False)
        agent._llm = llm
        cid = agent.new_chat()
        await agent.run("hi")
        check(
            "no_autosave_no_file",
            not os.path.exists(os.path.join(store_root, f"{cid}.jsonl")),
        )
        agent.save()
        check(
            "explicit_save_writes",
            os.path.exists(os.path.join(store_root, f"{cid}.jsonl")),
        )


async def test_permission_deny_persist():
    """权限拒绝也落盘（记录错误结果）。"""
    with tempfile.TemporaryDirectory() as ws:
        store_root = os.path.join(ws, ".agent", "sessions")
        llm = StatefulLLM(
            [
                tool_response("Write", {"file_path": "x.txt", "content": "h"}),
                LLMResponse(content="done"),
            ]
        )
        agent = Agent(
            model="m",
            workspace=ws,
            store_root=store_root,
            permissions=[PermissionRule(tool="Write", behavior="deny")],
        )
        agent._llm = llm
        cid = agent.new_chat()
        result = await agent.run("write")
        check("deny_is_error", result.tool_calls[0].is_error)
        check(
            "deny_persisted", os.path.exists(os.path.join(store_root, f"{cid}.jsonl"))
        )
        hist = agent.history()
        check(
            "deny_tool_msg",
            any(m.role == "tool" and "denied" in (m.content or "") for m in hist),
        )


async def main():
    await test_new_chat_run_persist()
    await test_load_chat_continues()
    await test_multi_chat_isolation()
    await test_autosave_false()
    await test_permission_deny_persist()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
