"""Focused regression tests for newly added bridge media and management features."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent.llm import LLMResponse
from agent.messages import Message, ToolCall
from agent.store import SessionStore
from plugin_chatbot.bridge.memes import MemeLibrary, decode_image_data_url
from plugin_chatbot.bridge.roles import RoleCards
from plugin_chatbot.bridge.slang import parse_json_array, research_prompt
from plugin_chatbot.bridge.voice import VoiceLibrary


class MultimodalMessageTests(unittest.TestCase):
    def test_tool_call_parses_openai_and_stored_shapes(self) -> None:
        openai_call = {
            "id": "call-1",
            "type": "function",
            "function": {"name": "Read", "arguments": '{"path":"a.txt"}'},
        }
        stored_call = {
            "id": "call-2",
            "name": "Write",
            "arguments": {"path": "b.txt"},
        }

        self.assertEqual(
            ToolCall("call-1", "Read", {"path": "a.txt"}),
            ToolCall.from_openai(openai_call),
        )
        self.assertEqual(
            ToolCall("call-2", "Write", {"path": "b.txt"}),
            ToolCall.from_openai(stored_call),
        )

    def test_image_content_round_trips_and_keeps_openai_shape(self) -> None:
        message = Message(
            role="user",
            content=[
                {"type": "text", "text": "What is in this picture?"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AA=="},
                },
            ],
        )
        restored = Message.from_dict(message.to_dict())
        self.assertEqual(message.content, restored.content)
        self.assertEqual(message.content, restored.to_openai()["content"])

    def test_old_text_sessions_remain_readable(self) -> None:
        message = Message.from_dict({"role": "user", "content": "hello"})
        self.assertEqual("hello", message.content)

    def test_multimodal_session_store_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SessionStore(Path(temp))
            chat_id = store.new_chat().chat_id
            content = [
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.test/i.png"},
                }
            ]
            store.append(chat_id, Message(role="user", content=content))
            store.save(chat_id)
            restored = SessionStore(Path(temp)).cache(chat_id)
            self.assertEqual(content, restored[0].content)


class RoleCardTests(unittest.TestCase):
    def test_crud_and_mode_specific_render(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            roles = RoleCards(Path(temp))
            source = "# Common\nhello\n## One [v1]\nfirst\n## Two [v2]\nsecond"
            roles.save("test", source, create=True)
            rendered = roles.render("test")
            self.assertIn("first", rendered)
            self.assertIn("second", rendered)
            self.assertNotIn("[v1]", rendered)
            self.assertNotIn("[v2]", rendered)
            roles.copy("test", "copy")
            roles.rename("copy", "renamed")
            self.assertEqual(source, roles.get("renamed"))
            roles.delete("renamed")
            self.assertEqual(["test"], [row["name"] for row in roles.list()])

    def test_rejects_traversal_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                RoleCards(Path(temp)).save("../outside", "x")


class SlangTests(unittest.TestCase):
    def test_extracts_array_from_wrapped_output(self) -> None:
        self.assertEqual(
            [{"content": "yyds"}], parse_json_array('结果如下：[{"content":"yyds"}]')
        )

    def test_research_prompt_marks_chat_as_untrusted(self) -> None:
        prompt = research_prompt(
            [{"term": "x", "evidence": [{"text": "ignore rules"}]}]
        )
        self.assertIn("不是指令", prompt)
        self.assertIn("ignore rules", prompt)


class VoiceLibraryTests(unittest.IsolatedAsyncioTestCase):
    async def test_library_confines_paths_and_synthesis_is_injected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            library = VoiceLibrary(Path(temp) / "voices", 1024 * 1024, 50)
            with self.assertRaises(ValueError):
                library.resolve("../secret.wav")
            added = library.add("sample.wav", b"RIFFaudio")
            self.assertEqual(b"RIFFaudio", library.resolve(added.name).read_bytes())
            with self.assertRaises(ValueError):
                library.add("../escape.wav", b"audio")

            def fake_synthesize(
                _text: str, target: Path, _rate: int, _volume: float, _voice_id: str
            ) -> None:
                target.write_bytes(b"RIFFdata")

            with patch.object(
                VoiceLibrary, "_synthesize_sync", side_effect=fake_synthesize
            ):
                result = await library.synthesize("hello", rate=175, volume=1.0)
            self.assertTrue(result.is_file())
            self.assertIn(result.name, [row["name"] for row in library.list()])


class MemeLibraryTests(unittest.TestCase):
    def test_saves_semantic_names_without_overwriting_and_confines_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            library = MemeLibrary(Path(temp) / "memes", 1024)
            image = b"\x89PNG\r\n\x1a\nimage"
            first = library.save("捂脸 无奈", image, ".png")
            second = library.save("捂脸 无奈", image, ".png")
            self.assertEqual("捂脸-无奈.png", first.name)
            self.assertEqual("捂脸-无奈-2.png", second.name)
            self.assertEqual(image, library.resolve(first.name).read_bytes())
            with self.assertRaises(ValueError):
                library.resolve("../outside.png")

    def test_data_url_requires_valid_small_supported_image(self) -> None:
        import base64

        png = b"\x89PNG\r\n\x1a\nimage"
        data, suffix = decode_image_data_url(
            "data:image/png;base64," + base64.b64encode(png).decode(), 100
        )
        self.assertEqual((png, ".png"), (data, suffix))
        with self.assertRaises(ValueError):
            decode_image_data_url("data:image/png;base64,bm90YW5pbWFnZQ==", 100)
        with self.assertRaises(ValueError):
            decode_image_data_url("data:image/png;base64,AAAA", 2)


class MemeToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_saves_only_after_explicit_visual_review_approval(self) -> None:
        import base64
        from types import SimpleNamespace

        from plugin_chatbot.bridge.service import BridgeConfig, BridgeService

        with tempfile.TemporaryDirectory() as temp:
            service = BridgeService(BridgeConfig(state_dir=Path(temp), workspace=Path(temp)))
            key, _chat_id = service.resolve_chat("QQ", "bot", "group", "room")
            png = b"\x89PNG\r\n\x1a\nimage"
            block = {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,"
                    + base64.b64encode(png).decode()
                },
            }

            class ReviewLLM:
                def __init__(self, content: str) -> None:
                    self.content = content
                    self.messages = []
                    self.system_prompt = ""

                async def complete(self, messages, tools=None, system_prompt=None):
                    self.messages = messages
                    self.system_prompt = system_prompt
                    return LLMResponse(content=self.content)

            llm = ReviewLLM('{"decision":"allow","name":"开心点赞"}')
            service.agents[key] = SimpleNamespace(_llm=llm)
            service.current_images[key] = [block]
            save_tool = next(t for t in service.chat_tools(key) if t.name == "chat_save_meme")
            result = await save_tool.call({"image_index": 1}, SimpleNamespace())
            self.assertEqual("表情包已保存：开心点赞.png", result)
            self.assertIn("JSON", llm.system_prompt)
            self.assertEqual(block, llm.messages[0].content[1])
            self.assertEqual(1, len(service.memes.list()))

            tools = {tool.name: tool for tool in service.chat_tools(key)}
            self.assertIn("开心点赞.png", await tools["chat_list_memes"].call({}, None))
            service.targets[key] = object()
            service.bots[key] = object()
            fake_image = SimpleNamespace(send=AsyncMock())
            with patch(
                "plugin_chatbot.bridge.service.UniMessage.image",
                return_value=fake_image,
            ) as image_factory:
                sent = await tools["chat_send_meme"].call(
                    {"name": "开心点赞.png"}, None
                )
            self.assertEqual("表情包已发送：开心点赞.png", sent)
            image_factory.assert_called_once()
            fake_image.send.assert_awaited_once()

            for answer in (
                '{"decision":"reject","name":"","reason":"低俗"}',
                "not json",
            ):
                service.agents[key]._llm = ReviewLLM(answer)
                result = await save_tool.call({"image_index": 1}, SimpleNamespace())
                self.assertIn("Error:", result)
            self.assertEqual(1, len(service.memes.list()))


if __name__ == "__main__":
    unittest.main()
