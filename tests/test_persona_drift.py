"""人格漂移检测与一次性自动纠正的行为测试。"""

from __future__ import annotations

import tempfile
import unittest
from typing import Any

from agent import Agent, LLMResponse, Message, ToolCall


class ScriptedLLM:
    """按顺序返回预设回复，并记录每次请求的消息列表。"""

    def __init__(self, replies: list[LLMResponse]) -> None:
        self.replies = list(replies)
        self.calls: list[list[Message]] = []

    async def complete(
        self,
        messages: list[Message],
        tools: Any = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        self.calls.append([*messages])
        if not self.replies:
            return LLMResponse(content="fallback")
        return self.replies.pop(0)


class DriftDetectingLLM:
    """第一次回复带禁用词，第二次符合人格。"""

    def __init__(self, banned: str = "本鲸") -> None:
        self.banned = banned
        self.calls: list[list[Message]] = []

    async def complete(
        self,
        messages: list[Message],
        tools: Any = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        self.calls.append([*messages])
        if len(self.calls) == 1:
            return LLMResponse(content=f"{self.banned}来了，今天也想吃白饭")
        return LLMResponse(content="我是魔法鼓鼓鱼，河豚一只")


def _guard(terms: list[str]):
    def guard(text: str) -> str | None:
        for term in terms:
            if term in text:
                return term
        return None

    return guard


class PersonaDriftTests(unittest.IsolatedAsyncioTestCase):
    async def test_guard_hit_discards_reply_and_retries_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(
                model="test",
                workspace=temp,
                tools=[],
                output_guard=_guard(["本鲸"]),
            )
            llm = DriftDetectingLLM()
            agent._llm = llm
            events: list[tuple[str, dict[str, Any]]] = []

            async def on_event(name: str, payload: dict[str, Any]) -> None:
                events.append((name, payload))

            agent._on_event = on_event
            chat_id = agent.new_chat()

            result = await agent.run("你是谁", chat_id=chat_id)

            self.assertEqual("completed", result.status)
            self.assertEqual("我是魔法鼓鼓鱼，河豚一只", result.text)
            self.assertEqual(2, len(llm.calls))
            # 第二次请求带了一次性纠正提示，且不进历史
            retry_messages = llm.calls[1]
            self.assertEqual("user", retry_messages[-1].role)
            self.assertIn("本鲸", retry_messages[-1].content or "")
            self.assertIn("已被丢弃", retry_messages[-1].content or "")
            stored = agent.history()
            self.assertFalse(
                any("已被丢弃" in str(message.content) for message in stored)
            )
            self.assertFalse(any("本鲸" in str(message.content) for message in stored))
            self.assertEqual(1, len(events))
            self.assertEqual("persona_drift", events[0][0])
            self.assertTrue(events[0][1]["retried"])

    async def test_second_hit_is_kept_and_recorded_without_third_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(
                model="test",
                workspace=temp,
                tools=[],
                output_guard=_guard(["本鲸"]),
            )
            llm = ScriptedLLM(
                [
                    LLMResponse(content="本鲸第一版"),
                    LLMResponse(content="本鲸第二版"),
                ]
            )
            agent._llm = llm
            events: list[dict[str, Any]] = []

            async def on_event(name: str, payload: dict[str, Any]) -> None:
                events.append(payload)

            agent._on_event = on_event
            chat_id = agent.new_chat()

            result = await agent.run("你是谁", chat_id=chat_id)

            self.assertEqual(2, len(llm.calls))
            self.assertEqual("本鲸第二版", result.text)
            self.assertEqual(2, len(events))
            self.assertTrue(events[0]["retried"])
            self.assertFalse(events[1]["retried"])

    async def test_no_hit_skips_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(
                model="test",
                workspace=temp,
                tools=[],
                output_guard=_guard(["本鲸"]),
            )
            llm = ScriptedLLM([LLMResponse(content="我是河豚")])
            agent._llm = llm
            chat_id = agent.new_chat()

            result = await agent.run("你是谁", chat_id=chat_id)

            self.assertEqual(1, len(llm.calls))
            self.assertEqual("我是河豚", result.text)

    async def test_missing_guard_never_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp, tools=[])
            llm = ScriptedLLM([LLMResponse(content="本鲸随便说")])
            agent._llm = llm
            chat_id = agent.new_chat()

            result = await agent.run("你是谁", chat_id=chat_id)

            self.assertEqual(1, len(llm.calls))
            self.assertEqual("本鲸随便说", result.text)

    async def test_guard_exception_does_not_break_the_turn(self) -> None:
        def boom(_text: str) -> str | None:
            raise RuntimeError("guard bug")

        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(
                model="test",
                workspace=temp,
                tools=[],
                output_guard=boom,
            )
            llm = ScriptedLLM([LLMResponse(content="正常回复")])
            agent._llm = llm
            chat_id = agent.new_chat()

            result = await agent.run("hi", chat_id=chat_id)

            self.assertEqual("completed", result.status)
            self.assertEqual("正常回复", result.text)

    async def test_tool_turn_records_drift_without_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(
                model="test",
                workspace=temp,
                tools=[],
                output_guard=_guard(["本鲸"]),
            )
            llm = ScriptedLLM(
                [
                    LLMResponse(
                        content="本鲸先查一下",
                        tool_calls=[ToolCall("c1", "chat_status", {})],
                    ),
                    LLMResponse(content="查完了，我是河豚"),
                ]
            )
            agent._llm = llm
            events: list[dict[str, Any]] = []

            async def on_event(name: str, payload: dict[str, Any]) -> None:
                if name == "persona_drift":
                    events.append(payload)

            agent._on_event = on_event
            chat_id = agent.new_chat()

            result = await agent.run("hi", chat_id=chat_id)

            self.assertEqual("completed", result.status)
            # 工具轮正文与会话正文一样会累积（原有行为），这里只关心命中处理
            self.assertIn("查完了，我是河豚", result.text)
            # 工具轮命中只告警，不回滚重试（否则会重复发消息）
            self.assertEqual(2, len(llm.calls))
            self.assertEqual(1, len(events))
            self.assertTrue(events[0]["tool_turn"])
            self.assertFalse(events[0]["retried"])


if __name__ == "__main__":
    unittest.main()
