"""Tests for Agent context estimation and transcript compaction."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent import Agent, LLMResponse, Message, ToolCall
from agent.context import estimate_message_tokens


class CompactionLLM:
    def __init__(self) -> None:
        self.calls: list[tuple[list[Message], str | None]] = []

    async def complete(self, messages, tools=None, system_prompt=None):
        self.calls.append((list(messages), system_prompt))
        if system_prompt:
            return LLMResponse(content="summary of earlier discussion")
        return LLMResponse(content="final answer")


class ContextCompactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_compaction_replaces_jsonl_and_retains_recent_image_and_tool_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store_root = Path(temp) / "sessions"
            agent = Agent(
                model="test",
                workspace=temp,
                store_root=store_root,
                max_context=256,
                compact_rate=0.5,
            )
            llm = CompactionLLM()
            agent._llm = llm
            chat_id = agent.new_chat()
            history = agent.store.cache(chat_id)
            history.extend(
                message
                for index in range(6)
                for message in (
                    Message(role="user", content=f"old question {index}"),
                    Message(role="assistant", content=f"old answer {index}"),
                )
            )
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

            result = await agent._compact_history(chat_id, history, "next request")

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
