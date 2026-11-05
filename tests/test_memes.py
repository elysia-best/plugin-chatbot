"""表情包库单元测试：视觉标注解析、关键词索引落盘与检索。"""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from plugin_chatbot.bridge.memes import (
    MemeAnnotation,
    MemeLibrary,
    decode_image_data_url,
    image_mimetype,
    normalize_keywords,
    parse_annotation,
)

PNG = b"\x89PNG\r\n\x1a\nimage"
GIF = b"GIF89a-animated"


def make_annotation(
    name: str = "开心点赞",
    keywords: tuple[str, ...] = ("点赞", "开心", "Q版", "少女", "夸奖", "紫发"),
    summary: str = "紫发少女竖起大拇指夸奖",
    *,
    allowed: bool = True,
) -> MemeAnnotation:
    """构造一条等价于视觉模型输出的标注。"""
    return MemeAnnotation(
        allowed=allowed,
        name=name,
        keywords=keywords,
        summary=summary,
        reason="" if allowed else "低俗",
    )


class ImageDecodeTests(unittest.TestCase):
    def test_data_url_requires_valid_small_supported_image(self) -> None:
        data, suffix = decode_image_data_url(
            "data:image/png;base64," + base64.b64encode(PNG).decode(), 100
        )
        self.assertEqual((PNG, ".png"), (data, suffix))
        with self.assertRaises(ValueError):
            decode_image_data_url("data:image/png;base64,bm90YW5pbWFnZQ==", 100)
        with self.assertRaises(ValueError):
            decode_image_data_url("data:image/png;base64,AAAA", 2)


class MemeAnnotationTests(unittest.TestCase):
    def test_parse_annotation_accepts_fenced_json_and_keeps_5_to_8_keywords(
        self,
    ) -> None:
        content = (
            "```json\n"
            + json.dumps(
                {
                    "decision": "allow",
                    "name": "紫发点赞",
                    "keywords": ["点赞", "夸奖", "紫发", "Q版", "开心"],
                    "summary": "紫发少女竖起大拇指",
                    "reason": "安全",
                },
                ensure_ascii=False,
            )
            + "\n```"
        )
        annotation = parse_annotation(content, suffix=".png")

        self.assertTrue(annotation.allowed)
        self.assertEqual("紫发点赞", annotation.name)
        self.assertEqual(("点赞", "夸奖", "紫发", "Q版", "开心"), annotation.keywords)
        self.assertEqual("紫发少女竖起大拇指", annotation.summary)

    def test_parse_annotation_pads_short_keyword_lists_to_five(self) -> None:
        content = json.dumps(
            {
                "decision": "allow",
                "name": "鼓掌",
                "keywords": ["鼓掌", "庆祝"],
                "summary": "拍手庆祝",
            },
            ensure_ascii=False,
        )
        annotation = parse_annotation(content, suffix=".gif")

        self.assertEqual(5, len(annotation.keywords))
        self.assertIn("动图", annotation.keywords)
        self.assertEqual(("鼓掌", "庆祝"), annotation.keywords[:2])

    def test_parse_annotation_caps_keywords_at_eight_and_deduplicates(self) -> None:
        keywords = ["标签" + str(index) for index in range(12)]
        annotation = parse_annotation(
            json.dumps(
                {"decision": "allow", "name": "测试", "keywords": [*keywords, "标签0"]},
                ensure_ascii=False,
            ),
            suffix=".png",
        )

        self.assertEqual(8, len(annotation.keywords))
        self.assertEqual(len(set(annotation.keywords)), len(annotation.keywords))

    def test_parse_annotation_rejects_invalid_or_unsafe_output(self) -> None:
        cases = (
            "not json",
            '{"decision":"maybe"}',
            '{"decision":"allow","name":""}',
            "[]",
        )
        for content in cases:
            with self.subTest(content=content), self.assertRaises(
                (ValueError, TypeError)
            ):
                parse_annotation(content, suffix=".png")

    def test_normalize_keywords_rejects_non_iterable_input(self) -> None:
        self.assertEqual((), normalize_keywords(None, name="", summary="", suffix=".png"))

    def test_image_mimetype_maps_each_supported_suffix(self) -> None:
        expected = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        for suffix, mimetype in expected.items():
            with self.subTest(suffix=suffix):
                self.assertEqual(mimetype, image_mimetype(suffix))


class MemeLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.library = MemeLibrary(Path(self._temp.name) / "memes", 1024)

    def test_save_writes_image_and_keyword_index_atomically(self) -> None:
        first = self.library.save(PNG, ".png", annotation=make_annotation())
        second = self.library.save(PNG, ".png", annotation=make_annotation())

        self.assertEqual("开心点赞.png", first.name)
        self.assertEqual("开心点赞-2.png", second.name)
        rows = self.library.list()
        self.assertEqual(2, len(rows))
        self.assertEqual(
            {"name", "file", "keywords", "summary", "bytes"}, set(rows[0])
        )
        self.assertEqual("开心点赞", rows[0]["name"])
        self.assertIn("点赞", rows[0]["keywords"])
        self.assertEqual(len(PNG), rows[0]["bytes"])
        self.assertTrue(self.library.index_path.is_file())

    def test_index_survives_library_reload(self) -> None:
        self.library.save(GIF, ".gif", annotation=make_annotation(name="俏皮眨眼"))
        reopened = MemeLibrary(self.library.root, 1024)

        self.assertEqual("俏皮眨眼", reopened.list()[0]["name"])
        self.assertEqual(6, len(reopened.list()[0]["keywords"]))

    def test_search_ranks_exact_keyword_matches_first(self) -> None:
        self.library.save(PNG, ".png", annotation=make_annotation(name="开心点赞"))
        self.library.save(
            GIF,
            ".gif",
            annotation=make_annotation(
                name="无奈摊手",
                keywords=("摊手", "无奈", "叹气", "疲惫", "拒绝", "灰心"),
                summary="摊手表示无可奈何",
            ),
        )
        rows = self.library.search(["点赞"])

        self.assertEqual(1, len(rows))
        self.assertEqual("开心点赞", rows[0]["name"])
        self.assertIn("keywords", rows[0])
        self.assertIn("summary", rows[0])

    def test_search_accepts_comma_separated_string_and_returns_empty_on_miss(
        self,
    ) -> None:
        self.library.save(PNG, ".png", annotation=make_annotation())
        self.assertEqual(1, len(self.library.search("点赞，夸奖")))
        self.assertEqual([], self.library.search(["不存在的情绪"]))

    def test_search_without_query_returns_bounded_catalog(self) -> None:
        for index in range(4):
            self.library.save(
                PNG,
                ".png",
                annotation=make_annotation(name=f"表情{index}"),
            )
        self.assertEqual(3, len(self.library.search([], limit=3)))

    def test_resolve_accepts_short_name_and_confines_paths(self) -> None:
        path = self.library.save(PNG, ".png", annotation=make_annotation())

        self.assertEqual(path, self.library.resolve("开心点赞"))
        self.assertEqual(path, self.library.resolve("开心点赞.png"))
        with self.assertRaises(ValueError):
            self.library.resolve("../outside.png")
        with self.assertRaises(ValueError):
            self.library.resolve("不存在")

    def test_legacy_files_without_index_are_backfilled(self) -> None:
        (self.library.root / "老表情.gif").write_bytes(GIF)
        rows = self.library.list()

        self.assertEqual(1, len(rows))
        self.assertEqual("老表情", rows[0]["name"])
        self.assertGreaterEqual(len(rows[0]["keywords"]), 5)

    def test_rejected_annotation_is_never_written(self) -> None:
        with self.assertRaises(ValueError):
            self.library.save(PNG, ".png", annotation=make_annotation(allowed=False))
        self.assertEqual([], self.library.list())


if __name__ == "__main__":
    unittest.main()
