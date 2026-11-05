"""记忆总结：模型输出解析、批次入队与失败退避的回归测试。"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from nonebot_plugin_alconna import Target

from plugin_chatbot.bridge.service import (
    MEMORY_RETRY_BASE_SECONDS,
    MEMORY_RETRY_MAX_SECONDS,
    BridgeConfig,
    BridgeService,
    IncomingMessage,
    parse_memory_draft,
)

PAYLOAD: dict[str, Any] = {
    "title": "沟通偏好",
    "description": "用户希望回答简洁",
    "type": "user",
    "content": "用户希望回答简洁。",
}


def _json(payload: Any = None) -> str:
    return json.dumps(PAYLOAD if payload is None else payload, ensure_ascii=False)


class _DraftLLM:
    """返回固定文本的总结模型替身。"""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0
        self.system_prompt = ""
        self.prompt = ""

    async def complete(self, messages, tools=None, system_prompt=None):
        self.calls += 1
        self.system_prompt = system_prompt or ""
        self.prompt = str(messages[0].content) if messages else ""
        return SimpleNamespace(content=self.content)


class MemoryDraftParsingTests(unittest.TestCase):
    def test_plain_object_returns_all_fields(self) -> None:
        self.assertEqual(PAYLOAD, parse_memory_draft(_json()))

    def test_code_fence_with_trailing_prose_is_parsed(self) -> None:
        content = f"```json\n{_json()}\n```\n\n以上为整理结果，请查收。"

        self.assertEqual(PAYLOAD, parse_memory_draft(content))

    def test_multiple_json_values_do_not_raise_extra_data(self) -> None:
        content = f'{{"title":"占位"}}\n{_json()}\n{{"title":"另一个"}}'

        self.assertEqual(PAYLOAD, parse_memory_draft(content))

    def test_leading_empty_array_then_object_is_parsed(self) -> None:
        content = f"[]\n{_json()}"

        self.assertEqual(PAYLOAD, parse_memory_draft(content))

    def test_top_level_array_is_unwrapped(self) -> None:
        self.assertEqual(PAYLOAD, parse_memory_draft(f"[{_json()}]"))

    def test_common_envelope_keys_are_unwrapped(self) -> None:
        for key in ("memory", "memories", "result", "data", "items"):
            with self.subTest(key=key):
                wrapped = {key: [PAYLOAD] if key.endswith("s") else PAYLOAD}
                self.assertEqual(PAYLOAD, parse_memory_draft(_json(wrapped)))

    def test_prefers_candidate_with_most_populated_fields(self) -> None:
        partial = {"title": "不完整", "type": "user"}
        content = f"{_json(partial)}\n{_json()}"

        self.assertEqual(PAYLOAD, parse_memory_draft(content))

    def test_unparseable_output_returns_none(self) -> None:
        for content in ("", "not json", "模型暂时无法总结", "[1, 2, 3]", "null"):
            with self.subTest(content=content):
                self.assertIsNone(parse_memory_draft(content))

    def test_nested_json_inside_string_does_not_break_scanning(self) -> None:
        payload = {**PAYLOAD, "content": '用户说过 "{" 只是举例'}

        self.assertEqual(payload, parse_memory_draft(_json(payload)))


class MemorySummaryBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.service = BridgeService(
            BridgeConfig(state_dir=root / "state", workspace=root)
        )
        self.service.state.data["accounts"] = [
            {
                "id": "test-bot",
                "platform": "test",
                "bot_id": "bot",
                "admins": [],
                "whitelist": [],
                "blacklist": [],
                "private_users": [],
            }
        ]

    def _seed(self) -> dict[str, Any]:
        account = self.service.state.data["accounts"][0]
        account["memory_enabled"] = True
        account["memory_interval"] = 2
        account["memory_buffer"] = [
            {"sender": "甲", "user": "请回答简洁", "assistant": "好的"},
            {"sender": "乙", "user": "记一下", "assistant": "已记"},
        ]
        self.service.state.save()
        return account

    def _run(
        self, content: str, account: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if account is None:
            account = self._seed()

        async def exercise() -> None:
            await self.service._summarize_memory_batch(
                "test-bot", _DraftLLM(content), 2
            )

        asyncio.run(exercise())
        return account

    def _exchange_task_count(self, account: dict[str, Any]) -> int:
        incoming = IncomingMessage(
            bot=None,
            platform="test",
            bot_id="bot",
            kind="private",
            peer_id="friend-1",
            user_id="friend-1",
            user_name="Visitor",
            text="新消息",
            target=Target("friend-1"),
        )

        async def exercise() -> int:
            await self.service._record_memory_exchange(
                account, incoming, "回复", _DraftLLM(_json())
            )
            created = len(self.service.memory_tasks)
            await asyncio.gather(*list(self.service.memory_tasks))
            return created

        return asyncio.run(exercise())

    def test_valid_output_creates_pending_candidate_and_drains_buffer(self) -> None:
        account = self._run(_json())

        queue = self.service.state.data["memory_queue"]
        self.assertEqual(1, len(queue))
        self.assertEqual("沟通偏好", queue[0]["title"])
        self.assertEqual("user", queue[0]["type"])
        self.assertEqual("pending", queue[0]["status"])
        self.assertEqual(2, queue[0]["source_messages"])
        self.assertEqual([], account["memory_buffer"])

    def test_all_unreliable_output_shapes_still_produce_a_candidate(self) -> None:
        valid = _json()
        cases = {
            "plain": valid,
            "fenced with trailing prose": f"```json\n{valid}\n```\n\n说明文字",
            "extra data (multiple objects)": f'{{"title":"占位"}}\n{valid}',
            "extra data (leading array)": f"[]\n{valid}",
            "top-level array": f"[{valid}]",
            "envelope": _json({"memory": PAYLOAD}),
        }
        for name, content in cases.items():
            with self.subTest(case=name):
                self.service.state.data["memory_queue"].clear()
                account = self._run(content)
                self.assertEqual(1, len(self.service.state.data["memory_queue"]))
                self.assertEqual([], account["memory_buffer"])
                self.assertNotIn("memory_summary_failures", account)

    def test_list_and_dict_content_is_normalized_to_text(self) -> None:
        self._run(_json({**PAYLOAD, "content": ["要点一", "要点二"]}))
        self.assertEqual(
            "要点一\n要点二", self.service.state.data["memory_queue"][0]["content"]
        )

        self.service.state.data["memory_queue"].clear()
        self._run(_json({**PAYLOAD, "content": {"偏好": "简洁", "语气": "轻松"}}))
        self.assertEqual(
            "偏好: 简洁\n语气: 轻松",
            self.service.state.data["memory_queue"][0]["content"],
        )

    def test_type_case_and_multiline_title_are_normalized(self) -> None:
        self._run(_json({**PAYLOAD, "type": "User", "title": "沟通\n偏好"}))

        candidate = self.service.state.data["memory_queue"][0]
        self.assertEqual("user", candidate["type"])
        self.assertEqual("沟通 偏好", candidate["title"])

    def test_unparseable_output_keeps_buffer_and_sets_backoff(self) -> None:
        account = self._run("not json")

        self.assertEqual([], self.service.state.data["memory_queue"])
        self.assertEqual(2, len(account["memory_buffer"]))
        self.assertEqual(1, account["memory_summary_failures"])
        self.assertGreater(account["memory_summary_retry_at"], time.time())
        logs = [row["text"] for row in self.service.state.data["activity"]]
        self.assertTrue(any("输出无法解析为记忆对象" in row for row in logs))
        self.assertTrue(any("秒后重试" in row for row in logs))

    def test_incomplete_fields_keep_buffer_and_set_backoff(self) -> None:
        account = self._run(_json({"title": "只有标题", "type": "unknown"}))

        self.assertEqual([], self.service.state.data["memory_queue"])
        self.assertEqual(2, len(account["memory_buffer"]))
        self.assertEqual(1, account["memory_summary_failures"])

    def test_backoff_suppresses_retry_on_every_new_message(self) -> None:
        account = self._run("not json")
        self.assertEqual(0, self._exchange_task_count(account))

    def test_retry_resumes_after_backoff_window(self) -> None:
        account = self._run("not json")
        future = time.time() + 3600
        with patch("plugin_chatbot.bridge.service.time.time", return_value=future):
            created = self._exchange_task_count(account)
        self.assertEqual(1, created)

    def test_backoff_grows_exponentially_and_is_capped(self) -> None:
        account = self._seed()
        for attempt in range(1, 7):
            with self.subTest(attempt=attempt):
                before = time.time()
                self._run("not json", account)
                expected = min(
                    MEMORY_RETRY_MAX_SECONDS,
                    MEMORY_RETRY_BASE_SECONDS * 2 ** (attempt - 1),
                )
                delay = account["memory_summary_retry_at"] - before
                self.assertAlmostEqual(expected, delay, delta=2)
                self.assertEqual(attempt, account["memory_summary_failures"])

    def test_success_clears_backoff_state(self) -> None:
        account = self._seed()
        account["memory_summary_failures"] = 3
        account["memory_summary_retry_at"] = time.time() + 900

        self._run(_json(), account)

        self.assertNotIn("memory_summary_failures", account)
        self.assertNotIn("memory_summary_retry_at", account)
        self.assertEqual(1, len(self.service.state.data["memory_queue"]))

    def test_prompt_forbids_arrays_and_extra_text(self) -> None:
        llm = _DraftLLM(_json())
        self._seed()

        async def exercise() -> None:
            await self.service._summarize_memory_batch("test-bot", llm, 2)

        asyncio.run(exercise())
        self.assertIn("只输出一个 JSON 对象", llm.prompt)
        self.assertIn("不要数组", llm.prompt)
        self.assertIn("单个 JSON 对象", llm.system_prompt)


if __name__ == "__main__":
    unittest.main()
