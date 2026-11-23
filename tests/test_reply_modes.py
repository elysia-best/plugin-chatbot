"""群聊仅 @ 回复模式：触发条件、概率失效与指令兼容的回归测试。"""

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
    DEFAULT_REPLY_MODE,
    BridgeConfig,
    BridgeService,
    IncomingMessage,
    normalize_reply_mode,
)


class _RecordingAgent:
    def __init__(self) -> None:
        self.prompts: list[Any] = []
        self._llm = None

    async def run(self, prompt, chat_id=None) -> AgentResult:
        self.prompts.append(prompt)
        return AgentResult(text="ok", messages=[], tool_calls=[], usage=Usage())


def _incoming(text: str, *, user_id: str = "member", mentions_bot: bool = False) -> IncomingMessage:
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
        mentions_bot=mentions_bot,
    )


class NormalizeReplyModeTests(unittest.TestCase):
    def test_accepts_known_modes(self) -> None:
        self.assertEqual("probability", normalize_reply_mode("probability"))
        self.assertEqual("mention_only", normalize_reply_mode("mention_only"))
        self.assertEqual("mention_only", normalize_reply_mode(" Mention_Only "))

    def test_rejects_unknown_values(self) -> None:
        for value in ("", None, "always", 42, "silent"):
            with self.subTest(value=value):
                self.assertEqual(DEFAULT_REPLY_MODE, normalize_reply_mode(value))


class MentionOnlyReplyTests(unittest.TestCase):
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
            "reply_mode": "mention_only",
            "reply_probability": 1.0,
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

    def test_mention_triggers_model_and_flushes_buffer(self) -> None:
        self.assertEqual("", self._handle(_incoming("闲聊一")))
        self.assertEqual("", self._handle(_incoming("闲聊二")))
        self.assertEqual([], self.agent.prompts)
        self.assertEqual(2, len(self.service.state.data["pending_messages"][self.key]))

        self._handle(_incoming("@在吗", mentions_bot=True))

        text = self._prompt_text()
        self.assertIn("闲聊一", text)
        self.assertIn("闲聊二", text)
        self.assertIn("@我", text)
        self.assertIn("@在吗", text)
        self.assertEqual({}, self.service.state.data["pending_messages"])

    def test_probability_zero_is_ignored_in_mention_only_mode(self) -> None:
        self._set_probability(0.0)
        self._handle(_incoming("被忽略", mentions_bot=True))

        self.assertEqual(1, len(self.agent.prompts))
        self.assertEqual({}, self.service.state.data["pending_messages"])

    def test_non_mention_messages_do_not_reach_the_model(self) -> None:
        self._set_probability(0.0)
        for index in range(5):
            self._handle(_incoming(f"未提及 {index}"))

        self.assertEqual([], self.agent.prompts)
        self.assertEqual(5, len(self.service.state.data["pending_messages"][self.key]))

    def test_commands_bypass_mention_only_gate(self) -> None:
        self._set_probability(0.0)
        result = self._handle(_incoming("/status"))

        self.assertIn("仅 @", result)
        self.assertEqual([], self.agent.prompts)

    def test_reply_command_reports_ineffective_probability(self) -> None:
        _key, chat_id = self.service.resolve_chat("test", "bot", "group", "room-1")
        self.assertEqual(
            "当前为仅 @ 模式，回复概率不生效。",
            self.service.command("owner", "/reply 0.5", self.key, chat_id),
        )
        self.assertEqual(
            "当前为仅 @ 模式，回复概率不生效。",
            self.service.command("owner", "/reply", self.key, chat_id),
        )
        # 设置被拒绝，但概率本身仍保持原值。
        group = self.service.group_config("test", "bot", "room-1")
        assert group is not None
        self.assertEqual(1.0, group["reply_probability"])

    def test_chat_status_reports_both_mode_and_probability(self) -> None:
        tool = next(
            tool
            for tool in self.service.chat_tools(self.key)
            if tool.name == "chat_status"
        )
        payload = json.loads(
            asyncio.run(
                tool.call({}, ToolContext(workspace=self.temp.name))
            )
        )
        self.assertEqual("mention_only", payload["reply_mode"])
        self.assertAlmostEqual(1.0, payload["reply_probability"])


if __name__ == "__main__":
    unittest.main()
