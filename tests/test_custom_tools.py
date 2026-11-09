"""自定义 Tool 的校验、执行与可见范围测试。

HTTP 层沿用与其它测试一致的策略：不启动 NoneBot / FastAPI，
路由鉴权靠人工冒烟核对。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tool import ToolContext
from plugin_chatbot.bridge.custom_tools import (
    MAX_SOURCE_CHARS,
    CustomToolError,
    CustomToolStore,
    execute,
    normalize_row,
    validate_definition,
)
from plugin_chatbot.bridge.service import BridgeConfig, BridgeService

RUNNER = (
    Path(__file__).resolve().parents[1]
    / "plugin_chatbot"
    / "bridge"
    / "custom_tool_runner.py"
)


def sample(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "custom_probe",
        "description": "探测工作区状态",
        "input_schema": {
            "type": "object",
            "properties": {"who": {"type": "string"}},
        },
        "source": "def run(args, ctx):\n    return 'hello ' + str(args.get('who'))\n",
        "scope": "admin",
        "timeout": 10,
        "enabled": True,
    }
    payload.update(overrides)
    return payload


class CustomToolValidationTests(unittest.TestCase):
    def test_rejects_bad_names(self) -> None:
        for name in ("custom-", "custom_", "custom_" + "x" * 60, "  "):
            with self.assertRaises(CustomToolError):
                validate_definition(sample(name=name), existing=[])

    def test_normalizes_prefix_and_case(self) -> None:
        spec = validate_definition(sample(name=" Disk_Usage "), existing=[])
        self.assertEqual("custom_disk_usage", spec["name"])

    def test_rejects_duplicate_name(self) -> None:
        existing = [{"id": "a" * 16, "name": "custom_probe"}]
        with self.assertRaises(CustomToolError) as ctx:
            validate_definition(sample(), existing=existing)
        self.assertEqual(409, ctx.exception.status)

    def test_update_ignores_own_row(self) -> None:
        existing = [{"id": "a" * 16, "name": "custom_probe"}]
        spec = validate_definition(sample(), existing=existing, current_id="a" * 16)
        self.assertEqual("custom_probe", spec["name"])

    def test_rejects_syntax_error_with_line_number(self) -> None:
        with self.assertRaises(CustomToolError) as ctx:
            validate_definition(
                sample(source="def run(args, ctx)\n    return 1\n"), existing=[]
            )
        self.assertIn("第 1 行", str(ctx.exception))

    def test_rejects_missing_run_and_async_run(self) -> None:
        with self.assertRaises(CustomToolError):
            validate_definition(sample(source="x = 1\n"), existing=[])
        with self.assertRaises(CustomToolError) as ctx:
            validate_definition(
                sample(source="async def run(args, ctx):\n    return 1\n"),
                existing=[],
            )
        self.assertIn("同步", str(ctx.exception))

    def test_rejects_run_with_single_argument(self) -> None:
        with self.assertRaises(CustomToolError):
            validate_definition(
                sample(source="def run(args):\n    return 1\n"), existing=[]
            )

    def test_rejects_bad_schema(self) -> None:
        for schema in (
            [],
            {"type": "string"},
            {"type": "object", "properties": []},
            {"type": "object", "properties": {"a": 1}},
            {"type": "object", "properties": {}, "required": ["missing"]},
        ):
            with self.assertRaises(CustomToolError):
                validate_definition(sample(input_schema=schema), existing=[])

    def test_rejects_out_of_range_timeout(self) -> None:
        for timeout in (0, 301, -5, "abc"):
            with self.assertRaises(CustomToolError):
                validate_definition(sample(timeout=timeout), existing=[])

    def test_rejects_oversized_source_and_tool_count(self) -> None:
        with self.assertRaises(CustomToolError):
            validate_definition(
                sample(source="def run(a, c):\n    return '" + "x" * MAX_SOURCE_CHARS + "'"),
                existing=[],
            )
        crowded = [{"id": f"{i:016x}", "name": f"custom_t{i}"} for i in range(40)]
        with self.assertRaises(CustomToolError):
            validate_definition(sample(), existing=crowded)

    def test_rejects_unknown_scope_and_empty_description(self) -> None:
        with self.assertRaises(CustomToolError):
            validate_definition(sample(scope="everyone"), existing=[])
        with self.assertRaises(CustomToolError):
            validate_definition(sample(description="   "), existing=[])

    def test_normalize_row_survives_broken_state(self) -> None:
        self.assertIsNone(normalize_row({"id": "nothex", "name": "custom_x"}))
        self.assertIsNone(normalize_row({"id": "a" * 16, "name": "Bash"}))
        row = normalize_row(
            {"id": "b" * 16, "name": "custom_x", "timeout": 9999, "scope": "weird"}
        )
        assert row is not None
        self.assertEqual(300.0, row["timeout"])
        self.assertEqual("admin", row["scope"])
        self.assertTrue(row["enabled"])


class CustomToolExecutionTests(unittest.TestCase):
    def test_roundtrip_with_run_cmd_and_env_isolation(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-must-not-leak"
        os.environ["BRIDGE_CONSOLE_TOKEN"] = "console-must-not-leak"
        source = (
            "import json, os\n"
            "def run(args, ctx):\n"
            "    out = run_cmd('echo hi-' + args['who'])\n"
            "    leaked = [k for k in os.environ if k.endswith('_API_KEY')]\n"
            "    leaked += [k for k in os.environ if k == 'BRIDGE_CONSOLE_TOKEN']\n"
            "    return json.dumps({'out': out['stdout'].strip(), 'leaked': leaked})\n"
        )
        with tempfile.TemporaryDirectory() as ws:
            result = asyncio.run(
                execute(
                    runner=RUNNER,
                    workspace=Path(ws),
                    source=source,
                    name="custom_probe",
                    args={"who": "there"},
                    timeout=20,
                )
            )
        self.assertTrue(result["ok"], result)
        payload = json.loads(result["output"])
        self.assertEqual("hi-there", payload["out"])
        self.assertEqual([], payload["leaked"])

    def test_print_does_not_break_the_protocol(self) -> None:
        source = 'print("noise")\ndef run(args, ctx):\n    print("more")\n    return "ok"\n'
        with tempfile.TemporaryDirectory() as ws:
            result = asyncio.run(
                execute(
                    runner=RUNNER,
                    workspace=Path(ws),
                    source=source,
                    name="custom_noisy",
                    args={},
                    timeout=10,
                )
            )
        self.assertTrue(result["ok"])
        self.assertEqual("ok", result["output"])

    def test_runtime_error_reports_traceback(self) -> None:
        source = "def run(args, ctx):\n    return 1 / 0\n"
        with tempfile.TemporaryDirectory() as ws:
            result = asyncio.run(
                execute(
                    runner=RUNNER,
                    workspace=Path(ws),
                    source=source,
                    name="custom_bad",
                    args={},
                    timeout=10,
                )
            )
        self.assertFalse(result["ok"])
        self.assertIn("ZeroDivisionError", result["error"])
        self.assertIn("<custom_tool:custom_bad>", result["traceback"])

    def test_timeout_kills_the_process(self) -> None:
        source = "import time\ndef run(args, ctx):\n    time.sleep(30)\n    return 'x'\n"
        with tempfile.TemporaryDirectory() as ws:
            result = asyncio.run(
                execute(
                    runner=RUNNER,
                    workspace=Path(ws),
                    source=source,
                    name="custom_slow",
                    args={},
                    timeout=1,
                )
            )
        self.assertFalse(result["ok"])
        self.assertIn("超时", result["error"])
        self.assertLess(result["elapsed_ms"], 8_000)

    def test_output_is_truncated(self) -> None:
        source = "def run(args, ctx):\n    return 'x' * 50000\n"
        with tempfile.TemporaryDirectory() as ws:
            result = asyncio.run(
                execute(
                    runner=RUNNER,
                    workspace=Path(ws),
                    source=source,
                    name="custom_loud",
                    args={},
                    timeout=10,
                    max_output_chars=100,
                )
            )
        self.assertTrue(result["ok"])
        self.assertEqual(100, len(result["output"]))
        self.assertTrue(result["truncated"])

    def test_store_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = CustomToolStore(Path(root))
            with self.assertRaises(CustomToolError):
                store.path("../../etc/passwd")


class CustomToolServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.service = BridgeService(
            BridgeConfig(state_dir=root / "state", workspace=root)
        )
        self.service.state.data["accounts"] = [
            {
                "id": "test-bot",
                "platform": "test",
                "bot_id": "bot",
                "admins": [{"id": "owner", "kind": "private", "name": "Owner"}],
                "whitelist": [],
                "blacklist": [],
                "private_users": [],
            }
        ]
        self.service.state.save()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create(self, **overrides: object) -> dict[str, object]:
        return self.service.create_custom_tool(sample(**overrides))

    def _keys(self) -> tuple[str, str, str]:
        admin_key, _ = self.service.resolve_chat("test", "bot", "private", "owner")
        friend_key, _ = self.service.resolve_chat("test", "bot", "private", "friend")
        group_key, _ = self.service.resolve_chat("test", "bot", "group", "room")
        return admin_key, friend_key, group_key

    def test_state_backfills_custom_tools(self) -> None:
        self.assertIn("custom_tools", self.service.state.data)
        self.assertEqual([], self.service.state.data["custom_tools"])

    def test_scope_matrix(self) -> None:
        admin_key, friend_key, group_key = self._keys()
        self.service.state.data["mode"] = "agent"
        self._create(scope="admin")
        names = {
            key: {tool.name for tool in self.service.available_session_tools(key)}
            for key in (admin_key, friend_key, group_key)
        }
        self.assertIn("custom_probe", names[admin_key])
        self.assertNotIn("custom_probe", names[friend_key])
        self.assertNotIn("custom_probe", names[group_key])

        self.service.delete_custom_tool(
            str(self.service.state.data["custom_tools"][0]["id"])
        )
        self._create(scope="private")
        self.assertIn(
            "custom_probe",
            {tool.name for tool in self.service.available_session_tools(friend_key)},
        )
        self.assertNotIn(
            "custom_probe",
            {tool.name for tool in self.service.available_session_tools(group_key)},
        )

        self.service.state.data["custom_tools"] = []
        self._create(scope="all")
        for key in (admin_key, friend_key, group_key):
            self.assertIn(
                "custom_probe",
                {tool.name for tool in self.service.available_session_tools(key)},
            )

    def test_chat_mode_hides_admin_scoped_tools(self) -> None:
        admin_key, _, _ = self._keys()
        self.service.state.data["mode"] = "chat"
        self._create(scope="admin")
        self.assertNotIn(
            "custom_probe",
            {tool.name for tool in self.service.available_session_tools(admin_key)},
        )
        self.assertNotIn(
            "custom_probe",
            {row["name"] for row in self.service.tool_catalog()},
        )

    def test_disabled_tool_is_hidden(self) -> None:
        admin_key, _, _ = self._keys()
        self.service.state.data["mode"] = "agent"
        self._create(enabled=False)
        self.assertNotIn(
            "custom_probe",
            {tool.name for tool in self.service.available_session_tools(admin_key)},
        )

    def test_catalog_marks_custom_source(self) -> None:
        self.service.state.data["mode"] = "agent"
        self._create()
        catalog = {row["name"]: row for row in self.service.tool_catalog()}
        self.assertEqual("custom", catalog["custom_probe"]["source"])
        self.assertTrue(catalog["custom_probe"]["admin_only"])

    def test_collision_with_builtin_is_skipped(self) -> None:
        admin_key, _, _ = self._keys()
        self.service.state.data["mode"] = "agent"
        self._create()
        self.service.state.data["custom_tools"][0]["name"] = "Bash"
        self.assertNotIn(
            "Bash",
            [
                tool.name
                for tool in self.service.available_session_tools(admin_key)
                if tool.name != "Bash"
            ],
        )
        self.assertTrue(
            any("同名" in row["text"] for row in self.service.state.data["activity"])
        )

    def test_owner_gets_allow_rule(self) -> None:
        admin_key, admin_chat = self.service.resolve_chat(
            "test", "bot", "private", "owner"
        )
        self.service.state.data["mode"] = "agent"
        self._create()
        agent = self.service._agent(admin_key, admin_chat, owner=True)
        rules = {rule.tool: rule.behavior for rule in agent.permission.rules}
        self.assertEqual("allow", rules.get("custom_probe"))

    def test_rename_migrates_enabled_tools(self) -> None:
        admin_key, _, _ = self._keys()
        self.service.state.data["mode"] = "agent"
        created = self._create()
        self.service.state.data["accounts"][0]["enabled_tools"] = ["custom_probe"]
        self.service.state.data["conversations"][admin_key]["enabled_tools"] = [
            "custom_probe"
        ]
        self.service.update_custom_tool(
            str(created["id"]), {"name": "custom_renamed"}
        )
        self.assertEqual(
            ["custom_renamed"], self.service.state.data["accounts"][0]["enabled_tools"]
        )
        self.assertEqual(
            ["custom_renamed"],
            self.service.state.data["conversations"][admin_key]["enabled_tools"],
        )

    def test_update_without_source_keeps_the_script(self) -> None:
        created = self._create()
        updated = self.service.update_custom_tool(
            str(created["id"]), {"enabled": False}
        )
        self.assertFalse(updated["enabled"])
        self.assertIn("def run", str(updated["source"]))

    def test_tampered_source_is_reported(self) -> None:
        created = self._create()
        path = self.service.custom_tools.path(str(created["id"]))
        path.write_text("def run(a, c):\n    return 'hacked'\n", encoding="utf-8")
        rows = {row["name"]: row for row in self.service.custom_tool_rows()}
        self.assertEqual("invalid", rows["custom_probe"]["status"])
        admin_key, _, _ = self._keys()
        self.service.state.data["mode"] = "agent"
        self.assertNotIn(
            "custom_probe",
            {tool.name for tool in self.service.available_session_tools(admin_key)},
        )

    def test_orphan_scripts_are_pruned(self) -> None:
        stray = self.service.custom_tools.root / ("c" * 16 + ".py")
        stray.write_text("def run(a, c):\n    return 'x'\n", encoding="utf-8")
        restored = BridgeService(self.service.config)
        self.assertFalse(stray.exists())
        self.assertEqual([], restored.state.data["custom_tools"])

    def test_delete_removes_script_and_row(self) -> None:
        created = self._create()
        path = self.service.custom_tools.path(str(created["id"]))
        self.assertTrue(path.exists())
        self.assertTrue(self.service.delete_custom_tool(str(created["id"])))
        self.assertFalse(path.exists())
        self.assertEqual([], self.service.state.data["custom_tools"])
        self.assertFalse(self.service.delete_custom_tool(str(created["id"])))

    def test_tool_handler_executes_the_script(self) -> None:
        admin_key, _, _ = self._keys()
        self.service.state.data["mode"] = "agent"
        self._create()
        tool = next(
            item
            for item in self.service.available_session_tools(admin_key)
            if item.name == "custom_probe"
        )
        ctx = ToolContext(workspace=self.temp.name)
        self.assertEqual("hello agent", asyncio.run(tool.handler({"who": "agent"}, ctx)))

    def test_tool_handler_reports_errors_with_prefix(self) -> None:
        admin_key, _, _ = self._keys()
        self.service.state.data["mode"] = "agent"
        self._create(source="def run(args, ctx):\n    return 1 / 0\n")
        tool = next(
            item
            for item in self.service.available_session_tools(admin_key)
            if item.name == "custom_probe"
        )
        output = asyncio.run(tool.handler({}, ToolContext(workspace=self.temp.name)))
        self.assertTrue(output.startswith("Error:"))
        self.assertIn("ZeroDivisionError", output)

    def test_run_custom_tool_logs_activity(self) -> None:
        created = self._create()
        source = self.service.custom_tool_detail(str(created["id"]))["source"]
        result = asyncio.run(
            self.service.run_custom_tool(
                source=str(source),
                name="custom_probe",
                args={"who": "log"},
                timeout=10,
                record=True,
            )
        )
        self.assertTrue(result["ok"], result)
        self.assertIn("custom_probe", self.service.state.data["activity"][-1]["text"])


if __name__ == "__main__":
    unittest.main()
