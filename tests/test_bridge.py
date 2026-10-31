"""Safety and persistence tests for the cross-platform bridge service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugin_chatbot.bridge.service import (
    BridgeConfig,
    BridgeService,
    audit_reply,
    conversation_key,
    split_message,
)


class BridgeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.service = BridgeService(
            BridgeConfig(
                state_dir=root / "state",
                workspace=root,
                owner_ids={"owner"},
                allowed_groups={"room-1"},
                allowed_private={"friend-1"},
            )
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_conversation_key_is_stable_and_scoped(self) -> None:
        key = conversation_key("Example", "bot", "group", "42")
        self.assertEqual(key, conversation_key("example", "bot", "group", "42"))
        self.assertNotEqual(
            key, conversation_key("example", "other-bot", "group", "42")
        )
        self.assertNotEqual(key, conversation_key("example", "bot", "private", "42"))

    def test_allowlist_defaults_to_deny_and_owner_bypasses(self) -> None:
        self.assertTrue(self.service.is_allowed("group", "room-1", "member"))
        self.assertFalse(self.service.is_allowed("group", "room-2", "member"))
        self.assertTrue(self.service.is_allowed("group", "room-2", "owner"))

    def test_mapping_survives_restart(self) -> None:
        first, chat_id = self.service.resolve_chat("satori", "bot", "group", "room")
        second_service = BridgeService(self.service.config)
        second, restored_chat = second_service.resolve_chat(
            "satori", "bot", "group", "room"
        )
        self.assertEqual(first, second)
        self.assertEqual(chat_id, restored_chat)

    def test_slang_settings_survive_restart_and_are_bounded(self) -> None:
        self.service.config.slang_enabled = False
        self.service.config.slang_min_messages = 12
        self.service.config.slang_cooldown_seconds = 900
        self.service.state.data["slang_settings"] = {
            "enabled": False,
            "min_messages": 12,
            "cooldown_seconds": 900,
        }
        self.service.state.save()

        restored = BridgeService(self.service.config)

        self.assertFalse(restored.config.slang_enabled)
        self.assertEqual(12, restored.config.slang_min_messages)
        self.assertEqual(900, restored.config.slang_cooldown_seconds)

        restored.state.data["slang_settings"] = {
            "enabled": True,
            "min_messages": "invalid",
            "cooldown_seconds": -1,
        }
        restored.state.save()
        bounded = BridgeService(restored.config)
        self.assertEqual(12, bounded.config.slang_min_messages)
        self.assertEqual(30, bounded.config.slang_cooldown_seconds)

    def test_split_message_keeps_all_text(self) -> None:
        text = "one two three four five six"
        parts = split_message(text, 9)
        self.assertTrue(all(len(part) <= 9 for part in parts))
        self.assertEqual(" ".join(parts), text)

    def test_sensitive_output_is_blocked(self) -> None:
        self.assertIsNotNone(audit_reply("api_key=topsecret"))
        self.assertIsNotNone(audit_reply("open C:\\Users\\alice\\private.txt"))
        self.assertIsNotNone(audit_reply("open D:\\workspace\\private.txt"))
        self.assertIsNone(audit_reply("普通聊天内容"))

    def test_chat_tools_are_allowlisted_by_agent_permissions(self) -> None:
        key, chat_id = self.service.resolve_chat("test", "bot", "private", "friend-1")
        agent = self.service._agent(key, chat_id, owner=False)
        send_tool = next(tool for tool in agent._tools if tool.name == "chat_send")
        self.assertEqual("allow", agent._check_permission(send_tool, {"text": "hi"}))

    def test_command_permissions_and_modes(self) -> None:
        key, chat_id = self.service.resolve_chat("test", "bot", "private", "owner")
        self.assertEqual(
            "无权执行管理命令。",
            self.service.command("member", "/silent", key, chat_id),
        )
        self.assertEqual(
            "已进入静默模式。", self.service.command("owner", "/silent", key, chat_id)
        )
        self.assertTrue(self.service.state.data["silent"])
        result = self.service.command("member", "/reset", key, chat_id)
        self.assertIsNotNone(result)
        self.assertIn("当前会话上下文已重置", result or "")


if __name__ == "__main__":
    unittest.main()
