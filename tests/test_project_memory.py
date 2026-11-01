from __future__ import annotations

import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from agent import Agent, LLMClient, LLMResponse, ProjectMemoryStore
from agent.memory import project_memory_tools
from agent.messages import Message
from agent.tool import ToolContext


class MemoryAgentBackend:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.tools = []

    async def complete(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        self.system_prompt = system_prompt or ""
        self.tools = list(tools or [])
        return LLMResponse(content="done")


class ProjectMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_index_round_trip_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectMemoryStore(temp)
            store.save(
                "release-policy",
                "Release policy",
                "Release timing and approval constraints",
                "project",
                "Production releases require owner approval.",
            )

            self.assertEqual(
                "Production releases require owner approval.",
                store.get("release-policy")["content"],
            )
            self.assertIn("Release policy", store.index())
            self.assertIn("release-policy.md", store.index())

            store.delete("release-policy")

            self.assertEqual([], store.list())
            self.assertEqual("", store.index())

    async def test_memory_validation_rejects_traversal_and_unknown_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectMemoryStore(temp)
            with self.assertRaises(ValueError):
                store.save("../outside", "x", "x", "project", "x")
            with self.assertRaises(ValueError):
                store.save("ok", "x", "x", "unknown", "x")

    async def test_agent_injects_index_and_lists_only_enabled_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectMemoryStore(temp)
            store.save(
                "team-pref",
                "Team preference",
                "Review style",
                "feedback",
                "Keep changes narrowly scoped.",
            )
            backend = MemoryAgentBackend()
            agent = Agent(workspace=temp, llm_client=backend)

            result = await agent.run("hello")

            self.assertEqual("completed", result.status)
            self.assertIn("Team preference", backend.system_prompt)
            self.assertIn("ProjectMemoryRead", backend.system_prompt)
            self.assertIn("ProjectMemoryWrite", backend.system_prompt)
            self.assertIn(
                '"required":["name","title","description","type","content"]',
                backend.system_prompt,
            )
            self.assertIn("structured tool calling interface", backend.system_prompt)
            self.assertIn(
                "If you are not sure about file content or codebase structure pertaining "
                "to the user's request, use your tools to read files and gather the "
                "relevant information: do NOT guess or make up an answer.",
                backend.system_prompt,
            )
            self.assertEqual(
                {tool.name for tool in backend.tools},
                {tool.name for tool in agent._tools},
            )
            self.assertTrue(
                {
                    "Bash",
                    "Read",
                    "Write",
                    "Edit",
                    "Glob",
                    "Grep",
                    "WebFetch",
                    "WebSearch",
                }.issubset({tool.name for tool in backend.tools})
            )
            for tool in backend.tools:
                self.assertIn(f"- {tool.name}: {tool.description}", backend.system_prompt)
                self.assertIn(
                    json.dumps(tool.input_schema, ensure_ascii=False, separators=(",", ":")),
                    backend.system_prompt,
                )

            read_only = Agent(
                workspace=temp,
                llm_client=MemoryAgentBackend(),
                project_memory_tools_enabled=False,
            )
            self.assertFalse(
                any(tool.name.startswith("ProjectMemory") for tool in read_only._tools)
            )

    async def test_memory_tools_read_and_write_shared_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectMemoryStore(temp)
            tools = {tool.name: tool for tool in project_memory_tools(store)}
            context = ToolContext(workspace=temp)
            saved = await tools["ProjectMemoryWrite"].call(
                {
                    "name": "architecture",
                    "title": "Architecture",
                    "description": "Core design decision",
                    "type": "project",
                    "content": "The bridge uses one Agent session per conversation.",
                },
                context,
            )
            read = await tools["ProjectMemoryRead"].call(
                {"name": "architecture"}, context
            )

            self.assertIn("Saved project memory", saved)
            self.assertIn("untrusted reference data", read)
            self.assertIn("one Agent session per conversation", read)

    async def test_reasoning_effort_is_passed_and_environment_fallback_works(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = Agent(workspace=temp, reasoning_effort="high")
            llm = agent._llm
            if not isinstance(llm, LLMClient):
                self.fail("Agent did not create an LLMClient")
            self.assertEqual("high", llm.reasoning_effort)
            await agent.close()

            with patch.dict(os.environ, {"OPENAI_REASONING_EFFORT": "low"}):
                client = LLMClient(model="test")
                self.assertEqual("low", client.reasoning_effort)
                await client._client.close()

    async def test_llm_client_sends_reasoning_effort(self) -> None:
        class FakeCompletions:
            def __init__(self) -> None:
                self.kwargs = {}

            async def create(self, **kwargs):
                self.kwargs = kwargs

                async def stream():
                    yield SimpleNamespace(usage=None, choices=[])

                return stream()

        api = FakeCompletions()
        client = LLMClient(model="test", reasoning_effort="medium")
        client._client = SimpleNamespace(chat=SimpleNamespace(completions=api))

        await client.complete([Message(role="user", content="hello")])

        self.assertEqual("medium", api.kwargs["reasoning_effort"])
        self.assertEqual("test", api.kwargs["model"])

        no_effort_api = FakeCompletions()
        no_effort_client = LLMClient(model="test")
        no_effort_client._client = SimpleNamespace(
            chat=SimpleNamespace(completions=no_effort_api)
        )
        with patch.dict(os.environ, {"OPENAI_REASONING_EFFORT": ""}):
            await no_effort_client.complete([Message(role="user", content="hello")])
        self.assertNotIn("reasoning_effort", no_effort_api.kwargs)


if __name__ == "__main__":
    unittest.main()
