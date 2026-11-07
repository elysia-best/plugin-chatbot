"""Safety and persistence tests for the cross-platform bridge service."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from nonebot_plugin_alconna import Target

from agent.llm import LLMClient
from agent.messages import Message
from agent.tool import ToolContext
from plugin_chatbot.bridge.service import (
    BridgeConfig,
    BridgeService,
    BridgeState,
    IncomingMessage,
    audit_reply,
    conversation_key,
    extract_context_length,
    is_silent_reply,
    normalize_model_records,
    sender_context,
    split_message,
    strip_think_blocks,
)


class BridgeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.service = BridgeService(
            BridgeConfig(
                state_dir=root / "state",
                workspace=root,
            )
        )
        self.service.state.data["accounts"] = [
            {
                "id": "test-bot",
                "platform": "test",
                "bot_id": "bot",
                "admins": [{"id": "owner", "kind": "private", "name": "Owner"}],
                "whitelist": [
                    {"id": "room-1", "kind": "group", "name": "Room 1"},
                    {"id": "friend-1", "kind": "private", "name": "Friend 1"},
                ],
                "blacklist": [],
                "private_users": [],
            }
        ]
        self.service.state.save()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_legacy_modes_migrate_to_chat_or_agent_and_drop_simulation_state(self) -> None:
        root = Path(self.temp.name) / "legacy-state"
        root.mkdir()
        state_path = root / "bridge-state.json"
        state_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "mode": "closed-agent",
                    "simulation_prompts": {"chat": "old prompt"},
                    "wake": {"conversation": {"after": 0}},
                }
            ),
            encoding="utf-8",
        )

        state = BridgeState(root)

        self.assertEqual("agent", state.data["mode"])
        self.assertNotIn("simulation_prompts", state.data)
        self.assertNotIn("wake", state.data)

    def test_conversation_key_is_stable_and_scoped(self) -> None:
        key = conversation_key("Example", "bot", "group", "42")
        self.assertEqual(key, conversation_key("example", "bot", "group", "42"))
        self.assertNotEqual(
            key, conversation_key("example", "other-bot", "group", "42")
        )
        self.assertNotEqual(key, conversation_key("example", "bot", "private", "42"))

    def test_allowlist_defaults_to_deny_and_owner_bypasses(self) -> None:
        self.assertTrue(self.service.is_allowed("group", "room-1", "member", "test", "bot"))
        self.assertFalse(self.service.is_allowed("group", "room-2", "member", "test", "bot"))
        self.assertTrue(self.service.is_allowed("group", "room-2", "owner", "test", "bot"))

    def test_group_member_admin_does_not_grant_webui_admin_access(self) -> None:
        incoming = IncomingMessage(
            bot=None,
            platform="test",
            bot_id="bot",
            kind="group",
            peer_id="unlisted-room",
            user_id="group-admin",
            user_name="Group Admin",
            text="hello",
            target=Target("unlisted-room"),
            group_member_is_admin=True,
        )

        self.assertFalse(
            self.service.is_admin(
                incoming.user_id, None, incoming.platform, incoming.bot_id
            )
        )
        self.assertTrue(self.service.is_admin("owner", None, "test", "bot"))
        self.assertFalse(
            self.service.is_allowed(
                incoming.kind,
                incoming.peer_id,
                incoming.user_id,
                incoming.platform,
                incoming.bot_id,
            )
        )
        self.assertEqual("【管理员】Group Admin：", sender_context(incoming))

    def test_private_target_id_can_identify_owner(self) -> None:
        self.service.state.data["accounts"].append(
            {
                "id": "qq-bot",
                "platform": "qq",
                "bot_id": "bot",
                "admins": [{"id": "qq-private-openid", "kind": "private"}],
                "whitelist": [],
                "blacklist": [],
            }
        )
        self.assertTrue(
            self.service.is_admin("different-event-openid", "qq-private-openid", "qq", "bot")
        )
        self.assertTrue(
            self.service.is_allowed(
                "private", "qq-private-openid", "different-event-openid", "qq", "bot"
            )
        )
        key, chat_id = self.service.resolve_chat(
            "qq", "bot", "private", "qq-private-openid"
        )
        self.assertEqual(
            "当前没有待审批操作。",
            self.service.command(
                "different-event-openid",
                "/approve yes",
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

    def test_pending_approval_rejection_and_account_isolation(self) -> None:
        key, _chat_id = self.service.resolve_chat("test", "bot", "group", "new-room")
        self.assertEqual("pending", self.service.state.data["conversations"][key]["status"])
        self.assertFalse(self.service.is_allowed("group", "new-room", "member", "test", "bot"))

        self.service.set_conversation_status(key, "approved")
        self.assertTrue(self.service.is_allowed("group", "new-room", "member", "test", "bot"))
        self.assertFalse(self.service.is_allowed("group", "new-room", "member", "test", "other"))

        self.service.set_conversation_status(key, "rejected")
        self.assertFalse(self.service.is_allowed("group", "new-room", "member", "test", "bot"))
        self.assertNotIn(
            "new-room",
            self.service._access_ids(
                self.service.state.data["accounts"][0]["whitelist"], "group"
            ),
        )
        self.service.set_conversation_status(key, "approved")
        restored = BridgeService(self.service.config)
        self.assertEqual("approved", restored.state.data["conversations"][key]["status"])
        self.assertTrue(restored.is_allowed("group", "new-room", "member", "test", "bot"))
        self.assertNotIn("new-room", restored._access_ids(restored.state.data["accounts"][0]["blacklist"], "group"))

    def test_unlisted_private_user_is_recorded_without_agent_reply(self) -> None:
        incoming = IncomingMessage(
            bot=None,
            platform="test",
            bot_id="bot",
            kind="private",
            peer_id="target-openid",
            user_id="user-openid",
            user_name="Visitor",
            text="hello",
            target=Target("target-openid"),
        )
        self.assertEqual("", asyncio.run(self.service._process_message(incoming)))
        key = conversation_key("test", "bot", "private", "target-openid")
        self.assertEqual("pending", self.service.state.data["conversations"][key]["status"])
        self.assertEqual("user-openid", self.service.state.data["conversations"][key]["user_id"])
        self.assertEqual(
            {"id": "user-openid", "name": "Visitor"},
            self.service.state.data["accounts"][0]["private_users"][0],
        )

    def test_memory_summary_is_queued_after_configured_inbound_message_count(self) -> None:
        class SummaryLLM:
            async def complete(self, messages, tools=None, system_prompt=None):
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "title": "沟通偏好",
                            "description": "用户希望回答简洁",
                            "type": "user",
                            "content": "用户希望回答简洁。",
                        },
                        ensure_ascii=False,
                    )
                )

        account = self.service.state.data["accounts"][0]
        account["memory_enabled"] = True
        account["memory_interval"] = 2
        incoming = IncomingMessage(
            bot=None,
            platform="test",
            bot_id="bot",
            kind="private",
            peer_id="friend-1",
            user_id="friend-1",
            user_name="Visitor",
            text="请回答简洁一些",
            target=Target("friend-1"),
        )

        async def exercise() -> None:
            await self.service._record_memory_exchange(
                account, incoming, "好的。", SummaryLLM()
            )
            self.assertEqual([], self.service.state.data["memory_queue"])
            restored = BridgeService(self.service.config)
            self.assertEqual(1, len(restored.state.data["accounts"][0]["memory_buffer"]))
            await self.service._record_memory_exchange(
                account, incoming, "我会简洁回答。", SummaryLLM()
            )
            await asyncio.gather(*list(self.service.memory_tasks))

        asyncio.run(exercise())

        self.assertEqual(1, len(self.service.state.data["memory_queue"]))
        candidate = self.service.state.data["memory_queue"][0]
        self.assertEqual("test-bot", candidate["account_id"])
        self.assertEqual("pending", candidate["status"])
        self.assertEqual(2, candidate["source_messages"])
        self.assertEqual([], account["memory_buffer"])

    def test_bot_memory_stores_are_isolated_per_account(self) -> None:
        first = self.service.state.data["accounts"][0]
        second = {"id": "other-bot", "platform": "test", "bot_id": "other"}
        first_store = self.service.bot_memory_store(first)
        second_store = self.service.bot_memory_store(second)
        first_store.save("one", "First", "First bot memory", "project", "Only bot one")

        self.assertEqual(["one"], [row["name"] for row in first_store.list()])
        self.assertEqual([], second_store.list())

    def test_clearing_one_conversation_persists_and_keeps_other(self) -> None:
        first, first_chat = self.service.resolve_chat("test", "bot", "group", "room-1")
        _second, second_chat = self.service.resolve_chat("test", "bot", "private", "friend-1")
        self.service.store.append(first_chat, Message(role="user", content="group message"))
        self.service.store.append(second_chat, Message(role="user", content="private message"))
        self.service.store.save(first_chat)
        self.service.store.save(second_chat)
        self.service.store.replace(first_chat, [])
        self.service.agents.pop(first, None)

        restored = BridgeService(self.service.config)
        self.assertEqual([], restored.store.load_messages(first_chat))
        self.assertEqual("private message", restored.store.load_messages(second_chat)[0].content)
        record = restored.store.get(first_chat)
        self.assertIsNotNone(record)
        self.assertEqual(0, record.message_count if record else None)

    def test_account_and_group_config_are_scoped_by_adapter_and_bot(self) -> None:
        self.service.state.data["accounts"] = [
            {
                "id": "a1",
                "platform": "onebot",
                "bot_id": "100",
                "name": "主 Bot",
                "model": "model-a",
                "enabled": True,
            },
            {
                "id": "a2",
                "platform": "onebot",
                "bot_id": "200",
                "name": "备用 Bot",
                "model": "model-b",
                "enabled": True,
            },
        ]
        self.service.state.data["groups"] = [
            {
                "id": "g1",
                "platform": "onebot",
                "bot_id": "100",
                "group_id": "room",
                "model": "group-model",
                "enabled": True,
            }
        ]
        self.assertEqual("model-a", self.service.effective_chat_config("onebot", "100", "private", "u")["model"])
        self.assertEqual("group-model", self.service.effective_chat_config("onebot", "100", "group", "room")["model"])
        self.assertEqual("model-b", self.service.effective_chat_config("onebot", "200", "group", "room")["model"])

    def test_state_migrates_plugin_fields_and_normalizes_models(self) -> None:
        self.service.state.data["accounts"] = [
            {
                "id": "a1",
                "platform": "onebot",
                "bot_id": "100",
                "name": "100",
                "plugin": "legacy",
                "plugin_config": {"unused": True},
            }
        ]
        self.service.state.data["interfaces"]["providers"] = [
            {"id": "p1", "models": ["legacy-model"]}
        ]
        self.service.state.save()
        restored = BridgeService(self.service.config)
        account = restored.state.data["accounts"][0]
        provider = restored.state.data["interfaces"]["providers"][0]
        self.assertNotIn("plugin", account)
        self.assertNotIn("plugin_config", account)
        self.assertEqual("legacy-model", provider["models"][0]["id"])
        self.assertIsNone(provider["models"][0]["context_length"])

    def test_persona_template_and_account_supplement_are_used(self) -> None:
        self.service.roles.save("friendly", "保持友好。", create=True)
        self.service.state.data["active_role"] = "friendly"
        self.service.state.data["accounts"] = [
            {
                "id": "a1",
                "platform": "onebot",
                "bot_id": "100",
                "persona_role": "friendly",
                "persona_prompt": "称呼用户为朋友。",
            }
        ]
        config = self.service.effective_chat_config("onebot", "100", "private", "u")
        self.assertEqual("保持友好。\n\n称呼用户为朋友。", config["system_prompt"])
        self.service.state.data["groups"] = [
            {
                "id": "g1",
                "platform": "onebot",
                "bot_id": "100",
                "group_id": "room",
                "system_prompt": "只在群里简洁回答。",
            }
        ]
        group_config = self.service.effective_chat_config(
            "onebot", "100", "group", "room"
        )
        self.assertEqual("只在群里简洁回答。", group_config["system_prompt"])

    def test_provider_model_and_context_override_account_defaults(self) -> None:
        self.service.state.data["accounts"] = [
            {
                "id": "a1",
                "platform": "onebot",
                "bot_id": "100",
                "model": "account-model",
                "context_length": 16_000,
                "base_url": "https://account.example/v1",
            }
        ]
        self.service.state.data["interfaces"]["providers"] = [
            {
                "id": "p1",
                "name": "Remote",
                "model": "provider-model",
                "context_length": 32_000,
                "base_url": "https://provider.example/v1",
                "models": [
                    {"id": "group-model", "context_length": 64_000}
                ],
            }
        ]
        self.service.state.data["groups"] = [
            {
                "id": "g1",
                "platform": "onebot",
                "bot_id": "100",
                "group_id": "room",
                "provider_id": "p1",
                "model": "group-model",
            }
        ]
        config = self.service.effective_chat_config("onebot", "100", "group", "room")
        self.assertEqual("group-model", config["model"])
        self.assertEqual("https://provider.example/v1", config["base_url"])
        self.assertEqual(64_000, config["max_context"])

    def test_bot_temperature_configuration_is_inherited_by_groups(self) -> None:
        self.service.state.data["accounts"] = [
            {
                "id": "a1",
                "platform": "onebot",
                "bot_id": "100",
                "temperature_enabled": False,
                "temperature": 1.0,
            }
        ]
        private_config = self.service.effective_chat_config(
            "onebot", "100", "private", "user"
        )
        group_config = self.service.effective_chat_config(
            "onebot", "100", "group", "room"
        )

        self.assertFalse(private_config["temperature_enabled"])
        self.assertEqual(1.0, private_config["temperature"])
        self.assertFalse(group_config["temperature_enabled"])
        self.assertEqual(1.0, group_config["temperature"])

    def test_account_provider_supplies_runtime_connection_and_model(self) -> None:
        self.service.state.data["accounts"] = [
            {
                "id": "a1",
                "platform": "onebot",
                "bot_id": "100",
                "provider_id": "p1",
                "model": "",
                "context_length": 12_000,
            }
        ]
        self.service.state.data["interfaces"]["providers"] = [
            {
                "id": "p1",
                "model": "provider-default",
                "base_url": "https://provider.example/v1",
                "api_key": "provider-key",
                "context_length": 32_000,
                "models": [
                    {"id": "provider-default", "context_length": 64_000}
                ],
            }
        ]
        config = self.service.effective_chat_config(
            "onebot", "100", "private", "user"
        )
        self.assertEqual("provider-default", config["model"])
        self.assertEqual("https://provider.example/v1", config["base_url"])
        self.assertEqual("provider-key", config["api_key"])
        self.assertEqual(64_000, config["max_context"])

    def test_account_model_overrides_provider_default(self) -> None:
        self.service.state.data["accounts"] = [
            {
                "id": "a1",
                "platform": "onebot",
                "bot_id": "100",
                "provider_id": "p1",
                "model": "account-model",
            }
        ]
        self.service.state.data["interfaces"]["providers"] = [
            {
                "id": "p1",
                "model": "provider-model",
                "models": [
                    {"id": "account-model", "context_length": 48_000},
                    {"id": "provider-model", "context_length": 32_000},
                ],
            }
        ]
        config = self.service.effective_chat_config(
            "onebot", "100", "private", "user"
        )
        self.assertEqual("account-model", config["model"])
        self.assertEqual(48_000, config["max_context"])

    def test_account_and_group_tool_selection_inherits_and_overrides(self) -> None:
        self.service.state.data["accounts"] = [
            {
                "id": "a1",
                "platform": "onebot",
                "bot_id": "100",
                "enabled_tools": ["chat_status"],
            }
        ]
        key, _chat_id = self.service.resolve_chat("onebot", "100", "group", "room")
        self.assertEqual(["chat_status"], self.service.inherited_tool_names(key))
        self.service.state.data["groups"] = [
            {
                "id": "g1",
                "platform": "onebot",
                "bot_id": "100",
                "group_id": "room",
                "enabled_tools": ["chat_current_datetime"],
            }
        ]
        self.assertEqual(["chat_current_datetime"], self.service.inherited_tool_names(key))

    def test_context_metadata_parser_supports_nested_provider_fields(self) -> None:
        self.assertEqual(128_000, extract_context_length({"metadata": {"max_model_len": "128000"}}))
        self.assertEqual(
            [{"id": "alpha", "context_length": 32_000, "context_source": "remote"}],
            normalize_model_records([{"id": "alpha", "context_window": 32_000}]),
        )

    def test_slang_settings_survive_restart_and_are_bounded(self) -> None:
        self.service.config.slang_enabled = False
        self.service.config.slang_min_messages = 12
        self.service.config.slang_cooldown_seconds = 900
        self.service.state.data["slang_settings"] = {
            "enabled": False,
            "min_messages": 12,
            "cooldown_seconds": 900,
            "review_provider_id": "p-review",
            "review_model": "review-small",
        }
        self.service.state.save()

        restored = BridgeService(self.service.config)

        self.assertFalse(restored.config.slang_enabled)
        self.assertEqual(12, restored.config.slang_min_messages)
        self.assertEqual(900, restored.config.slang_cooldown_seconds)
        self.assertEqual(
            "p-review",
            restored.state.data["slang_settings"]["review_provider_id"],
        )
        self.assertEqual(
            "review-small",
            restored.state.data["slang_settings"]["review_model"],
        )

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

    def test_sender_context_uses_concise_group_sender_and_admin_prefix(self) -> None:
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
            group_name="Research Group",
            group_member_is_admin=True,
        )
        self.assertEqual("【管理员】Alice Example：", sender_context(incoming))

        incoming.kind = "private"
        self.assertEqual("", sender_context(incoming))

    def test_bridge_agent_system_prompt_explains_concise_sender_and_mentions(self) -> None:
        key, chat_id = self.service.resolve_chat("test", "bot", "group", "room-1")
        agent = self.service._agent(key, chat_id, owner=False)
        prompt = agent._build_system_prompt()
        self.assertIn("群聊消息使用 `昵称：消息` 格式", prompt)
        self.assertIn("不代表 Bot 的 WebUI 配置管理员身份", prompt)
        self.assertIn("`@我` 表示有人提及机器人", prompt)
        self.assertIn("逐条区分用户", prompt)
        self.assertIn("不是每条消息都必须回复", prompt)
        self.assertIn("[SILENT]", prompt)

    def test_persona_is_injected_in_chat_and_agent_modes(self) -> None:
        self.service.state.data["role"] = "始终以小西琳的人格回答"
        key, chat_id = self.service.resolve_chat("test", "bot", "group", "room-1")

        for mode in ("chat", "agent"):
            self.service.set_mode(mode)
            prompt = self.service._agent(key, chat_id, owner=False)._build_system_prompt()
            self.assertIn("始终以小西琳的人格回答", prompt)

    def test_agent_error_is_logged_without_sending_reply(self) -> None:
        async def run_test() -> None:
            usage = SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0)
            result = SimpleNamespace(
                status="error",
                text="",
                error="Error code: 503 - Service temporarily unavailable",
                usage=usage,
                tool_calls=[],
            )
            agent = SimpleNamespace(run=AsyncMock(return_value=result))
            self.service._agent = cast("Any", lambda *_args, **_kwargs: agent)
            incoming = IncomingMessage(
                bot=None,
                platform="test",
                bot_id="bot",
                kind="group",
                peer_id="room-1",
                user_id="member",
                user_name="Member",
                text="hello",
                target=Target("room-1"),
            )

            self.assertEqual("", await self.service._process_message(incoming))
            self.assertTrue(
                any(
                    "处理失败：Error code: 503 - Service temporarily unavailable"
                    in entry.get("text", "")
                    for entry in self.service.state.data["activity"]
                )
            )
            agent.run.assert_awaited_once()

        asyncio.run(run_test())

    def test_chat_mode_suppresses_silent_marker(self) -> None:
        async def run_test() -> None:
            usage = SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0)
            result = SimpleNamespace(
                status="success", text="[SILENT]", usage=usage, tool_calls=[]
            )
            agent = SimpleNamespace(run=AsyncMock(return_value=result))
            self.service._agent = cast("Any", lambda *_args, **_kwargs: agent)
            incoming = IncomingMessage(
                bot=None,
                platform="test",
                bot_id="bot",
                kind="group",
                peer_id="room-1",
                user_id="member",
                user_name="Member",
                text="这条不用回复",
                target=Target("room-1"),
            )

            self.assertEqual("", await self.service._process_message(incoming))
            agent.run.assert_awaited_once()

        asyncio.run(run_test())

    def _process_agent_text(self, text: str) -> str:
        async def run_test() -> str:
            usage = SimpleNamespace(
                prompt_tokens=0, completion_tokens=0, total_tokens=0
            )
            result = SimpleNamespace(
                status="success", text=text, usage=usage, tool_calls=[]
            )
            agent = SimpleNamespace(run=AsyncMock(return_value=result))
            self.service._agent = cast("Any", lambda *_args, **_kwargs: agent)
            incoming = IncomingMessage(
                bot=None,
                platform="test",
                bot_id="bot",
                kind="group",
                peer_id="room-1",
                user_id="member",
                user_name="Member",
                text="hello",
                target=Target("room-1"),
            )
            return await self.service._process_message(incoming)

        return asyncio.run(run_test())

    def test_chat_mode_strips_think_blocks_before_sending(self) -> None:
        reply = self._process_agent_text(
            "<thinking>first</thinking>\n"
            "<thinking>second</thinking>\n"
            "<thinking>third</thinking>\n"
            "同一天啊，那你得好好陪陪你妈，别只顾着刷群了"
        )

        self.assertEqual(
            "同一天啊，那你得好好陪陪你妈，别只顾着刷群了", reply
        )

    def test_chat_mode_suppresses_silent_marker_after_think_blocks(self) -> None:
        reply = self._process_agent_text(
            "<thinking>first</thinking>\n"
            "<thinking>second</thinking>\n"
            "<thinking>third</thinking>\n"
            "[SILENT]"
        )

        self.assertEqual("", reply)

    def test_chat_mode_suppresses_reply_with_only_think_blocks(self) -> None:
        reply = self._process_agent_text(
            "<thinking>first</thinking>\n<thinking>second</thinking>"
        )

        self.assertEqual("", reply)

    def _chat_send_tool(self) -> tuple[str, Any]:
        key, _chat_id = self.service.resolve_chat("test", "bot", "group", "room-1")
        self.service.targets[key] = Target("room-1")
        self.service.bots[key] = object()
        tool = next(
            tool for tool in self.service.chat_tools(key) if tool.name == "chat_send"
        )
        return key, tool

    def test_chat_send_strips_think_blocks_before_sending(self) -> None:
        async def run_test() -> None:
            key, tool = self._chat_send_tool()
            with patch.object(
                self.service, "send_text", AsyncMock(return_value=True)
            ) as send_text:
                result = await tool.call(
                    {"text": "<thinking>hidden</thinking>\n可见正文"},
                    ToolContext(workspace=self.temp.name),
                )

            self.assertEqual("Message sent", result)
            send_text.assert_awaited_once_with(key, "可见正文", reply_to=None)

        asyncio.run(run_test())

    def test_chat_send_suppresses_silent_marker_after_think_blocks(self) -> None:
        async def run_test() -> None:
            _key, tool = self._chat_send_tool()
            with patch.object(
                self.service, "send_text", AsyncMock(return_value=True)
            ) as send_text:
                result = await tool.call(
                    {"text": "<thinking>hidden</thinking>\n[SILENT]"},
                    ToolContext(workspace=self.temp.name),
                )

            self.assertIn("suppressed", result)
            send_text.assert_not_awaited()

        asyncio.run(run_test())

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
            self.assertIn("member-1：hello", combined.text)
            self.assertIn("member-2：world", combined.text)
            self.assertNotIn("user_id=", combined.text)
            self.assertNotIn("group_openid=", combined.text)

        asyncio.run(run_test())

    def test_sensitive_output_is_blocked(self) -> None:
        self.assertIsNotNone(audit_reply("api_key=topsecret"))
        self.assertIsNotNone(audit_reply("open C:\\Users\\alice\\private.txt"))
        self.assertIsNotNone(audit_reply("open D:\\workspace\\private.txt"))
        self.assertIsNone(audit_reply("普通聊天内容"))

    def test_chat_tools_are_allowlisted_by_agent_permissions(self) -> None:
        self.service.state.data["accounts"][0]["reasoning_effort"] = "high"
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
        self.assertIn("WebSearch", defaults["enabled"])
        self.assertNotIn("Bash", defaults["enabled"])

        agent = self.service._agent(key, chat_id, owner=False)
        self.assertIn("WebSearch", {tool.name for tool in agent._tools})
        self.assertEqual(
            "allow",
            agent._check_permission(
                next(tool for tool in agent._tools if tool.name == "WebSearch"),
                {"query": "test"},
            ),
        )
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
        restored.set_mode("agent")
        self.assertNotIn("enabled_tools", restored.state.data["conversations"][key])
        reset_config = restored.session_tool_config(key)
        self.assertIn("chat_current_datetime", reset_config["enabled"])
        self.assertIn("chat_send", reset_config["enabled"])

    def test_mode_defaults_change_available_tools_for_owner_session(self) -> None:
        key, _chat_id = self.service.resolve_chat("test", "bot", "private", "owner")
        chat_tools = self.service.session_tool_config(key)
        bash = next(tool for tool in chat_tools["tools"] if tool["name"] == "Bash")
        self.assertFalse(bash["available"])
        self.assertNotIn("Bash", chat_tools["enabled"])

        self.service.set_mode("agent")
        tools = self.service.session_tool_config(key)
        self.assertIn("Bash", tools["enabled"])
        self.assertTrue(
            next(tool for tool in tools["tools"] if tool["name"] == "Bash")["available"]
        )
        self.assertIn("chat_current_datetime", tools["enabled"])

        self.service.set_session_tools(key, ["chat_current_datetime"])
        self.service.set_mode("chat")
        self.assertNotIn("enabled_tools", self.service.state.data["conversations"][key])
        defaults = self.service.session_tool_config(key)
        self.assertNotIn("Bash", defaults["enabled"])
        self.assertIn("chat_send", defaults["enabled"])

    def test_session_tool_catalog_does_not_expose_admin_tools_to_group(self) -> None:
        key, _chat_id = self.service.resolve_chat("test", "bot", "group", "room-1")
        tools = self.service.session_tool_config(key)["tools"]
        self.assertNotIn("Bash", {tool["name"] for tool in tools})

    def test_discovered_mcp_tools_are_session_selectable_and_allowed(self) -> None:
        key, chat_id = self.service.resolve_chat("test", "bot", "group", "room-1")
        self.service.mcp_server_url = "http://localhost:3000/mcp"
        self.service.mcp_tools = [
            {
                "name": "search",
                "description": "Search the web",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ]
        tool_name = "mcp__open_websearch__search"
        catalog = self.service.session_tool_config(key)
        self.assertIn(tool_name, {tool["name"] for tool in catalog["tools"]})
        self.assertIn(tool_name, catalog["enabled"])
        self.assertNotIn("WebSearch", {tool["name"] for tool in catalog["tools"]})
        agent = self.service._agent(key, chat_id, owner=False)
        tool = next(tool for tool in agent._tools if tool.name == tool_name)
        self.assertEqual("allow", agent._check_permission(tool, {"query": "test"}))

    def test_mcp_tool_call_uses_discovered_server_tool(self) -> None:
        self.service.mcp_server_url = "http://localhost:3000/mcp"
        self.service.mcp_tools = [
            {
                "name": "search",
                "description": "Search the web",
                "inputSchema": {"type": "object"},
            }
        ]

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def initialize(self):
                return None

            async def call_tool(self, name, arguments):
                self.called = (name, arguments)
                return type(
                    "Result", (), {"content": [type("Text", (), {"text": "Found it"})()]}
                )()

        class FakeTransport:
            async def __aenter__(self):
                return object(), object(), lambda: None

            async def __aexit__(self, *_args):
                return None

        session = FakeSession()
        with (
            patch("mcp.ClientSession", return_value=session),
            patch(
                "mcp.client.streamable_http.streamablehttp_client",
                return_value=FakeTransport(),
            ) as transport,
        ):
            tool = self.service._mcp_tools()[0]
            result = asyncio.run(
                tool.call({"query": "MCP"}, ToolContext(workspace=self.temp.name))
            )

        self.assertEqual("Found it", result)
        self.assertEqual(("search", {"query": "MCP"}), session.called)
        transport.assert_called_once_with("http://localhost:3000/mcp")

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
            self.service.command("member", "/reply 0.5", key, chat_id),
        )
        self.assertEqual(
            "回复概率只对群聊生效。",
            self.service.command("owner", "/reply 0.5", key, chat_id),
        )
        group_key, group_chat = self.service.resolve_chat(
            "test", "bot", "group", "room-1"
        )
        self.assertEqual(
            "回复概率已设为 0.5。",
            self.service.command("owner", "/reply 0.5", group_key, group_chat),
        )
        self.assertEqual(0.5, self.service.reply_probability_for_key(group_key))
        result = self.service.command("member", "/reset", key, chat_id)
        self.assertIsNotNone(result)
        self.assertIn("当前会话上下文已重置", result or "")


class ReplyCleaningTests(unittest.TestCase):
    def test_strip_think_blocks_removes_consecutive_blocks(self) -> None:
        text = (
            "<thinking>first</thinking>\n"
            "<thinking>second</thinking>\n"
            "<thinking>third</thinking>\n"
            "同一天啊，那你得好好陪陪你妈，别只顾着刷群了"
        )

        self.assertEqual(
            "\n\n\n同一天啊，那你得好好陪陪你妈，别只顾着刷群了",
            strip_think_blocks(text),
        )

    def test_strip_think_blocks_handles_case_and_attributes(self) -> None:
        text = (
            '<THINKING type="inner">hidden</THINKING>\n'
            "<Think>secret</Think>\n"
            "可见正文"
        )

        self.assertEqual("\n\n可见正文", strip_think_blocks(text))

    def test_strip_think_blocks_discards_unclosed_block(self) -> None:
        self.assertEqual("可见正文", strip_think_blocks("可见正文<thinking>截断的思考"))

    def test_strip_think_blocks_removes_stray_closing_tag(self) -> None:
        self.assertEqual("正文", strip_think_blocks("正文</thinking>"))

    def test_is_silent_reply_recognizes_case_insensitive_marker(self) -> None:
        self.assertTrue(is_silent_reply("[SILENT]"))
        self.assertTrue(is_silent_reply("[silent]"))
        self.assertTrue(is_silent_reply("[Silent]"))

    def test_is_silent_reply_ignores_marker_inside_think_block(self) -> None:
        visible = strip_think_blocks("<thinking>[SILENT]</thinking>")

        self.assertEqual("", visible)
        self.assertFalse(is_silent_reply(visible))

    def test_is_silent_reply_detects_marker_after_think_blocks(self) -> None:
        visible = strip_think_blocks(
            "<thinking>first</thinking><thinking>second</thinking>\n[SILENT]"
        )

        self.assertTrue(is_silent_reply(visible))

    def test_is_silent_reply_false_for_normal_reply_after_think_blocks(self) -> None:
        visible = strip_think_blocks(
            "<thinking>first</thinking>\n同一天啊，那你得好好陪陪你妈"
        )

        self.assertFalse(is_silent_reply(visible))


if __name__ == "__main__":
    unittest.main()
