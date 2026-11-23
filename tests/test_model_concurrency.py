"""按模型的 FIFO 并发闸门与排队超时：单元级回归测试。"""

from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from nonebot_plugin_alconna import Target

from agent import AgentResult, LLMResponse, Usage
from agent.messages import Message
from plugin_chatbot.bridge.concurrency import (
    DEFAULT_QUEUE_WAIT_SECONDS,
    GatedLLM,
    ModelGate,
    ModelQueueTimeoutError,
    normalize_concurrency,
    normalize_queue_wait,
)
from plugin_chatbot.bridge.service import BridgeConfig, BridgeService, IncomingMessage


def _usage() -> Usage:
    return Usage()


class NormalizeTests(unittest.TestCase):
    def test_normalize_concurrency_accepts_valid_range(self) -> None:
        self.assertIsNone(normalize_concurrency(None))
        self.assertIsNone(normalize_concurrency(""))
        self.assertIsNone(normalize_concurrency(0))
        self.assertIsNone(normalize_concurrency(-3))
        self.assertEqual(1, normalize_concurrency(1))
        self.assertEqual(8, normalize_concurrency("8"))
        self.assertEqual(64, normalize_concurrency(64))
        self.assertEqual(64, normalize_concurrency(1000))

    def test_normalize_concurrency_rejects_garbage(self) -> None:
        for value in ("abc", [], {}):
            with self.subTest(value=value):
                self.assertIsNone(normalize_concurrency(value))

    def test_normalize_queue_wait_falls_back_to_default(self) -> None:
        self.assertEqual(DEFAULT_QUEUE_WAIT_SECONDS, normalize_queue_wait(None))
        self.assertEqual(DEFAULT_QUEUE_WAIT_SECONDS, normalize_queue_wait(0))
        self.assertEqual(DEFAULT_QUEUE_WAIT_SECONDS, normalize_queue_wait(-5))
        self.assertEqual(DEFAULT_QUEUE_WAIT_SECONDS, normalize_queue_wait("abc"))
        self.assertEqual(1.0, normalize_queue_wait(0.5))
        self.assertEqual(30.0, normalize_queue_wait(30))
        self.assertEqual(600.0, normalize_queue_wait(10_000))


class _RecordingLLM:
    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.calls: list[Message] = []
        self.active = 0
        self.max_active = 0
        self.start_times: list[float] = []

    async def complete(self, messages, tools=None, system_prompt=None) -> LLMResponse:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.start_times.append(time.monotonic())
        try:
            await asyncio.sleep(self.delay)
            self.calls.extend(messages)
            return LLMResponse(content="ok", usage=_usage())
        finally:
            self.active -= 1


class ModelGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_unlimited_gate_passes_through_without_serialisation(self) -> None:
        gate = ModelGate(None)
        inner = _RecordingLLM(delay=0.05)
        backend = GatedLLM(inner, gate)
        message = [Message(role="user", content="hi")]

        self.assertTrue(gate.unlimited)
        await asyncio.gather(*(backend.complete(message) for _ in range(5)))

        self.assertGreaterEqual(inner.max_active, 2)
        self.assertEqual(5, len(inner.calls))

    async def test_concurrency_limit_one_serialises_calls(self) -> None:
        gate = ModelGate(1, queue_wait_seconds=10)
        inner = _RecordingLLM(delay=0.05)
        backend = GatedLLM(inner, gate)
        message = [Message(role="user", content="hi")]

        await asyncio.gather(*(backend.complete(message) for _ in range(4)))

        self.assertEqual(1, inner.max_active)
        self.assertEqual(4, len(inner.calls))
        self.assertFalse(gate.unlimited)

    async def test_queue_is_first_in_first_out(self) -> None:
        gate = ModelGate(1, queue_wait_seconds=10)
        inner = _RecordingLLM(delay=0.03)
        backend = GatedLLM(inner, gate)

        order: list[int] = []

        async def call(label: int) -> None:
            message = [Message(role="user", content=str(label))]
            await backend.complete(message)
            order.append(label)

        await asyncio.gather(*(call(index) for index in range(5)))

        self.assertEqual([0, 1, 2, 3, 4], order)

    async def test_queue_timeout_aborts_call_and_does_not_reach_inner(self) -> None:
        gate = ModelGate(1, queue_wait_seconds=1)
        inner = _RecordingLLM(delay=2.0)
        backend = GatedLLM(inner, gate)
        message = [Message(role="user", content="hi")]

        async def slow_call() -> None:
            await backend.complete(message)

        slow = asyncio.create_task(slow_call())
        await asyncio.sleep(0.05)
        with self.assertRaises(ModelQueueTimeoutError):
            await backend.complete(message)
        # 第二个调用在排队时超时，从未进入内层；第一个仍在运行。
        self.assertEqual(0, len(inner.calls))
        self.assertFalse(slow.done())
        await slow
        self.assertEqual(1, len(inner.calls))

    async def test_inner_error_still_releases_token(self) -> None:
        gate = ModelGate(1, queue_wait_seconds=5)

        class ExplodingInner:
            async def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
                raise RuntimeError("boom")

        backend = GatedLLM(ExplodingInner(), gate)
        message = [Message(role="user", content="hi")]
        with self.assertRaises(RuntimeError):
            await backend.complete(message)

        # 令牌已归还：下一次调用应当立即成功。
        healthy = _RecordingLLM(delay=0)
        backend = GatedLLM(healthy, gate)
        await backend.complete(message)
        self.assertEqual(1, len(healthy.calls))


class ServiceGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config = BridgeConfig(
            state_dir=root / "state", workspace=root, group_batch_seconds=0.0
        )
        self.service = BridgeService(self.config)
        self.service.state.data["interfaces"]["providers"] = [
            {
                "id": "prov-1",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-test",
                "model": "model-a",
                "max_concurrency": 2,
                "queue_wait_seconds": 30,
                "models": [
                    {"id": "model-a"},
                    {"id": "model-slow", "max_concurrency": 1, "queue_wait_seconds": 5},
                ],
            }
        ]
        self.service.state.data["accounts"] = [
            {
                "id": "test-bot",
                "platform": "test",
                "bot_id": "bot",
                "provider_id": "prov-1",
                "model": "model-a",
                "whitelist": [],
                "blacklist": [],
            }
        ]

    def test_effective_config_resolves_provider_defaults(self) -> None:
        runtime = self.service.effective_chat_config("test", "bot", "group", "room-1")
        self.assertEqual(2, runtime["max_concurrency"])
        self.assertEqual(30.0, runtime["queue_wait_seconds"])

    def test_effective_config_prefers_model_override(self) -> None:
        self.service.state.data["accounts"][0]["model"] = "model-slow"
        runtime = self.service.effective_chat_config("test", "bot", "group", "room-1")
        self.assertEqual(1, runtime["max_concurrency"])
        self.assertEqual(5.0, runtime["queue_wait_seconds"])

    def test_effective_config_honours_model_missing_concurrency(self) -> None:
        self.service.state.data["interfaces"]["providers"][0]["models"].append(
            {"id": "model-plain"}
        )
        self.service.state.data["accounts"][0]["model"] = "model-plain"
        runtime = self.service.effective_chat_config("test", "bot", "group", "room-1")
        self.assertEqual(2, runtime["max_concurrency"])
        self.assertEqual(30.0, runtime["queue_wait_seconds"])

    def test_model_gate_is_shared_by_base_url_and_model(self) -> None:
        first = self.service.model_gate(
            "https://api.example.com/v1", "model-a", max_concurrency=2
        )
        second = self.service.model_gate(
            "https://api.example.com/v1", "model-a", max_concurrency=2
        )
        other = self.service.model_gate(
            "https://api.example.com/v1", "model-b", max_concurrency=2
        )

        self.assertIs(first, second)
        self.assertIsNot(first, other)
        self.assertEqual(2, first.limit)

    def test_model_gate_recreates_on_limit_change(self) -> None:
        first = self.service.model_gate(
            "https://api.example.com/v1", "model-a", max_concurrency=2
        )
        replaced = self.service.model_gate(
            "https://api.example.com/v1", "model-a", max_concurrency=4
        )
        self.assertIsNot(first, replaced)
        self.assertEqual(4, replaced.limit)

    def test_unlimited_concurrency_returns_passthrough_gate(self) -> None:
        gate = self.service.model_gate(
            "https://api.example.com/v1", "model-a", max_concurrency=None
        )
        self.assertTrue(gate.unlimited)


class BridgeIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config = BridgeConfig(
            state_dir=root / "state", workspace=root, group_batch_seconds=0.0
        )
        self.service = BridgeService(self.config)
        self.service.state.data["accounts"] = [
            {
                "id": "test-bot",
                "platform": "test",
                "bot_id": "bot",
                "provider_id": "",
                "model": "",
                "whitelist": [{"id": "room-1", "kind": "group"}],
                "blacklist": [],
            }
        ]
        self.service.state.data["groups"] = [
            {
                "id": "group-1",
                "platform": "test",
                "bot_id": "bot",
                "group_id": "room-1",
                "enabled": True,
                "reply_probability": 1.0,
            }
        ]

    def _incoming(self) -> IncomingMessage:
        return IncomingMessage(
            bot=None,
            platform="test",
            bot_id="bot",
            kind="group",
            peer_id="room-1",
            user_id="member",
            user_name="群友",
            text="hi",
            target=Target("room-1"),
        )

    async def test_process_message_catches_queue_timeout(self) -> None:
        from plugin_chatbot.bridge.concurrency import ModelQueueTimeoutError

        class TimeoutAgent:
            _llm = None

            async def run(self, *args: Any, **kwargs: Any) -> AgentResult:
                raise ModelQueueTimeoutError(1.0)

        self.service.state.data["conversations"] = {}
        _key, _chat_id = self.service.resolve_chat("test", "bot", "group", "room-1")
        with patch.object(self.service, "_agent", return_value=TimeoutAgent()):
            result = await self.service._process_message(self._incoming())
        self.assertEqual("", result)
        self.assertTrue(
            any(
                "并发排队超时" in row["text"]
                for row in self.service.state.data["activity"]
            )
        )


if __name__ == "__main__":
    unittest.main()
