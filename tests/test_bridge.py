"""Safety and persistence tests for the cross-platform bridge service."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

from nonebot_plugin_alconna import Target

from agent.llm import LLMClient
from agent.tool import ToolContext
from plugin_chatbot.bridge.service import (
    BridgeConfig,
    BridgeService,
    IncomingMessage,
    audit_reply,
    conversation_key,
    sender_context,
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

    def test_private_target_id_can_identify_owner(self) -> None:
        self.service.config.owner_ids = {"qq-private-openid"}
        self.assertTrue(
            self.service.is_admin("different-event-openid", "qq-private-openid")
        )
        self.assertTrue(
            self.service.is_allowed(
                "private", "qq-private-openid", "different-event-openid"
            )
        )
        key, chat_id = self.service.resolve_chat(
            "qq", "bot", "private", "qq-private-openid"
        )
        self.assertEqual(
            "已进入静默模式。",
            self.service.command(
                "different-event-openid",
                "/silent",
                key,
                chat_id,
                peer_id="qq-private-openid",
            ),
        )

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

    def test_outbound_rate_limit_is_per_conversation_and_persists(self) -> None:
        self.service.config.max_messages_per_minute = 2
        self.assertTrue(self.service.reserve_outbound("group-a", now=100))
        self.assertTrue(self.service.reserve_outbound("group-a", now=100))
        self.assertFalse(self.service.reserve_outbound("group-a", now=100))
        self.assertTrue(self.service.reserve_outbound("group-b", now=100))

        restored = BridgeService(self.service.config)
        self.assertFalse(restored.reserve_outbound("group-a", now=100))
        self.assertTrue(restored.reserve_outbound("group-a", now=160.01))

    def test_sender_context_includes_group_and_speaker_ids(self) -> None:
        incoming = IncomingMessage(
            bot=None,
            platform="QQ",
            bot_id="bot",
            kind="group",
            peer_id="group-openid",
            user_id="member-openid",
            user_name="Alice Example",
            text="hello",
            target=Target("group-openid"),
            reply_to="message-1",
            group_name="Research Group",
        )
        context = sender_context(incoming)
        self.assertIn("group_openid=group-openid", context)
        self.assertIn("user_id=member-openid", context)
        self.assertIn('group_name="Research Group"', context)
        self.assertIn('user_nickname="Alice Example"', context)
        self.assertIn("\n[member-openid]", context)
        self.assertIn("引用: message-1", context)

    def test_bridge_agent_system_prompt_explains_group_and_sender_metadata(self) -> None:
        key, chat_id = self.service.resolve_chat("test", "bot", "group", "room-1")
        agent = self.service._agent(key, chat_id, owner=False)
        prompt = agent._build_system_prompt()
        self.assertIn("`user_id` 始终是当前发言用户", prompt)
        self.assertIn("`group_openid` 是群标识，不是发言用户标识", prompt)
        self.assertIn("逐条区分用户", prompt)

    def test_group_messages_in_batch_share_one_agent_request(self) -> None:
        async def run_test() -> None:
            self.service.config.group_batch_seconds = 0.01
            process = AsyncMock(return_value="one grouped reply")
            self.service._process_message = process

            def incoming(user_id: str, text: str) -> IncomingMessage:
                return IncomingMessage(
                    bot=None,
                    platform="QQ",
                    bot_id="bot",
                    kind="group",
                    peer_id="group-openid",
                    user_id=user_id,
                    user_name=user_id,
                    text=text,
                    target=Target("group-openid"),
                    event_id=f"event-{user_id}",
                )

            first, second = await asyncio.gather(
                self.service.handle_message(incoming("member-1", "hello")),
                self.service.handle_message(incoming("member-2", "world")),
            )

            self.assertEqual(1, process.await_count)
            self.assertCountEqual(["one grouped reply", ""], [first, second])
            call = process.await_args
            if call is None:
                self.fail("Agent processing was not called")
            combined = call.args[0]
            self.assertTrue(combined.preformatted)
            self.assertIn("user_id=member-1", combined.text)
            self.assertIn("user_id=member-2", combined.text)
            self.assertIn("group_openid=group-openid", combined.text)

        asyncio.run(run_test())

    def test_sensitive_output_is_blocked(self) -> None:
        self.assertIsNotNone(audit_reply("api_key=topsecret"))
        self.assertIsNotNone(audit_reply("open C:\\Users\\alice\\private.txt"))
        self.assertIsNotNone(audit_reply("open D:\\workspace\\private.txt"))
        self.assertIsNone(audit_reply("普通聊天内容"))

    def test_chat_tools_are_allowlisted_by_agent_permissions(self) -> None:
        self.service.config.reasoning_effort = "high"
        key, chat_id = self.service.resolve_chat("test", "bot", "private", "friend-1")
        agent = self.service._agent(key, chat_id, owner=False)
        send_tool = next(tool for tool in agent._tools if tool.name == "chat_send")
        memory_read = next(
            tool for tool in agent._tools if tool.name == "ProjectMemoryRead"
        )
        memory_write = next(
            tool for tool in agent._tools if tool.name == "ProjectMemoryWrite"
        )
        self.assertEqual("allow", agent._check_permission(send_tool, {"text": "hi"}))
        self.assertEqual("allow", agent._check_permission(memory_read, {}))
        self.assertEqual("deny", agent._check_permission(memory_write, {}))

        same_agent = self.service._agent(key, chat_id, owner=True)

        self.assertIs(agent, same_agent)
        self.assertEqual("allow", agent._check_permission(memory_write, {}))
        llm = agent._llm
        if not isinstance(llm, LLMClient):
            self.fail("Bridge did not create an LLMClient")
        self.assertEqual("high", llm.reasoning_effort)

    def test_session_tools_persist_apply_and_reset_when_mode_changes(self) -> None:
        key, chat_id = self.service.resolve_chat("test", "bot", "group", "room-1")
        defaults = self.service.session_tool_config(key)
        self.assertIn("chat_current_datetime", defaults["enabled"])
        self.assertIn("ProjectMemoryRead", defaults["enabled"])

        agent = self.service._agent(key, chat_id, owner=False)
        self.service.set_session_tools(key, ["chat_status", "chat_current_datetime"])
        updated_agent = self.service._agent(key, chat_id, owner=False)
        self.assertIs(agent, updated_agent)
        self.assertEqual(
            {"chat_status", "chat_current_datetime"},
            {tool.name for tool in agent._tools},
        )

        restored = BridgeService(self.service.config)
        self.assertCountEqual(
            ["chat_current_datetime", "chat_status"],
            restored.session_tool_config(key)["enabled"],
        )
        restored.set_mode("reserved")
        self.assertNotIn("enabled_tools", restored.state.data["conversations"][key])
        reset_config = restored.session_tool_config(key)
        self.assertIn("chat_current_datetime", reset_config["enabled"])
        self.assertIn("chat_send", reset_config["enabled"])

    def test_mode_defaults_change_available_tools_for_owner_session(self) -> None:
        key, _chat_id = self.service.resolve_chat("test", "bot", "private", "owner")
        self.service.set_mode("closed-agent")
        tools = self.service.session_tool_config(key)
        self.assertIn("Bash", tools["enabled"])
        self.assertIn("chat_current_datetime", tools["enabled"])

        self.service.set_session_tools(key, ["chat_current_datetime"])
        self.service.set_mode("chat")
        self.assertNotIn("enabled_tools", self.service.state.data["conversations"][key])
        defaults = self.service.session_tool_config(key)
        self.assertNotIn("Bash", defaults["enabled"])
        self.assertIn("chat_send", defaults["enabled"])

    def test_current_datetime_tool_returns_local_timezone_and_iso_timestamp(self) -> None:
        key, _chat_id = self.service.resolve_chat("test", "bot", "group", "room-1")
        tool = next(
            tool
            for tool in self.service.chat_tools(key)
            if tool.name == "chat_current_datetime"
        )
        result = asyncio.run(
            tool.call({}, ToolContext(workspace=self.temp.name))
        )
        payload = json.loads(result)
        parsed = datetime.fromisoformat(payload["datetime"])
        self.assertIsNotNone(parsed.tzinfo)
        self.assertTrue(payload["timezone"])

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
