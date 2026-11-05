"""@ mention parsing regression tests for OneBot v11 and adapter-qq."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from nonebot_plugin_alconna.uniseg.segment import At

from plugin_chatbot.bridge import mentions


def _onebot_at(qq: str, **extra: str) -> SimpleNamespace:
    return SimpleNamespace(type="at", data={"qq": qq, **extra})


def _qq_mention(user_id: str, username: str | None = None) -> SimpleNamespace:
    data = {"user_id": user_id}
    if username is not None:
        data["username"] = username
    return SimpleNamespace(type="mention_user", data=data)


def _text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", data={"text": value})


class FakeEvent:
    def __init__(self, message, original=None) -> None:
        self._message = message
        self.original_message = message if original is None else original

    def get_message(self):
        return self._message


class FakeOneBot:
    def __init__(
        self, self_id: str = "10000", member=None, error: Exception | None = None
    ):
        self.self_id = self_id
        self.member = member
        self.error = error
        self.calls: list[dict] = []

    async def get_group_member_info(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.member


class FakeQQBot:
    def __init__(self, self_id: str = "bot-openid", member=None):
        self.self_id = self_id
        self.member = member
        self.calls: list[dict] = []

    async def get_group_member(self, **kwargs):
        self.calls.append(kwargs)
        return self.member


class MentionTargetTests(unittest.TestCase):
    def test_onebot_at_reads_qq(self) -> None:
        self.assertEqual(
            mentions.mention_target(_onebot_at("3399534625")), ("3399534625", "")
        )

    def test_unimessage_at_reads_target_and_display(self) -> None:
        segment = At("user", "3399534625", "冰佬")
        self.assertEqual(mentions.mention_target(segment), ("3399534625", "冰佬"))

    def test_qq_mention_reads_user_id_and_username(self) -> None:
        segment = _qq_mention("member-openid", "群友A")
        self.assertEqual(mentions.mention_target(segment), ("member-openid", "群友A"))

    def test_display_prefix_is_stripped(self) -> None:
        segment = At("user", "123", "@冰佬")
        self.assertEqual(mentions.mention_target(segment), ("123", "冰佬"))


class SegmentTextTests(unittest.TestCase):
    def test_onebot_at_uses_resolved_name(self) -> None:
        segment = _onebot_at("3399534625")
        self.assertEqual(
            mentions.segment_text(segment, "10000", {"3399534625": "冰佬"}), "@冰佬"
        )

    def test_onebot_at_falls_back_to_id(self) -> None:
        self.assertEqual(
            mentions.segment_text(_onebot_at("3399534625"), "10000"), "@3399534625"
        )

    def test_unimessage_at_keeps_embedded_name(self) -> None:
        self.assertEqual(
            mentions.segment_text(At("user", "3399534625", "冰佬"), "10000"), "@冰佬"
        )

    def test_qq_mention_keeps_embedded_username(self) -> None:
        self.assertEqual(
            mentions.segment_text(_qq_mention("m1", "群友A"), "bot"), "@群友A"
        )

    def test_bot_mention_becomes_self(self) -> None:
        self.assertEqual(mentions.segment_text(_onebot_at("10000"), "10000"), "@我")
        self.assertEqual(
            mentions.segment_text(
                SimpleNamespace(
                    type="mention_user",
                    data={"user_id": "m1", "is_bot": True},
                ),
                "bot",
            ),
            "@我",
        )

    def test_everyone_variants(self) -> None:
        self.assertEqual(mentions.segment_text(_onebot_at("all"), "10000"), "@全体成员")
        self.assertEqual(
            mentions.segment_text(SimpleNamespace(type="atall", data={}), "10000"),
            "@全体成员",
        )
        self.assertEqual(
            mentions.segment_text(
                SimpleNamespace(type="mention_everyone", data={}), "10000"
            ),
            "@全体成员",
        )

    def test_text_segment_passthrough(self) -> None:
        self.assertEqual(
            mentions.segment_text(_text("冰佬的歌好听捏"), "10000"), "冰佬的歌好听捏"
        )


class CollectTargetsTests(unittest.TestCase):
    def test_skips_named_bot_and_everyone(self) -> None:
        segments = [
            _onebot_at("1"),
            _onebot_at("10000"),
            _onebot_at("all"),
            At("user", "2", "已有昵称"),
            _qq_mention("3", "QQ 昵称"),
            _text("hi"),
        ]
        self.assertEqual(mentions.collect_targets(segments, "10000"), {"1"})


class InboundMessageTests(unittest.TestCase):
    def test_restores_reply_stripped_mention(self) -> None:
        original = [_onebot_at("3399534625"), _text(" 冰佬的歌好听捏")]
        message = [_text("冰佬的歌好听捏")]
        event = FakeEvent(message, original)
        self.assertIs(mentions.inbound_message(event, "10000"), original)

    def test_does_not_restore_only_bot_mention(self) -> None:
        original = [_onebot_at("10000"), _text(" hi")]
        message = [_text("hi")]
        event = FakeEvent(message, original)
        self.assertIs(mentions.inbound_message(event, "10000"), message)

    def test_does_not_restore_qq_self_mention(self) -> None:
        original = [
            SimpleNamespace(
                type="mention_user", data={"user_id": "bot-openid", "is_bot": True}
            ),
            _text(" hi"),
        ]
        message = [_text("hi")]
        event = FakeEvent(message, original)
        self.assertIs(mentions.inbound_message(event, "app-id"), message)

    def test_keeps_message_without_original(self) -> None:
        message = [_text("hi")]
        event = FakeEvent(message)
        self.assertIs(mentions.inbound_message(event, "10000"), message)


class ResolveNamesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        mentions.clear_cache()

    async def test_group_card_preferred_over_nickname(self) -> None:
        bot = FakeOneBot(member={"card": "群名片", "nickname": "昵称"})
        names = await mentions.resolve_names(bot, "group", "-100", {"42"})
        self.assertEqual(names, {"42": "群名片"})
        self.assertEqual(
            bot.calls, [{"group_id": "-100", "user_id": "42", "no_cache": False}]
        )

    async def test_second_lookup_hits_cache(self) -> None:
        bot = FakeOneBot(member={"nickname": "昵称"})
        await mentions.resolve_names(bot, "group", "-100", {"42"})
        await mentions.resolve_names(bot, "group", "-100", {"42"})
        self.assertEqual(len(bot.calls), 1)

    async def test_qq_adapter_member_api(self) -> None:
        bot = FakeQQBot(member={"username": "QQ昵称"})
        names = await mentions.resolve_names(
            bot, "group", "group-openid", {"member-openid"}
        )
        self.assertEqual(names, {"member-openid": "QQ昵称"})
        self.assertEqual(
            bot.calls,
            [{"group_openid": "group-openid", "member_openid": "member-openid"}],
        )

    async def test_failed_lookup_is_silent(self) -> None:
        bot = FakeOneBot(error=RuntimeError("api down"))
        names = await mentions.resolve_names(bot, "group", "-100", {"42"})
        self.assertEqual(names, {})

    async def test_empty_targets_skip_api(self) -> None:
        bot = FakeOneBot(member={"nickname": "昵称"})
        self.assertEqual(await mentions.resolve_names(bot, "group", "-100", set()), {})
        self.assertEqual(bot.calls, [])


if __name__ == "__main__":
    unittest.main()
