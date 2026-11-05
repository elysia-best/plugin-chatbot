"""Tests for Agent context estimation and transcript compaction."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent import Agent, LLMResponse, Message, ToolCall, Usage
from agent.context import estimate_message_tokens
from agent.errors import ContextOverflowError, is_context_overflow, parse_context_limit
from agent.store import SessionStore


class CompactionLLM:
    def __init__(self) -> None:
        self.calls: list[tuple[list[Message], str | None]] = []

    async def complete(self, messages, tools=None, system_prompt=None):
        self.calls.append((list(messages), system_prompt))
        if tools is None:
            return LLMResponse(content="summary of earlier discussion")
        return LLMResponse(content="final answer")


class MeasuredLLM:
    async def complete(self, messages, tools=None, system_prompt=None):
        return LLMResponse(content="answer", usage=Usage(prompt_tokens=77))


class OverflowOnceLLM:
    """主请求先报一次超限，压缩后成功；摘要请求正常返回。"""

    def __init__(self) -> None:
        self.main_calls = 0
        self.summary_calls = 0

    async def complete(self, messages, tools=None, system_prompt=None):
        if tools is None:
            self.summary_calls += 1
            return LLMResponse(content="summary")
        self.main_calls += 1
        if self.main_calls == 1:
            raise RuntimeError(
                "This model's maximum context length is 8192 tokens. "
                "However, your messages resulted in 20000 tokens."
            )
        return LLMResponse(content="ok")


class AlwaysOverflowLLM:
    def __init__(self) -> None:
        self.main_calls = 0
        self.summary_calls = 0

    async def complete(self, messages, tools=None, system_prompt=None):
        if tools is None:
            self.summary_calls += 1
            return LLMResponse(content="summary")
        self.main_calls += 1
        raise RuntimeError("context_length_exceeded: prompt is too long")


class BodyOnlyServiceUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("upstream request failed")
        self.body = {"error": {"message": "Service temporarily unavailable"}}


class TemporaryEngineFailureLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, tools=None, system_prompt=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("Error code: 500 - engine is not available temporarily")
        return LLMResponse(content="recovered")


class BodyOnlyServiceUnavailableLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, tools=None, system_prompt=None):
        self.calls += 1
        if self.calls == 1:
            raise BodyOnlyServiceUnavailable()
        return LLMResponse(content="recovered from 503")


class RateLimitLLM:
    def __init__(self, succeed_after: int, retry_after: str | None = None) -> None:
        self.succeed_after = succeed_after
        self.retry_after = retry_after
        self.calls = 0

    async def complete(self, messages, tools=None, system_prompt=None):
        self.calls += 1
        if self.calls < self.succeed_after:
            exc = RuntimeError(
                "Error code: 429 - inference exceeds tpm/rpm limit"
            )
            exc.status_code = 429
            exc.response = SimpleNamespace(
                headers={"retry-after": self.retry_after} if self.retry_after else {}
            )
            raise exc
        return LLMResponse(content="rate limit recovered")


class FailingSummaryLLM:
    def __init__(self) -> None:
        self.summary_calls = 0

    async def complete(self, messages, tools=None, system_prompt=None):
        if tools is None:
            self.summary_calls += 1
            raise RuntimeError("upstream boom")
        return LLMResponse(content="answer")


def _turns(count: int, prefix: str = "question") -> list[Message]:
    return [
        message
        for index in range(count)
        for message in (
            Message(role="user", content=f"{prefix} {index}"),
            Message(role="assistant", content=f"answer {index}"),
        )
    ]


class ContextCompactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_temporarily_unavailable_engine_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp)
            llm = TemporaryEngineFailureLLM()
            agent._llm = llm

            result = await agent.run("hello")

            self.assertEqual("completed", result.status)
            self.assertEqual("recovered", result.text)
            self.assertEqual(2, llm.calls)

    async def test_service_unavailable_in_error_body_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp)
            llm = BodyOnlyServiceUnavailableLLM()
            agent._llm = llm

            result = await agent.run("hello")

            self.assertEqual("completed", result.status)
            self.assertEqual("recovered from 503", result.text)
            self.assertEqual(2, llm.calls)

    async def test_tpm_rpm_rate_limit_retries_with_backoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp)
            llm = RateLimitLLM(succeed_after=3)
            agent._llm = llm
            delays = []

            async def capture_delay(seconds: float) -> None:
                delays.append(seconds)

            with patch("agent.core.asyncio.sleep", side_effect=capture_delay):
                result = await agent.run("hello")

            self.assertEqual("completed", result.status)
            self.assertEqual("rate limit recovered", result.text)
            self.assertEqual(3, llm.calls)
            self.assertEqual([2.0, 4.0], delays)

    async def test_rate_limit_respects_retry_after_header(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp)
            llm = RateLimitLLM(succeed_after=2, retry_after="3")
            agent._llm = llm
            delays = []

            async def capture_delay(seconds: float) -> None:
                delays.append(seconds)

            with patch("agent.core.asyncio.sleep", side_effect=capture_delay):
                result = await agent.run("hello")

            self.assertEqual("completed", result.status)
            self.assertEqual([3.0], delays)

    async def test_run_persists_provider_reported_prompt_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp)
            agent._llm = MeasuredLLM()
            chat_id = agent.new_chat()

            await agent.run("hello", chat_id=chat_id)

            record = agent.store.get(chat_id)
            if record is None:
                self.fail("session record was not persisted")
            self.assertEqual(77, record.last_prompt_tokens)
            self.assertGreater(record.last_estimated_tokens, 0)
            self.assertEqual(
                (77, record.last_estimated_tokens),
                agent.store.context_usage(chat_id, agent._context_fingerprint()),
            )

    async def test_provider_prompt_usage_calibrates_transcript_compaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store_root = Path(temp) / "sessions"
            store = SessionStore(store_root)
            agent = Agent(
                model="test",
                workspace=temp,
                store=store,
                tools=[],
                max_context=10_000,
                compact_rate=0.8,
            )
            llm = CompactionLLM()
            agent._llm = llm
            chat_id = agent.new_chat()
            history = agent.store.cache(chat_id)
            history.extend(_turns(6))
            estimated = agent._fixed_tokens() + estimate_message_tokens(history)
            fingerprint = agent._context_fingerprint()
            agent.store.set_context_usage(
                chat_id,
                prompt_tokens=9000,
                estimated_tokens=estimated,
                fingerprint=fingerprint,
            )

            await agent._compact_history(chat_id, history, "next")

            self.assertEqual(1, len(llm.calls))
            self.assertIsNone(agent.store.context_usage(chat_id, fingerprint))

    async def test_context_usage_survives_store_reload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store_root = Path(temp) / "sessions"
            store = SessionStore(store_root)
            chat_id = store.new_chat().chat_id
            store.set_context_usage(
                chat_id,
                prompt_tokens=1234,
                estimated_tokens=800,
                fingerprint="model-tools-prompt",
            )

            restored = SessionStore(store_root)

            self.assertEqual(
                (1234, 800),
                restored.context_usage(chat_id, "model-tools-prompt"),
            )

    async def test_compaction_replaces_jsonl_and_retains_recent_image_and_tool_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store_root = Path(temp) / "sessions"
            agent = Agent(
                model="test",
                workspace=temp,
                store_root=store_root,
                tools=[],
                system_prompt="test",
                max_context=10_000,
                compact_rate=0.8,
            )
            llm = CompactionLLM()
            agent._llm = llm
            chat_id = agent.new_chat()
            history = agent.store.cache(chat_id)
            history.extend(_turns(6, prefix="old question"))
            history.extend(
                [
                    Message(
                        role="user",
                        content=[
                            {"type": "text", "text": "recent image"},
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:image/png;base64,BB=="},
                            },
                        ],
                    ),
                    Message(
                        role="assistant",
                        tool_calls=[
                            ToolCall(
                                id="call-recent",
                                name="chat_status",
                                arguments={},
                            )
                        ],
                    ),
                    Message(
                        role="tool",
                        content="recent tool result",
                        tool_call_id="call-recent",
                        name="chat_status",
                    ),
                    Message(role="assistant", content="recent tool answer"),
                ]
            )
            agent.store.save(chat_id)
            before_lines = (store_root / f"{chat_id}.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertGreater(len(before_lines), 8)

            result = await agent._compact_history(
                chat_id, history, "next request", force=True
            )

            self.assertEqual(1, len(llm.calls))
            self.assertIn("summary", history[0].content or "")
            self.assertTrue(
                any(
                    isinstance(message.content, list)
                    and any(block.get("type") == "image_url" for block in message.content)
                    for message in history
                )
            )
            self.assertTrue(any("recent tool answer" in (m.content or "") for m in history))
            self.assertTrue(any(m.role == "tool" and "recent tool result" in (m.content or "") for m in history))
            self.assertGreaterEqual(result.completion_tokens, 0)
            after_lines = (store_root / f"{chat_id}.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertLess(len(after_lines), len(before_lines))
            self.assertTrue(all("summary of earlier discussion" not in line for line in before_lines))

            restored = Agent(model="test", workspace=temp, store_root=store_root)
            restored.load_chat(chat_id)
            self.assertIn("summary of earlier discussion", restored.history()[0].content or "")

            await agent.run("continue after compaction", chat_id=chat_id)
            continued = Agent(model="test", workspace=temp, store_root=store_root)
            continued.load_chat(chat_id)
            self.assertTrue(
                any(
                    message.role == "user"
                    and message.content == "continue after compaction"
                    for message in continued.history()
                )
            )

    async def test_estimator_counts_cjk_and_image_payload_without_base64_size(self) -> None:
        text_tokens = estimate_message_tokens([Message(role="user", content="你好")])
        image_tokens = estimate_message_tokens(
            [
                Message(
                    role="user",
                    content=[
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64," + "A" * 10000},
                        }
                    ],
                )
            ]
        )
        self.assertGreaterEqual(text_tokens, 10)
        self.assertLess(image_tokens, 2000)

    async def test_fixed_prompt_and_tool_schemas_count_toward_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(
                model="test",
                workspace=temp,
                system_prompt="persona " * 3000,
                max_context=50_000,
                compact_rate=0.8,
            )
            budget = agent._context_budget()

            self.assertGreater(budget.fixed, 3000)
            self.assertEqual(int(50_000 * 0.8), budget.trigger)
            self.assertEqual(budget.trigger - budget.fixed, budget.history_limit)

    async def test_huge_system_prompt_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(
                model="test",
                workspace=temp,
                tools=[],
                system_prompt="x" * 40_000,
                max_context=12_000,
                compact_rate=0.8,
            )
            chat_id = agent.new_chat()

            self.assertEqual(0, agent._context_budget().history_limit)
            await agent._compact_history(chat_id, [], "hi")

    async def test_overflow_is_detected_and_limit_parsed(self) -> None:
        error = RuntimeError(
            "This model's maximum context length is 8192 tokens. "
            "However, your messages resulted in 20000 tokens."
        )
        self.assertTrue(is_context_overflow(error))
        self.assertEqual(8192, parse_context_limit(error))
        dashscope = RuntimeError(
            "InvalidParameter: Range of input length should be [1, 129024]"
        )
        self.assertTrue(is_context_overflow(dashscope))
        self.assertEqual(129024, parse_context_limit(dashscope))
        self.assertFalse(is_context_overflow(RuntimeError("invalid api key")))
        self.assertTrue(is_context_overflow(ContextOverflowError("boom", 4096)))

    async def test_overflow_compacts_and_retries_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(
                model="test",
                workspace=temp,
                tools=[],
                system_prompt="test",
                max_context=262_144,
                compact_rate=0.8,
            )
            llm = OverflowOnceLLM()
            agent._llm = llm
            chat_id = agent.new_chat()
            agent.store.cache(chat_id).extend(_turns(10))

            result = await agent.run("hello", chat_id=chat_id)

            self.assertEqual("completed", result.status)
            self.assertEqual(8192, agent.max_context)
            self.assertEqual(2, llm.main_calls)
            self.assertEqual(1, llm.summary_calls)
            self.assertIn("[Earlier conversation summary]", agent.history()[0].content or "")

    async def test_repeated_overflow_returns_error_after_single_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(
                model="test",
                workspace=temp,
                tools=[],
                system_prompt="test",
                max_context=262_144,
                compact_rate=0.8,
            )
            llm = AlwaysOverflowLLM()
            agent._llm = llm
            chat_id = agent.new_chat()
            agent.store.cache(chat_id).extend(_turns(10))

            result = await agent.run("hello", chat_id=chat_id)

            self.assertEqual("error", result.status)
            self.assertIn("context", (result.error or "").lower())
            self.assertEqual(2, llm.main_calls)

    async def test_summarizer_receives_flat_text_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp, tools=[])
            captured: list[list[Message]] = []

            class Recorder:
                async def complete(self, messages, tools=None, system_prompt=None):
                    if tools is None:
                        captured.append(list(messages))
                        return LLMResponse(content="summary")
                    return LLMResponse(content="answer")

            agent._llm = Recorder()
            chat_id = agent.new_chat()
            history = agent.store.cache(chat_id)
            history.extend(
                [
                    Message(role="user", content="old question"),
                    Message(
                        role="assistant",
                        tool_calls=[ToolCall("c1", "chat_status", {})],
                    ),
                    Message(
                        role="tool",
                        content="tool output",
                        tool_call_id="c1",
                        name="chat_status",
                    ),
                    Message(
                        role="user",
                        content=[
                            {"type": "text", "text": "look"},
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:image/png;base64,CC=="},
                            },
                        ],
                    ),
                    *_turns(6),
                ]
            )

            await agent._compact_history(chat_id, history, "next", force=True)

            self.assertEqual(1, len(captured))
            self.assertEqual(1, len(captured[0]))
            self.assertEqual("user", captured[0][0].role)
            body = captured[0][0].content or ""
            self.assertIn("[tool:chat_status]", body)
            self.assertIn("[image]", body)
            self.assertNotIn("base64", body)

    async def test_summary_source_respects_50_message_cap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp, tools=[])
            history = [
                Message(
                    role="user" if index % 2 == 0 else "assistant",
                    content="FIRST-SENTINEL" if index == 0 else f"m{index}",
                )
                for index in range(200)
            ]

            source = agent._summary_source(history)

            self.assertLessEqual(len(source.splitlines()), 50)
            self.assertNotIn("FIRST-SENTINEL", source)

    async def test_summary_failure_falls_back_to_hard_trim(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(
                model="test",
                workspace=temp,
                tools=[],
                system_prompt="test",
                max_context=2000,
                compact_rate=0.8,
            )
            llm = FailingSummaryLLM()
            agent._llm = llm
            chat_id = agent.new_chat()
            history = agent.store.cache(chat_id)
            history.extend(_turns(10))
            history.append(
                Message(role="tool", content="Z" * 50_000, tool_call_id="c9")
            )

            await agent._compact_history(chat_id, history, "next", force=True)

            self.assertEqual(1, llm.summary_calls)
            self.assertLessEqual(
                estimate_message_tokens(history),
                agent._context_budget().history_limit,
            )
            self.assertIsNone(
                agent.store.context_usage(chat_id, agent._context_fingerprint())
            )

    async def test_hard_trim_clamps_gigantic_tool_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp, tools=[])
            messages = [
                Message(role="user", content="hi"),
                Message(
                    role="assistant",
                    tool_calls=[ToolCall("c1", "Read", {})],
                ),
                Message(
                    role="tool",
                    content="A" * 200_000,
                    tool_call_id="c1",
                    name="Read",
                ),
            ]

            trimmed = agent._hard_trim(messages, limit_tokens=2000)

            if trimmed is None:
                self.fail("hard trim should have shortened the transcript")
            self.assertLessEqual(estimate_message_tokens(trimmed), 2000)
            self.assertEqual("tool", trimmed[-1].role)
            self.assertEqual("c1", trimmed[-1].tool_call_id)
            self.assertIn("...[truncated]...", trimmed[-1].content or "")

    async def test_hard_trim_keeps_newest_user_and_no_leading_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp, tools=[])
            messages: list[Message] = []
            for index in range(10):
                messages.append(Message(role="user", content=f"u{index}"))
                messages.append(Message(role="assistant", content="a" * 5000))

            trimmed = agent._hard_trim(messages, limit_tokens=300)

            if trimmed is None:
                self.fail("hard trim should have shortened the transcript")
            self.assertNotEqual("tool", trimmed[0].role)
            self.assertNotEqual("tool", trimmed[-1].role)
            self.assertTrue(any(message.content == "u9" for message in trimmed))

    async def test_repair_transcript_fills_orphan_tool_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp, tools=[])
            history = [
                Message(role="tool", content="orphan", tool_call_id="lost"),
                Message(role="user", content="hi"),
                Message(
                    role="assistant",
                    tool_calls=[ToolCall("c1", "chat_status", {})],
                ),
            ]

            changed = agent._repair_transcript(history)

            self.assertTrue(changed)
            self.assertEqual("user", history[0].role)
            self.assertEqual("tool", history[-1].role)
            self.assertEqual("c1", history[-1].tool_call_id)
            self.assertEqual("Error: tool call interrupted", history[-1].content)

    async def test_run_repairs_orphan_tool_calls_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store_root = Path(temp) / "sessions"
            agent = Agent(
                model="test",
                workspace=temp,
                store_root=store_root,
                tools=[],
                system_prompt="test",
            )
            agent._llm = CompactionLLM()
            chat_id = agent.new_chat()
            agent.store.replace(
                chat_id,
                [
                    Message(role="user", content="hi"),
                    Message(
                        role="assistant",
                        content="thinking",
                        tool_calls=[ToolCall("c1", "chat_status", {})],
                    ),
                ],
            )

            result = await agent.run("again", chat_id=chat_id)

            self.assertEqual("completed", result.status)
            messages = agent.history()
            self.assertTrue(
                any(
                    message.role == "tool" and message.tool_call_id == "c1"
                    for message in messages
                )
            )
            saved = (store_root / f"{chat_id}.jsonl").read_text(encoding="utf-8")
            self.assertIn("Error: tool call interrupted", saved)

    async def test_summary_source_includes_previous_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp, tools=[])
            history = [
                Message(
                    role="assistant",
                    content="[Earlier conversation summary]\nOLD-FACTS",
                ),
                *[
                    Message(
                        role="user" if index % 2 == 0 else "assistant",
                        content=f"m{index}",
                    )
                    for index in range(200)
                ],
            ]

            source = agent._summary_source(history)

            self.assertIn("OLD-FACTS", source)
            headers = [line for line in source.splitlines() if line.startswith("[")]
            self.assertLessEqual(len(headers), 51)

    async def test_hard_trim_keeps_leading_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp, tools=[])
            messages = [
                Message(
                    role="assistant",
                    content="[Earlier conversation summary]\nKEEP-ME",
                ),
                *_turns(10),
            ]

            trimmed = agent._hard_trim(messages, limit_tokens=100)

            if trimmed is None:
                self.fail("hard trim should have shortened the transcript")
            self.assertIn("KEEP-ME", trimmed[0].content or "")

    async def test_long_conversation_with_wrong_budget_self_heals(self) -> None:
        limit = 8000

        class StrictLLM:
            def __init__(self) -> None:
                self.rejections = 0
                self.max_prompt = 0

            async def complete(self, messages, tools=None, system_prompt=None):
                tokens = (
                    estimate_message_tokens(messages) + len(system_prompt or "") // 4
                )
                if tokens > limit:
                    self.rejections += 1
                    raise RuntimeError(
                        f"This model's maximum context length is {limit} tokens"
                    )
                if tools is None:
                    return LLMResponse(content="summary")
                self.max_prompt = max(self.max_prompt, tokens)
                return LLMResponse(content="ok")

        with tempfile.TemporaryDirectory() as temp:
            # 故意把预算配得远高于真实模型上限，验证超限自愈
            agent = Agent(
                model="test",
                workspace=temp,
                tools=[],
                system_prompt="persona " * 500,
                max_context=200_000,
                compact_rate=0.8,
            )
            llm = StrictLLM()
            agent._llm = llm
            chat_id = agent.new_chat()

            for index in range(30):
                result = await agent.run(
                    "Q" * 1200 + f" #{index}", chat_id=chat_id
                )
                self.assertEqual("completed", result.status, result.error)

            self.assertEqual(1, llm.rejections)
            self.assertEqual(limit, agent.max_context)
            self.assertLess(llm.max_prompt, limit)

    async def test_apply_context_limit_never_raises_learned_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(model="test", workspace=temp, max_context=262_144)

            agent.apply_context_limit(32_000)
            self.assertEqual(32_000, agent.max_context)

            agent._adopt_overflow_limit(16_000)
            self.assertEqual(16_000, agent.max_context)

            agent.apply_context_limit(32_000)
            self.assertEqual(16_000, agent.max_context)
