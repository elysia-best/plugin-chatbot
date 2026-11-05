"""群聊概率回复：配置校验、消息暂存、时间戳注入与超长截断的回归测试。"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from nonebot_plugin_alconna import Target

from agent import AgentResult, ToolContext, Usage
from plugin_chatbot.bridge.service import (
    DEFAULT_REPLY_PROBABILITY,
    PENDING_RECENT_LIMIT,
    BridgeConfig,
    BridgeService,
    IncomingMessage,
    normalize_probability,
)

TIMESTAMP_PATTERN = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"


class _RecordingAgent:
    """记录每轮交给模型的 prompt，不发起真实模型请求。"""

    def __init__(self) -> None:
        self.prompts: list[Any] = []
        self._llm = None

    async def run(self, prompt, chat_id=None) -> AgentResult:
        self.prompts.append(prompt)
        return AgentResult(text="", messages=[], tool_calls=[], usage=Usage())


def _incoming(text: str, *, user_id: str = "member", content=None) -> IncomingMessage:
    return IncomingMessage(
        bot=None,
        platform="test",
        bot_id="bot",
        kind="group",
        peer_id="room-1",
        user_id=user_id,
        user_name="群友" if user_id == "member" else "Owner",
        text=text,
        target=Target("room-1"),
        content=content,
    )


class ProbabilityConfigTests(unittest.TestCase):
    def test_normalize_probability_accepts_in_range_values(self) -> None:
        for value, expected in (
            (0, 0.0),
            (1, 1.0),
            (0.25, 0.25),
            ("0.3", 0.3),
            (True, 1.0),
        ):
            with self.subTest(value=value):
                parsed = normalize_probability(value)
                assert parsed is not None
                self.assertAlmostEqual(expected, parsed)

    def test_normalize_probability_rejects_invalid_values(self) -> None:
        for value in (-0.1, 1.1, 2, "abc", "", None, float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assertIsNone(normalize_probability(value))


class ProbabilityReplyTests(unittest.TestCase):
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
                "admins": [{"id": "owner", "kind": "private"}],
                "whitelist": [{"id": "room-1", "kind": "group"}],
                "blacklist": [],
                "private_users": [],
            }
        ]
        self.group = {
            "id": "group-1",
            "platform": "test",
            "bot_id": "bot",
            "group_id": "room-1",
            "enabled": True,
            "reply_probability": DEFAULT_REPLY_PROBABILITY,
        }
        self.service.state.data["groups"] = [self.group]
        self.key, _chat_id = self.service.resolve_chat("test", "bot", "group", "room-1")
        self.agent = _RecordingAgent()

    def _set_probability(self, value: float) -> None:
        self.group["reply_probability"] = value
        self.service.state.save()

    def _handle(self, incoming: IncomingMessage) -> str:
        with patch.object(self.service, "_agent", return_value=self.agent):
            return asyncio.run(self.service.handle_message(incoming))

    def _prompt_text(self) -> str:
        self.assertEqual(1, len(self.agent.prompts))
        prompt = self.agent.prompts[0]
        if isinstance(prompt, str):
            return prompt
        self.assertIsInstance(prompt, list)
        return str(prompt[0]["text"])

    def test_probability_one_keeps_default_behaviour_without_timestamps(self) -> None:
        self._set_probability(1.0)

        self._handle(_incoming("早上好"))

        text = self._prompt_text()
        self.assertIn("早上好", text)
        self.assertNotIn("[20", text)
        self.assertEqual({}, self.service.state.data["pending_messages"])

    def test_probability_zero_buffers_messages_without_calling_model(self) -> None:
        self._set_probability(0.0)

        for text in ("第一条", "第二条", "第三条"):
            self.assertEqual("", self._handle(_incoming(text)))

        self.assertEqual([], self.agent.prompts)
        rows = self.service.state.data["pending_messages"][self.key]
        self.assertEqual(3, len(rows))
        self.assertEqual(
            ["群友：第一条", "群友：第二条", "群友：第三条"],
            [row["text"] for row in rows],
        )
        for row in rows:
            self.assertRegex(row["at"], f"^{TIMESTAMP_PATTERN}$")

    def test_duplicate_event_is_not_buffered_twice(self) -> None:
        self._set_probability(0.0)
        for _ in range(2):
            duplicate = _incoming("重复消息")
            duplicate.event_id = "evt-1"
            self._handle(duplicate)

        self.assertEqual(1, len(self.service.state.data["pending_messages"][self.key]))

    def test_buffered_messages_are_delivered_with_timestamps_on_hit(self) -> None:
        self._set_probability(0.5)
        with patch(
            "plugin_chatbot.bridge.service.random.random", side_effect=[0.9, 0.9, 0.1]
        ):
            self._handle(_incoming("第一条"))
            self._handle(_incoming("第二条"))
            self._handle(_incoming("第三条"))

        text = self._prompt_text()
        lines = text.splitlines()
        self.assertEqual(3, len(lines))
        for line, expected in zip(lines, ("第一条", "第二条", "第三条")):
            self.assertRegex(line, r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]")
            self.assertIn(expected, line)
        self.assertEqual({}, self.service.state.data["pending_messages"])

    def test_administrator_has_no_probability_exemption(self) -> None:
        self._set_probability(0.5)
        with patch("plugin_chatbot.bridge.service.random.random", return_value=0.9):
            self._handle(_incoming("管理员未命中", user_id="owner"))

        self.assertEqual([], self.agent.prompts)
        self.assertEqual(1, len(self.service.state.data["pending_messages"][self.key]))

        with patch("plugin_chatbot.bridge.service.random.random", return_value=0.1):
            self._handle(_incoming("普通成员命中"))

        text = self._prompt_text()
        self.assertIn("管理员未命中", text)
        self.assertIn("普通成员命中", text)
        self.assertEqual({}, self.service.state.data["pending_messages"])

    def test_probability_zero_buffers_even_administrator_messages(self) -> None:
        self._set_probability(0.0)

        self.assertEqual("", self._handle(_incoming("管理员消息", user_id="owner")))

        self.assertEqual([], self.agent.prompts)
        self.assertEqual(1, len(self.service.state.data["pending_messages"][self.key]))

    def test_long_buffer_only_sends_three_most_recent_messages(self) -> None:
        self._set_probability(0.5)
        long_text = "内容" * 450
        with patch(
            "plugin_chatbot.bridge.service.random.random",
            side_effect=[0.9] * 5 + [0.1],
        ):
            for index in range(5):
                self._handle(_incoming(f"第{index}条-{long_text}"))
            self._handle(_incoming(f"最新-{long_text}"))

        text = self._prompt_text()
        lines = text.splitlines()
        self.assertEqual(PENDING_RECENT_LIMIT, len(lines))
        self.assertIn("最新-", lines[-1])
        self.assertNotIn("第0条-", text)
        self.assertNotIn("第1条-", text)

    def test_hit_message_preserves_image_blocks(self) -> None:
        self._set_probability(0.5)
        image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}
        with patch("plugin_chatbot.bridge.service.random.random", return_value=0.1):
            self._handle(_incoming("看图", content=[image]))

        prompt = self.agent.prompts[0]
        self.assertIn(image, prompt)
        self.assertIn("看图", str(prompt[0]["text"]))

    def test_failed_model_run_does_not_rebuffer_messages(self) -> None:
        self._set_probability(0.5)

        class FailingAgent(_RecordingAgent):
            async def run(self, prompt, chat_id=None) -> AgentResult:
                await super().run(prompt, chat_id)
                return AgentResult(
                    text="",
                    messages=[],
                    tool_calls=[],
                    usage=Usage(),
                    status="error",
                    error="model unavailable",
                )

        failing = FailingAgent()
        with patch.object(self.service, "_agent", return_value=failing):
            with patch("plugin_chatbot.bridge.service.random.random", return_value=0.1):
                asyncio.run(self.service.handle_message(_incoming("已投递")))
                asyncio.run(self.service.handle_message(_incoming("下一轮")))

        self.assertEqual({}, self.service.state.data["pending_messages"])
        self.assertEqual(2, len(failing.prompts))
        for prompt in failing.prompts:
            first = prompt[0]["text"] if isinstance(prompt, list) else prompt
            self.assertEqual(1, len(first.splitlines()))

    def test_consecutive_hits_never_redeliver_earlier_messages(self) -> None:
        self._set_probability(0.5)
        with patch("plugin_chatbot.bridge.service.random.random", return_value=0.1):
            for text in ("第一条", "第二条", "第三条"):
                self._handle(_incoming(text))

        self.assertEqual(3, len(self.agent.prompts))
        for prompt, own in zip(
            self.agent.prompts, ("第一条", "第二条", "第三条")
        ):
            block = prompt[0]["text"] if isinstance(prompt, list) else prompt
            lines = block.splitlines()
            self.assertEqual(1, len(lines))
            self.assertIn(own, lines[0])

    def test_duplicate_event_after_flush_is_not_rebuffered(self) -> None:
        self._set_probability(0.5)
        incoming = _incoming("只处理一次")
        incoming.event_id = "evt-flush"
        with patch("plugin_chatbot.bridge.service.random.random", return_value=0.1):
            self._handle(incoming)
            self._handle(incoming)

        self.assertEqual(1, len(self.agent.prompts))
        self.assertEqual({}, self.service.state.data["pending_messages"])

    def test_rejected_conversation_clears_buffer(self) -> None:
        self._set_probability(0.0)
        self._handle(_incoming("停止前"))
        self.assertEqual(1, len(self.service.state.data["pending_messages"][self.key]))

        self.service.state.data["conversations"][self.key]["status"] = "rejected"
        self._set_probability(0.5)
        with patch("plugin_chatbot.bridge.service.random.random", return_value=0.1):
            self._handle(_incoming("停止中"))

        self.assertEqual({}, self.service.state.data["pending_messages"])
        self.assertEqual([], self.agent.prompts)

    def test_chat_status_reports_probability_instead_of_silent(self) -> None:
        self._set_probability(0.25)
        tool = next(
            tool
            for tool in self.service.chat_tools(self.key)
            if tool.name == "chat_status"
        )
        payload = json.loads(
            asyncio.run(tool.call({}, ToolContext(workspace=self.temp.name)))
        )

        self.assertAlmostEqual(0.25, payload["reply_probability"])
        self.assertNotIn("silent", payload)

    def test_reply_command_sets_reports_and_rejects_invalid_values(self) -> None:
        _key, chat_id = self.service.resolve_chat("test", "bot", "group", "room-1")

        self.assertEqual(
            "回复概率已设为 0.25。",
            self.service.command("owner", "/reply 0.25", self.key, chat_id),
        )
        self.assertEqual(
            "当前回复概率：0.25",
            self.service.command("owner", "/reply", self.key, chat_id),
        )
        self.assertEqual(
            "用法：/reply 0~1（0 永不回复，1 一直回复）",
            self.service.command("owner", "/reply 2", self.key, chat_id),
        )
        self.assertAlmostEqual(0.25, self.service.reply_probability_for_key(self.key))

    def test_legacy_silent_state_and_frequency_field_are_migrated(self) -> None:
        self.group.pop("reply_probability")
        self.group["reply_frequency"] = "quiet"
        self.service.state.data["silent"] = True
        self.service.state.save()

        restored = BridgeService(self.config)

        self.assertNotIn("silent", restored.state.data)
        self.assertEqual({}, restored.state.data["pending_messages"])
        migrated = restored.group_config("test", "bot", "room-1")
        assert migrated is not None
        self.assertEqual(DEFAULT_REPLY_PROBABILITY, migrated["reply_probability"])
        self.assertNotIn("reply_frequency", migrated)


if __name__ == "__main__":
    unittest.main()
