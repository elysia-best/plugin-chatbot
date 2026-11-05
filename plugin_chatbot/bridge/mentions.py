"""Resolve @-mention targets and display names across chat adapters.

OneBot v11 的 ``at`` 段只携带 QQ 号，昵称必须另行查询群成员资料；而 alconna 的
``UniMessage`` 又把该段转成 ``At(flag, target, display)``。本模块统一两种结构，
并对查询结果做短时缓存，避免每条消息都打一次平台 API。
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Iterable

MENTION_NAME_TTL_SECONDS = 300.0
MENTION_LOOKUP_TIMEOUT_SECONDS = 3.0
MENTION_CACHE_MAX_ENTRIES = 2048
_ALL_TARGETS = frozenset({"", "0", "all"})

_name_cache: dict[tuple[str, str, str, str], tuple[float, str]] = {}


def _data_of(segment: Any) -> dict[str, Any]:
    data = getattr(segment, "data", None)
    return data if isinstance(data, dict) else {}


def mention_target(segment: Any) -> tuple[str, str]:
    """Return ``(target_id, embedded_name)`` for an at-like segment.

    ``target_id`` 兼容 OneBot 原生 ``data["qq"]`` 与 UniMessage ``At.target``；
    ``embedded_name`` 优先取段内自带的显示名，取不到时返回空串，由调用方查 API。
    """
    data = _data_of(segment)
    target = (
        data.get("qq")
        or data.get("user_id")
        or data.get("id")
        or getattr(segment, "target", "")
        or ""
    )
    display = (
        data.get("username")
        or data.get("name")
        or getattr(segment, "display", "")
        or ""
    )
    name = str(display).strip()
    if name.startswith("@"):
        name = name.lstrip("@").strip()
    return str(target).strip(), name


def segment_text(  # noqa: PLR0911 - 每种段类型都是独立分支，扁平返回比嵌套更清晰
    segment: Any,
    bot_id: str,
    names: dict[str, str] | None = None,
) -> str:
    """Render one unified segment as plain text, keeping @ information."""
    kind = str(getattr(segment, "type", ""))
    data = _data_of(segment)
    if kind == "text":
        return str(data.get("text", ""))
    if kind in {"at", "mention_user"}:
        target_id, display = mention_target(segment)
        if bool(data.get("is_bot")) or (target_id and target_id == bot_id):
            return "@我"
        if target_id in _ALL_TARGETS:
            return "@全体成员"
        name = display or (names or {}).get(target_id, "")
        if name:
            return f"@{name}"
        return f"@{target_id}" if target_id else "@"
    if kind in {"atall", "mention_everyone"}:
        return "@全体成员"
    if kind == "group_mention_user":
        return "@我" if bool(data.get("is_you")) else ""
    return ""


def collect_at_ids(segments: Iterable[Any]) -> set[str]:
    """Return every concrete at-target id in a message, regardless of naming."""
    targets: set[str] = set()
    for segment in segments:
        if str(getattr(segment, "type", "")) not in {"at", "mention_user"}:
            continue
        # adapter-qq flags its own self-mention; it is stripped from the visible
        # message on purpose and must not trigger an original-message fallback.
        if bool(_data_of(segment).get("is_bot")):
            continue
        target_id, _ = mention_target(segment)
        if target_id and target_id not in _ALL_TARGETS:
            targets.add(target_id)
    return targets


def inbound_message(event: Any, bot_id: str) -> Any:
    """Restore at-segments an adapter stripped, without adding noise.

    OneBot v11 removes the "@被回复者" segment on reply; adapter-qq instead inserts
    a bot self-mention into ``original_message``. Fall back to the original only
    when it carries a non-bot mention that the visible message lost.
    """
    message = event.get_message()
    original = getattr(event, "original_message", None)
    if original is None or original is message:
        return message
    try:
        lost = collect_at_ids(original) - collect_at_ids(message)
    except (AttributeError, TypeError):
        return message
    return original if lost - {bot_id} else message


def collect_targets(
    segments: Iterable[Any],
    bot_id: str,
    names: dict[str, str] | None = None,
) -> set[str]:
    """Collect at-target ids that still need a display name."""
    targets: set[str] = set()
    for segment in segments:
        if str(getattr(segment, "type", "")) not in {"at", "mention_user"}:
            continue
        target_id, display = mention_target(segment)
        if not target_id or target_id in _ALL_TARGETS or target_id == bot_id:
            continue
        if display or (names or {}).get(target_id):
            continue
        targets.add(target_id)
    return targets


async def resolve_names(
    bot: Any,
    kind: str,
    peer_id: str,
    targets: set[str],
) -> dict[str, str]:
    """Look up member names for at-targets, using a short-lived cache."""
    if not targets:
        return {}
    now = time.monotonic()
    _prune(now)
    bot_id = str(getattr(bot, "self_id", ""))
    resolved: dict[str, str] = {}
    pending: list[str] = []
    for user_id in targets:
        cached = _name_cache.get((bot_id, kind, peer_id, user_id))
        if cached is not None and now - cached[0] < MENTION_NAME_TTL_SECONDS:
            resolved[user_id] = cached[1]
        else:
            pending.append(user_id)
    if pending:
        results = await asyncio.gather(
            *(_lookup(bot, kind, peer_id, user_id) for user_id in pending)
        )
        for user_id, name in zip(pending, results, strict=True):
            if not name:
                continue
            _name_cache[(bot_id, kind, peer_id, user_id)] = (now, name)
            resolved[user_id] = name
    return resolved


async def _lookup(bot: Any, kind: str, peer_id: str, user_id: str) -> str:
    if kind == "group" and peer_id:
        # OneBot v11 / v12 style group member API.
        member = await _call(
            bot,
            "get_group_member_info",
            group_id=peer_id,
            user_id=user_id,
            no_cache=False,
        )
        name = _pick(member, ("card", "nickname", "name"))
        if name:
            return name
        # QQ official adapter: openid based member API.
        member = await _call(
            bot,
            "get_group_member",
            group_openid=peer_id,
            member_openid=user_id,
        )
        name = _pick(member, ("username", "nickname", "card", "name"))
        if name:
            return name
    stranger = await _call(bot, "get_stranger_info", user_id=user_id, no_cache=False)
    return _pick(stranger, ("nickname", "username", "name", "card"))


async def _call(bot: Any, method: str, **kwargs: Any) -> Any:
    getter = getattr(bot, method, None)
    if not callable(getter):
        return None
    try:
        result = getter(**kwargs)
        if not hasattr(result, "__await__"):
            return result
        return await asyncio.wait_for(
            cast("Any", result), MENTION_LOOKUP_TIMEOUT_SECONDS
        )
    except Exception:  # noqa: BLE001 - 名称只是装饰，查询失败不应影响消息处理
        return None


def _pick(value: Any, keys: tuple[str, ...]) -> str:
    if isinstance(value, dict):
        for key in keys:
            name = value.get(key)
            if isinstance(name, str) and name.strip():
                return name.strip()
    for key in keys:
        name = getattr(value, key, None)
        if isinstance(name, str) and name.strip():
            return name.strip()
    return ""


def _prune(now: float) -> None:
    if len(_name_cache) < MENTION_CACHE_MAX_ENTRIES:
        return
    for key, (stamp, _) in list(_name_cache.items()):
        if now - stamp >= MENTION_NAME_TTL_SECONDS:
            _name_cache.pop(key, None)
    if len(_name_cache) >= MENTION_CACHE_MAX_ENTRIES:
        _name_cache.clear()


def clear_cache() -> None:
    """Drop cached names; used by management actions and tests."""
    _name_cache.clear()
