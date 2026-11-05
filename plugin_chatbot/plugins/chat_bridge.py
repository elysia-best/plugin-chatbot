"""NoneBot message entrypoint and authenticated management API."""

from __future__ import annotations

import asyncio
import base64
import binascii
import math
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from nonebot import get_driver, get_plugin_config, logger, on_message
from nonebot.adapters import Bot, Event  # noqa: TC002
from nonebot_plugin_alconna import Image, Target, UniMessage, get_target, image_fetch
from pydantic import BaseModel

from plugin_chatbot.bridge import BridgeConfig, BridgeService
from plugin_chatbot.bridge.service import (
    IncomingMessage,
    normalize_model_records,
    positive_context_length,
)

if TYPE_CHECKING:
    from plugin_chatbot.bridge.service import Mode

MAX_ROLE_CHARS = 6000
MAX_INITIAL_PROMPT_CHARS = 4000
MAX_SLANG_TERM_CHARS = 100
MAX_IMAGES_PER_MESSAGE = 8
MAX_MCP_URL_CHARS = 2000
MESSAGE_LOG_PREVIEW_CHARS = 120


class Settings(BaseModel):
    """Configuration read from NoneBot's plugin configuration."""

    agent_workspace: str = ""
    bridge_state_dir: str = ""
    bridge_mode: str = "chat"
    bridge_max_message_chars: int = 500
    bridge_max_messages_per_minute: int = 6
    bridge_group_batch_seconds: float = 1.0
    max_context: int = 262_144
    compact_rate: float = 0.8
    bridge_max_media_bytes: int = 8 * 1024 * 1024
    bridge_console_token: str = ""
    bridge_mcp_server_url: str = ""
    bridge_voice_dir: str = ""
    bridge_voice_max_bytes: int = 20 * 1024 * 1024
    bridge_voice_max_text_chars: int = 500
    bridge_voice_rate: int = 175
    bridge_voice_volume: float = 1.0
    bridge_voice_id: str = ""
    bridge_voice_sends_per_hour: int = 20
    bridge_slang_enabled: bool = True
    bridge_slang_min_messages: int = 10
    bridge_slang_cooldown_seconds: int = 300
    bridge_input_cost_per_million: float = 0.0
    bridge_output_cost_per_million: float = 0.0


_settings = get_plugin_config(Settings)
_root = Path(__file__).resolve().parents[2]
_workspace = Path(_settings.agent_workspace or _root).resolve()
_state_dir = Path(_settings.bridge_state_dir or (_root / ".agent" / "bridge")).resolve()
_service = BridgeService(
    BridgeConfig(
        state_dir=_state_dir,
        workspace=_workspace,
        mode=cast(
            "Mode",
            _settings.bridge_mode
            if _settings.bridge_mode in {"chat", "agent"}
            else "chat",
        ),
        max_message_chars=max(100, min(_settings.bridge_max_message_chars, 4000)),
        max_messages_per_minute=max(
            1, min(_settings.bridge_max_messages_per_minute, 60)
        ),
        group_batch_seconds=max(0.0, min(_settings.bridge_group_batch_seconds, 10.0)),
        max_context=max(4096, min(_settings.max_context, 2_000_000)),
        compact_rate=max(0.1, min(_settings.compact_rate, 0.99)),
        max_media_bytes=max(
            1024, min(_settings.bridge_max_media_bytes, 32 * 1024 * 1024)
        ),
        console_token=_settings.bridge_console_token,
        mcp_server_url=_settings.bridge_mcp_server_url,
        voice_dir=Path(_settings.bridge_voice_dir).resolve()
        if _settings.bridge_voice_dir
        else None,
        voice_max_bytes=max(1024, _settings.bridge_voice_max_bytes),
        voice_max_text_chars=max(1, min(_settings.bridge_voice_max_text_chars, 2000)),
        voice_rate=max(80, min(_settings.bridge_voice_rate, 300)),
        voice_volume=max(0.0, min(_settings.bridge_voice_volume, 1.0)),
        voice_id=_settings.bridge_voice_id,
        voice_sends_per_hour=max(1, min(_settings.bridge_voice_sends_per_hour, 500)),
        slang_enabled=_settings.bridge_slang_enabled,
        slang_min_messages=max(3, min(_settings.bridge_slang_min_messages, 100)),
        slang_cooldown_seconds=max(
            30, min(_settings.bridge_slang_cooldown_seconds, 86400)
        ),
        input_cost_per_million=max(0.0, _settings.bridge_input_cost_per_million),
        output_cost_per_million=max(0.0, _settings.bridge_output_cost_per_million),
    )
)

_message = on_message(priority=20, block=False)


async def _message_content(
    message: Any, event: Event, bot: Bot
) -> tuple[str, list[dict[str, Any]]]:
    try:
        unified = UniMessage.of(message, bot=bot)
        plain = unified.extract_plain_text().strip()
    except (AttributeError, TypeError):
        unified = UniMessage()
        plain = str(message).strip()
    media_types = {str(getattr(segment, "type", "")) for segment in unified}
    placeholders = [
        label
        for kind, label in (
            ("audio", "[收到音频；当前桥接未配置语音转写]"),
            ("voice", "[收到语音；当前桥接未配置语音转写]"),
            ("video", "[收到视频；当前模型接口不能读取视频内容]"),
            ("file", "[收到文件；当前桥接未配置文件解析]"),
        )
        if kind in media_types
    ]
    content: list[dict[str, Any]] = []
    media_bytes = 0
    for segment in unified:
        if not isinstance(segment, Image) and getattr(segment, "type", "") != "image":
            continue
        if len(content) >= MAX_IMAGES_PER_MESSAGE:
            placeholders.append("[图片数量超过单条消息上限]")
            continue
        try:
            raw_bytes = await image_fetch(event, bot, {}, segment)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chat bridge image fetch failed: {}", type(exc).__name__)
            raw_bytes = None
        if not raw_bytes:
            placeholders.append("[图片不可读取]")
            continue
        if (
            len(raw_bytes) > _service.config.max_media_bytes
            or media_bytes + len(raw_bytes) > _service.config.max_media_bytes
        ):
            placeholders.append("[图片超过媒体大小限制]")
            continue
        media_bytes += len(raw_bytes)
        mimetype = getattr(segment, "mimetype", None) or "image/png"
        if not mimetype.startswith("image/"):
            mimetype = "image/png"
        encoded = base64.b64encode(raw_bytes).decode("ascii")
        uri = f"data:{mimetype};base64,{encoded}"
        content.append({"type": "image_url", "image_url": {"url": uri}})
    return " ".join(part for part in [plain, *placeholders] if part), content


def _name_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    keys = (
        "name",
        "title",
        "nickname",
        "user_name",
        "display_name",
        "username",
        "card",
        "member_name",
        "bot_name",
        "group_name",
        "guild_name",
        "channel_name",
    )
    if isinstance(value, dict):
        for key in keys:
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    for key in keys:
        nested = getattr(value, key, None)
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return ""


def _group_name(event: Event, target: Target) -> str:
    getter = getattr(event, "get_group_name", None)
    if callable(getter):
        try:
            name = _name_value(getter())
        except (AttributeError, NotImplementedError, TypeError, ValueError):
            name = ""
        if name:
            return name
    keys = ("group_name", "guild_name", "channel_name", "group", "guild", "channel")
    for source in (
        event,
        getattr(event, "sender", None),
        getattr(event, "group", None),
        getattr(event, "guild", None),
        getattr(event, "channel", None),
        target.extra,
    ):
        for key in keys:
            value = (
                source.get(key)
                if isinstance(source, dict)
                else getattr(source, key, None)
            )
            name = _name_value(value)
            if name:
                return name
    return ""


def _bot_name(bot: Bot) -> str:
    """Best-effort display name across NoneBot adapters."""
    candidates: list[Any] = [
        getattr(bot, "nickname", None),
        getattr(bot, "display_name", None),
        getattr(bot, "name", None),
        getattr(bot, "user_name", None),
        getattr(bot, "user", None),
        getattr(bot, "config", None),
    ]
    for value in candidates:
        name = _name_value(value)
        if name:
            return name
    return str(getattr(bot, "self_id", ""))


def _user_name(event: Event, user_id: str) -> str:
    getter = getattr(event, "get_user_name", None)
    if callable(getter):
        try:
            name = _name_value(getter())
        except (AttributeError, NotImplementedError, TypeError, ValueError):
            name = ""
        if name:
            return name
    for source in (
        getattr(event, "sender", None),
        getattr(event, "user", None),
        getattr(event, "member", None),
        getattr(event, "author", None),
        event,
    ):
        name = _name_value(source)
        if name:
            return name
    return user_id


async def _resolve_bot_name(bot: Bot) -> str:
    name = _bot_name(bot)
    if name and name != str(getattr(bot, "self_id", "")):
        return name
    getter = getattr(bot, "get_login_info", None)
    if callable(getter):
        try:
            result = getter()
            if hasattr(result, "__await__"):
                result = await cast("Any", result)
            name = _name_value(result)
        except (AttributeError, NotImplementedError, TypeError, ValueError):
            name = ""
    return name or str(getattr(bot, "self_id", ""))


async def _resolve_group_name(bot: Bot, group_id: str, current: str) -> str:
    if current:
        return current
    getter = getattr(bot, "get_group_info", None)
    if callable(getter):
        try:
            result = getter(group_id=group_id)
            if hasattr(result, "__await__"):
                result = await cast("Any", result)
            name = _name_value(result)
            if name:
                return name
        except (AttributeError, NotImplementedError, TypeError, ValueError):
            pass
    return group_id


@_message.handle()
async def _handle_message(bot: Bot, event: Event) -> None:  # noqa: C901
    user_id = str(event.get_user_id())
    if user_id == str(getattr(bot, "self_id", "")):
        return
    try:
        target: Target = get_target(event, bot)
    except (AttributeError, TypeError, ValueError):
        return
    kind = "private" if target.private else "group"
    peer_id = target.id if kind == "private" else (target.parent_id or target.id)
    user_name = _user_name(event, user_id)
    event_id_method = getattr(event, "get_message_id", None)
    event_id = str(event_id_method() if callable(event_id_method) else "")
    message = event.get_message()
    text, content = await _message_content(message, event, bot)
    normalized_text = " ".join(text.split())
    preview = normalized_text[:MESSAGE_LOG_PREVIEW_CHARS]
    event_type = getattr(getattr(event, "__type__", None), "value", None)
    logger.info(
        "Chat bridge inbound: platform={} event_type={} bot_id={} kind={} "
        "user_id={} target_id={} message={!r}{}",
        bot.adapter.get_name(),
        event_type or event.get_type(),
        bot.self_id,
        kind,
        user_id,
        peer_id,
        preview,
        "..." if len(normalized_text) > MESSAGE_LOG_PREVIEW_CHARS else "",
    )
    if not text and not content:
        return
    reply_to = ""
    for segment in message:
        if getattr(segment, "type", "") == "reply":
            reply_to = str(getattr(segment, "data", {}).get("id", ""))
            break
    incoming = IncomingMessage(
        bot=bot,
        platform=bot.adapter.get_name(),
        bot_id=str(bot.self_id),
        kind=kind,
        peer_id=peer_id,
        user_id=user_id,
        user_name=user_name,
        text=text,
        target=target,
        event_id=event_id,
        reply_to=reply_to,
        content=content,
        group_name=_group_name(event, target) if kind == "group" else "",
    )
    account = _service.account_config(incoming.platform, incoming.bot_id)
    bot_name = await _resolve_bot_name(bot)
    if account is None:
        _service.state.data["accounts"].append(
            {
                "id": secrets.token_hex(8),
                "platform": incoming.platform,
                "adapter": incoming.platform,
                "bot_id": incoming.bot_id,
                "name": bot_name,
                "name_source": "adapter" if bot_name != incoming.bot_id else "fallback",
                "enabled": True,
                "provider_id": "",
                "model": "",
                "reasoning_effort": "",
                "temperature_enabled": True,
                "temperature": 0.7,
                "context_length": None,
                "persona_role": None,
                "persona_prompt": "",
                "enabled_tools": None,
                "admins": [],
                "whitelist": [],
                "blacklist": [],
                "private_users": [],
                "groups": [],
            }
        )
        _service.state.save()
    elif account.get("name_source") != "manual" and (
        not account.get("name") or account.get("name_source") == "fallback"
    ):
        account["name"] = bot_name
        account["name_source"] = (
            "adapter" if bot_name != incoming.bot_id else "fallback"
        )
        _service.state.save()
    if kind == "group" and not incoming.group_name:
        incoming.group_name = await _resolve_group_name(bot, incoming.peer_id, "")
    if (
        kind == "group"
        and _service.group_config(incoming.platform, incoming.bot_id, incoming.peer_id)
        is None
    ):
        _service.state.data["groups"].append(
            {
                "id": secrets.token_hex(8),
                "platform": incoming.platform,
                "bot_id": incoming.bot_id,
                "group_id": incoming.peer_id,
                "name": incoming.group_name or incoming.peer_id,
                "name_source": (
                    "adapter" if incoming.group_name != incoming.peer_id else "fallback"
                ),
                "enabled": True,
                "provider_id": "",
                "system_prompt": "",
                "reply_frequency": "balanced",
                "reasoning_effort": "",
                "model": "",
                "cost_limit": None,
                "enabled_tools": None,
                "tools": {"skills": [], "mcps": [], "rules": []},
            }
        )
        _service.state.save()
    elif kind == "group":
        group = _service.group_config(
            incoming.platform, incoming.bot_id, incoming.peer_id
        )
        if group and group.get("name_source") != "manual" and incoming.group_name:
            group["name"] = incoming.group_name
            group["name_source"] = "adapter"
            _service.state.save()
    response = await _service.handle_message(incoming)
    if response and not await _service.send_reply(incoming, response):
        logger.warning("Chat bridge suppressed reply due to outbound rate limit")


def _console_token() -> str:
    configured = _settings.bridge_console_token.strip()
    if configured:
        return configured
    token_path = _state_dir / "console-token"
    try:
        token = token_path.read_text(encoding="utf-8").strip()
        if token:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    token_path.write_text(token, encoding="utf-8")
    return token


async def _authorize(x_console_token: str = Header(default="")) -> None:
    if not secrets.compare_digest(x_console_token, _console_token()):
        raise HTTPException(status_code=401, detail="Unauthorized")


_driver = get_driver()
_api = FastAPI()


def _new_id() -> str:
    return secrets.token_hex(8)


def _find_row(rows: list[dict[str, Any]], row_id: str) -> dict[str, Any] | None:
    return next((row for row in rows if str(row.get("id")) == row_id), None)


def _memory_interval(value: Any) -> int:
    try:
        return max(1, min(1000, int(value)))
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(status_code=422, detail="Invalid memory interval") from None


def _temperature_value(value: Any) -> float:
    try:
        temperature = float(value)
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(status_code=422, detail="Invalid temperature") from None
    if not math.isfinite(temperature) or not 0 <= temperature <= 2:
        raise HTTPException(status_code=422, detail="Temperature must be between 0 and 2")
    return temperature


@_api.get("/api/accounts", dependencies=[Depends(_authorize)])
async def _accounts() -> list[dict[str, Any]]:
    return _service.state.data["accounts"]


@_api.post("/api/accounts", dependencies=[Depends(_authorize)])
async def _create_account(body: dict[str, Any]) -> dict[str, Any]:
    platform = str(body.get("platform") or body.get("adapter") or "").strip()
    bot_id = str(body.get("bot_id", "")).strip()
    if not platform or not bot_id:
        raise HTTPException(status_code=422, detail="platform and bot_id are required")
    if _service.account_config(platform, bot_id):
        raise HTTPException(status_code=409, detail="Account already exists")
    row = {
        "id": _new_id(),
        "platform": platform,
        "adapter": str(body.get("adapter") or platform),
        "bot_id": bot_id,
        "name": str(body.get("name") or bot_id)[:120],
        "name_source": "manual" if body.get("name") else "fallback",
        "enabled": bool(body.get("enabled", True)),
        "provider_id": str(body.get("provider_id") or ""),
        "model": str(body.get("model") or ""),
        "reasoning_effort": str(body.get("reasoning_effort") or "medium"),
        "temperature_enabled": bool(body.get("temperature_enabled", True)),
        "temperature": _temperature_value(body.get("temperature", 0.7)),
        "context_length": positive_context_length(body.get("context_length")),

        "persona_role": str(body.get("persona_role") or "") or None,
        "persona_prompt": str(body.get("persona_prompt") or ""),
        "enabled_tools": body.get("enabled_tools")
        if isinstance(body.get("enabled_tools"), list)
        else None,
        "memory_enabled": bool(body.get("memory_enabled", True)),
        "memory_interval": _memory_interval(body.get("memory_interval", 50) or 50),
        "memory_buffer": [],
        "admins": [],
        "whitelist": [],
        "blacklist": [],
        "private_users": [],
        "groups": [],
    }
    _service.state.data["accounts"].append(row)
    _service.state.save()
    _service.agents.clear()
    return row


@_api.put("/api/accounts/{row_id}", dependencies=[Depends(_authorize)])
async def _update_account(row_id: str, body: dict[str, Any]) -> dict[str, Any]:
    row = _find_row(_service.state.data["accounts"], row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found")
    for key in (
        "name",
        "platform",
        "adapter",
        "bot_id",
        "provider_id",
        "model",
        "reasoning_effort",
        "temperature_enabled",
        "context_length",
        "persona_role",
        "persona_prompt",
        "enabled",
        "enabled_tools",
        "memory_enabled",
        "memory_interval",
    ):
        if key in body:
            row[key] = body[key]
    if "temperature" in body:
        row["temperature"] = _temperature_value(body["temperature"])
    if "memory_interval" in body:
        row["memory_interval"] = _memory_interval(body["memory_interval"])
    if "memory_enabled" in body:
        row["memory_enabled"] = bool(body["memory_enabled"])
    if "name" in body:
        row["name_source"] = "manual" if str(body["name"]).strip() else "fallback"
    _service.state.save()
    _service.agents.clear()
    return row


@_api.delete("/api/accounts/{row_id}", dependencies=[Depends(_authorize)])
async def _delete_account(row_id: str) -> dict[str, bool]:
    before = len(_service.state.data["accounts"])
    account = _find_row(_service.state.data["accounts"], row_id)
    _service.state.data["accounts"] = [
        row for row in _service.state.data["accounts"] if str(row.get("id")) != row_id
    ]
    if account:
        _service.state.data["groups"] = [
            row
            for row in _service.state.data["groups"]
            if not (
                str(row.get("platform")) == str(account.get("platform"))
                and str(row.get("bot_id")) == str(account.get("bot_id"))
            )
        ]
    _service.state.save()
    return {"deleted": len(_service.state.data["accounts"]) < before}


@_api.get("/api/groups", dependencies=[Depends(_authorize)])
async def _groups() -> list[dict[str, Any]]:
    return _service.state.data["groups"]


@_api.post("/api/groups", dependencies=[Depends(_authorize)])
async def _create_group(body: dict[str, Any]) -> dict[str, Any]:
    platform = str(body.get("platform") or "").strip()
    bot_id = str(body.get("bot_id") or "").strip()
    group_id = str(body.get("group_id") or "").strip()
    if not platform or not bot_id or not group_id:
        raise HTTPException(
            status_code=422, detail="platform, bot_id and group_id are required"
        )
    if _service.group_config(platform, bot_id, group_id):
        raise HTTPException(status_code=409, detail="Group already exists")
    row = {
        "id": _new_id(),
        "platform": platform,
        "bot_id": bot_id,
        "group_id": group_id,
        "name": str(body.get("name") or group_id)[:160],
        "name_source": "manual" if body.get("name") else "fallback",
        "enabled": bool(body.get("enabled", True)),
        "provider_id": str(body.get("provider_id") or ""),
        "system_prompt": str(body.get("system_prompt") or ""),
        "reply_frequency": str(body.get("reply_frequency") or "balanced"),
        "reasoning_effort": str(body.get("reasoning_effort") or ""),
        "model": str(body.get("model") or ""),
        "cost_limit": body.get("cost_limit"),
        "tools": body.get("tools")
        if isinstance(body.get("tools"), dict)
        else {"skills": [], "mcps": [], "rules": []},
        "enabled_tools": body.get("enabled_tools")
        if isinstance(body.get("enabled_tools"), list)
        else None,
    }
    _service.state.data["groups"].append(row)
    _service.state.save()
    _service.agents.clear()
    return row


@_api.put("/api/groups/{row_id}", dependencies=[Depends(_authorize)])
async def _update_group(row_id: str, body: dict[str, Any]) -> dict[str, Any]:
    row = _find_row(_service.state.data["groups"], row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Group not found")
    for key in (
        "platform",
        "bot_id",
        "group_id",
        "name",
        "enabled",
        "provider_id",
        "system_prompt",
        "reply_frequency",
        "reasoning_effort",
        "model",
        "cost_limit",
        "tools",
        "enabled_tools",
    ):
        if key in body:
            row[key] = body[key]
    if "name" in body:
        row["name_source"] = "manual" if str(body["name"]).strip() else "fallback"
    _service.state.save()
    _service.agents.clear()
    return row


@_api.delete("/api/groups/{row_id}", dependencies=[Depends(_authorize)])
async def _delete_group(row_id: str) -> dict[str, bool]:
    before = len(_service.state.data["groups"])
    _service.state.data["groups"] = [
        row for row in _service.state.data["groups"] if str(row.get("id")) != row_id
    ]
    _service.state.save()
    return {"deleted": len(_service.state.data["groups"]) < before}


@_api.get("/api/interfaces/{kind}", dependencies=[Depends(_authorize)])
async def _interfaces(kind: str) -> list[dict[str, Any]]:
    if kind not in {"providers", "skills", "mcps", "rules"}:
        raise HTTPException(status_code=404, detail="Unknown interface kind")
    return _service.state.data["interfaces"][kind]


@_api.post("/api/interfaces/{kind}", dependencies=[Depends(_authorize)])
async def _create_interface(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    if kind not in {"providers", "skills", "mcps", "rules"}:
        raise HTTPException(status_code=404, detail="Unknown interface kind")
    row = {"id": _new_id(), **body}
    if kind == "providers":
        row["models"] = normalize_model_records(row.get("models", []))
        row["context_length"] = positive_context_length(row.get("context_length"))
    _service.state.data["interfaces"][kind].append(row)
    _service.state.save()
    _service.agents.clear()
    return row


@_api.put("/api/interfaces/{kind}/{row_id}", dependencies=[Depends(_authorize)])
async def _update_interface(
    kind: str, row_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    if kind not in {"providers", "skills", "mcps", "rules"}:
        raise HTTPException(status_code=404, detail="Unknown interface kind")
    row = _find_row(_service.state.data["interfaces"][kind], row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Interface not found")
    row.update(body)
    if kind == "providers":
        row["models"] = normalize_model_records(row.get("models", []))
        row["context_length"] = positive_context_length(row.get("context_length"))
    _service.state.save()
    _service.agents.clear()
    return row


@_api.delete("/api/interfaces/{kind}/{row_id}", dependencies=[Depends(_authorize)])
async def _delete_interface(kind: str, row_id: str) -> dict[str, bool]:
    if kind not in {"providers", "skills", "mcps", "rules"}:
        raise HTTPException(status_code=404, detail="Unknown interface kind")
    rows = _service.state.data["interfaces"][kind]
    before = len(rows)
    _service.state.data["interfaces"][kind] = [
        row for row in rows if str(row.get("id")) != row_id
    ]
    _service.state.save()
    return {"deleted": len(_service.state.data["interfaces"][kind]) < before}


async def _fetch_provider_models(base_url: str, api_key: str) -> list[dict[str, Any]]:
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=base_url.strip() or None,
            api_key=api_key.strip() or "EMPTY",
        )
        try:
            response = await client.models.list()
            raw_models = list(response.data)
        finally:
            await client.close()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Model discovery failed: {type(exc).__name__}",
        ) from exc
    return normalize_model_records(raw_models)


@_api.post(
    "/api/interfaces/providers/discover",
    dependencies=[Depends(_authorize)],
)
async def _discover_provider_models_preview(body: dict[str, Any]) -> dict[str, Any]:
    models = await _fetch_provider_models(
        str(body.get("base_url") or ""), str(body.get("api_key") or "")
    )
    return {"models": models}


@_api.post(
    "/api/interfaces/providers/{row_id}/models",
    dependencies=[Depends(_authorize)],
)
async def _discover_provider_models(row_id: str) -> dict[str, Any]:
    provider = _find_row(_service.state.data["interfaces"]["providers"], row_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    models = await _fetch_provider_models(
        str(provider.get("base_url") or ""), str(provider.get("api_key") or "")
    )
    provider["models"] = models
    _service.state.save()
    return {"models": models}


@_api.get("/api/tools", dependencies=[Depends(_authorize)])
async def _tools() -> list[dict[str, Any]]:
    return _service.tool_catalog()


@_api.get("/api/status", dependencies=[Depends(_authorize)])
async def _status() -> dict[str, Any]:
    return _service.snapshot()


@_api.get("/api/logs", dependencies=[Depends(_authorize)])
async def _logs(limit: int = 200) -> dict[str, Any]:
    bounded = max(1, min(limit, 1000))
    return {
        "activity": _service.state.data["activity"][-bounded:],
        "conversations": list(_service.state.data["conversations"].values()),
        "usage": _service.state.data["usage"][-bounded:],
    }


@_api.put("/api/accounts/{row_id}/access", dependencies=[Depends(_authorize)])
async def _update_account_access(  # noqa: C901, PLR0912
    row_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    account = _find_row(_service.state.data["accounts"], row_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    validated: dict[str, list[dict[str, str]]] = {}
    for field in ("admins", "whitelist", "blacklist"):
        rows = body.get(field)
        if not isinstance(rows, list):
            raise HTTPException(status_code=422, detail=f"{field} must be a list")
        normalized = []
        for row in rows:
            if isinstance(row, (str, int)):
                entry_id = str(row).strip()
                if not entry_id:
                    continue
                # Untyped legacy IDs used to match both private and group peers.
                kinds = ("private",) if field == "admins" else ("private", "group")
                normalized.extend(
                    {"id": entry_id, "kind": kind, "name": ""} for kind in kinds
                )
                continue
            if not isinstance(row, dict):
                raise HTTPException(status_code=422, detail=f"Invalid {field} entry")
            entry_id = str(row.get("id") or "").strip()
            kind = "private" if field == "admins" else str(row.get("kind") or "")
            if not entry_id or kind not in {"private", "group"}:
                raise HTTPException(status_code=422, detail=f"Invalid {field} entry")
            if field == "admins" and kind != "private":
                raise HTTPException(
                    status_code=422, detail="Admins must be private users"
                )
            entry = {
                "id": entry_id,
                "kind": kind,
                "name": str(row.get("name") or "")[:120],
            }
            if entry not in normalized:
                normalized.append(entry)
        validated[field] = normalized
    account.update(validated)
    for record in _service.state.data["conversations"].values():
        if (record.get("platform"), record.get("bot_id")) != (
            account.get("platform"), account.get("bot_id")
        ):
            continue
        listed = _service.is_allowed(
            str(record.get("kind", "private")),
            str(record.get("peer_id", "")),
            str(record.get("user_id", "")),
            str(record.get("platform", "")),
            str(record.get("bot_id", "")),
        )
        kind = "group" if record.get("kind") == "group" else "private"
        blacklisted = str(record.get("peer_id", "")) in _service._access_ids(
            account["blacklist"], kind
        )
        next_status = "approved" if listed else "rejected" if blacklisted else "pending"
        if record.get("status") != next_status:
            record["status"] = next_status
            record["confirmed_at"] = time.time() if next_status == "approved" else None
    _service.agents.clear()
    _service.state.save()
    return {
        key: account[key]
        for key in ("admins", "whitelist", "blacklist", "private_users")
    }


@_api.put(
    "/api/conversations/{conversation_key}/status",
    dependencies=[Depends(_authorize)],
)
async def _update_conversation_status(
    conversation_key: str, body: dict[str, str]
) -> dict[str, Any]:
    status = str(body.get("status") or "")
    try:
        updated = _service.set_conversation_status(conversation_key, status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _service.state.save()
    return updated


@_api.get(
    "/api/conversations/{conversation_key}",
    dependencies=[Depends(_authorize)],
)
async def _conversation_detail(
    conversation_key: str, limit: int = 1000
) -> dict[str, Any]:
    """Return one bridge conversation and its persisted transcript."""
    record = _service.state.data["conversations"].get(conversation_key)
    if record is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    bounded = max(1, min(limit, 2000))
    messages = _service.store.load_messages(str(record["chat_id"]))
    return {
        **record,
        "messages": [message.to_dict() for message in messages[-bounded:]],
    }


@_api.post("/api/approvals/{conversation_key}", dependencies=[Depends(_authorize)])
async def _resolve_approval(
    conversation_key: str, body: dict[str, bool]
) -> dict[str, bool]:
    if "approved" not in body:
        raise HTTPException(status_code=422, detail="approved is required")
    resolved = _service.resolve_approval(conversation_key, approved=body["approved"])
    if not resolved:
        raise HTTPException(status_code=404, detail="Approval not found")
    return {"resolved": True}


class UpdateRequest(BaseModel):
    value: str


@_api.get("/api/mcp", dependencies=[Depends(_authorize)])
async def _mcp_status() -> dict[str, Any]:
    return _service.mcp_status()


@_api.put("/api/mcp", dependencies=[Depends(_authorize)])
async def _configure_mcp(body: UpdateRequest) -> dict[str, Any]:
    if len(body.value) > MAX_MCP_URL_CHARS:
        raise HTTPException(status_code=422, detail="MCP URL is too long")
    return await _service.configure_mcp(body.value)


class EnabledToolsRequest(BaseModel):
    enabled: list[str]


class ProjectMemoryRequest(BaseModel):
    name: str
    title: str
    description: str
    type: str
    content: str


class VoiceUploadRequest(BaseModel):
    name: str
    data: str


class SlangSettingsRequest(BaseModel):
    enabled: bool
    min_messages: int
    cooldown_seconds: int


@_api.put("/api/mode", dependencies=[Depends(_authorize)])
async def _set_mode(body: UpdateRequest) -> dict[str, str]:
    if body.value not in {"chat", "agent"}:
        raise HTTPException(status_code=422, detail="Invalid mode")
    _service.set_mode(cast("Mode", body.value))
    return {"mode": body.value}


@_api.get(
    "/api/conversations/{conversation_key}/tools",
    dependencies=[Depends(_authorize)],
)
async def _session_tools(conversation_key: str) -> dict[str, Any]:
    try:
        return _service.session_tool_config(conversation_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc


@_api.put(
    "/api/conversations/{conversation_key}/tools",
    dependencies=[Depends(_authorize)],
)
async def _set_session_tools(
    conversation_key: str, body: EnabledToolsRequest
) -> dict[str, Any]:
    lock = _service.locks.setdefault(conversation_key, asyncio.Lock())
    try:
        async with lock:
            _service.set_session_tools(conversation_key, body.enabled)
            return _service.session_tool_config(conversation_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@_api.put("/api/silent", dependencies=[Depends(_authorize)])
async def _set_silent(body: dict[str, bool]) -> dict[str, bool]:
    _service.state.data["silent"] = bool(body.get("enabled", False))
    _service.state.save()
    return {"silent": _service.state.data["silent"]}


@_api.put("/api/role", dependencies=[Depends(_authorize)])
async def _set_role(body: UpdateRequest) -> dict[str, str | None]:
    role = body.value.strip()
    if len(role) > MAX_ROLE_CHARS:
        raise HTTPException(status_code=422, detail="Role prompt is too long")
    _service.state.data["role"] = role or None
    _service.agents.clear()
    _service.state.save()
    return {"role": _service.state.data["role"]}


@_api.put("/api/initial-prompt/{conversation_key}", dependencies=[Depends(_authorize)])
async def _set_initial_prompt(
    conversation_key: str, body: UpdateRequest
) -> dict[str, bool]:
    if len(body.value) > MAX_INITIAL_PROMPT_CHARS:
        raise HTTPException(status_code=422, detail="Initial prompt is too long")
    if conversation_key not in _service.state.data["conversations"]:
        raise HTTPException(status_code=404, detail="Conversation not found")
    _service.state.data["initial_prompts"][conversation_key] = body.value
    _service.state.save()
    return {"saved": True}


@_api.post(
    "/api/conversations/{conversation_key}/reset", dependencies=[Depends(_authorize)]
)
async def _reset_chat(conversation_key: str) -> dict[str, bool]:
    record = _service.state.data["conversations"].get(conversation_key)
    if not record:
        raise HTTPException(status_code=404, detail="Conversation not found")
    lock = _service.locks.setdefault(conversation_key, asyncio.Lock())
    async with lock:
        messages = _service.store.load_messages(record["chat_id"])
        cleared = bool(messages)
        _service.store.replace(record["chat_id"], [])
        _service.agents.pop(conversation_key, None)
    return {"reset": True, "cleared": cleared}


@_api.get("/api/slang", dependencies=[Depends(_authorize)])
async def _list_slang() -> list[dict[str, Any]]:
    return _service.state.data["slang"]


@_api.post("/api/slang", dependencies=[Depends(_authorize)])
async def _add_slang(body: dict[str, str]) -> dict[str, Any]:
    term = body.get("term", "").strip()
    if not term or len(term) > MAX_SLANG_TERM_CHARS:
        raise HTTPException(status_code=422, detail="Invalid term")
    row = {
        "id": secrets.token_hex(8),
        "term": term,
        "meaning": body.get("meaning", "")[:1000],
        "status": "candidate",
    }
    _service.state.data["slang"].append(row)
    _service.state.save()
    return row


@_api.patch("/api/slang/{entry_id}", dependencies=[Depends(_authorize)])
async def _review_slang(entry_id: str, body: dict[str, str]) -> dict[str, Any]:
    for row in _service.state.data["slang"]:
        if row["id"] == entry_id:
            status = body.get("status", "")
            if status not in {"confirmed", "rejected", "candidate"}:
                raise HTTPException(status_code=422, detail="Invalid status")
            row["status"] = status
            if "meaning" in body:
                row["meaning"] = body["meaning"][:1000]
            _service.state.save()
            return row
    raise HTTPException(status_code=404, detail="Entry not found")


@_api.delete("/api/slang/{entry_id}", dependencies=[Depends(_authorize)])
async def _delete_slang(entry_id: str) -> dict[str, bool]:
    before = len(_service.state.data["slang"])
    _service.state.data["slang"] = [
        row for row in _service.state.data["slang"] if row["id"] != entry_id
    ]
    _service.state.save()
    return {"deleted": len(_service.state.data["slang"]) < before}


def _clear_role_agents() -> None:
    _service.agents.clear()


@_api.get("/api/roles", dependencies=[Depends(_authorize)])
async def _roles() -> dict[str, Any]:
    return {
        "roles": _service.roles.list(),
        "active": _service.state.data.get("active_role"),
    }


@_api.get("/api/roles/{name}", dependencies=[Depends(_authorize)])
async def _get_role(name: str) -> dict[str, Any]:
    try:
        content = _service.roles.get(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Role not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "name": name,
        "content": content,
        "rendered": _service.roles.render(name),
        **_service.roles.inspect(content),
    }


@_api.post("/api/roles", dependencies=[Depends(_authorize)])
async def _create_role(body: dict[str, str]) -> dict[str, str]:
    try:
        _service.roles.save(body.get("name", ""), body.get("content", ""), create=True)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="Role already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"name": body["name"]}


@_api.put("/api/roles/{name}", dependencies=[Depends(_authorize)])
async def _update_role(name: str, body: UpdateRequest) -> dict[str, str]:
    try:
        _service.roles.save(name, body.value)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Role not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _clear_role_agents()
    return {"name": name}


@_api.post("/api/roles/{name}/copy", dependencies=[Depends(_authorize)])
async def _copy_role(name: str, body: dict[str, str]) -> dict[str, str]:
    try:
        _service.roles.copy(name, body.get("name", ""))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Role not found") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="Role already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"name": body["name"]}


@_api.post("/api/roles/{name}/rename", dependencies=[Depends(_authorize)])
async def _rename_role(name: str, body: dict[str, str]) -> dict[str, str]:
    destination = body.get("name", "")
    try:
        _service.roles.rename(name, destination)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Role not found") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="Role already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if _service.state.data.get("active_role") == name:
        _service.state.data["active_role"] = destination
        _service.state.save()
    _clear_role_agents()
    return {"name": destination}


@_api.delete("/api/roles/{name}", dependencies=[Depends(_authorize)])
async def _delete_role(name: str) -> dict[str, bool]:
    try:
        _service.roles.delete(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Role not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if _service.state.data.get("active_role") == name:
        _service.state.data["active_role"] = None
        _service.state.save()
    _clear_role_agents()
    return {"deleted": True}


@_api.get("/api/memories", dependencies=[Depends(_authorize)])
async def _memories() -> list[dict[str, Any]]:
    return _service.memories.list()


@_api.get("/api/memories/index", dependencies=[Depends(_authorize)])
async def _memory_index() -> dict[str, str]:
    return {"content": _service.memories.index()}


@_api.get("/api/memories/{name}", dependencies=[Depends(_authorize)])
async def _get_memory(name: str) -> dict[str, Any]:
    try:
        return _service.memories.get(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@_api.post("/api/memories", dependencies=[Depends(_authorize)])
async def _create_memory(body: ProjectMemoryRequest) -> dict[str, str]:
    try:
        _service.memories.get(body.name)
    except FileNotFoundError:
        pass
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        raise HTTPException(status_code=409, detail="Memory already exists")
    try:
        _service.memories.save(
            body.name, body.title, body.description, body.type, body.content
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"name": body.name}


@_api.put("/api/memories/{name}", dependencies=[Depends(_authorize)])
async def _update_memory(name: str, body: ProjectMemoryRequest) -> dict[str, str]:
    if name != body.name:
        raise HTTPException(status_code=422, detail="Memory name cannot be changed")
    try:
        _service.memories.get(name)
        _service.memories.save(
            body.name, body.title, body.description, body.type, body.content
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"name": name}


@_api.delete("/api/memories/{name}", dependencies=[Depends(_authorize)])
async def _delete_memory(name: str) -> dict[str, bool]:
    try:
        _service.memories.delete(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"deleted": True}


@_api.get("/api/accounts/{row_id}/memories", dependencies=[Depends(_authorize)])
async def _bot_memories(row_id: str) -> list[dict[str, Any]]:
    account = _find_row(_service.state.data["accounts"], row_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return _service.bot_memory_store(account).list()


@_api.get(
    "/api/accounts/{row_id}/memories/{name}", dependencies=[Depends(_authorize)]
)
async def _get_bot_memory(row_id: str, name: str) -> dict[str, Any]:
    account = _find_row(_service.state.data["accounts"], row_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    try:
        return _service.bot_memory_store(account).get(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@_api.post(
    "/api/accounts/{row_id}/memories", dependencies=[Depends(_authorize)]
)
async def _create_bot_memory(
    row_id: str, body: ProjectMemoryRequest
) -> dict[str, str]:
    account = _find_row(_service.state.data["accounts"], row_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    store = _service.bot_memory_store(account)
    try:
        store.get(body.name)
    except FileNotFoundError:
        pass
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        raise HTTPException(status_code=409, detail="Memory already exists")
    try:
        store.save(body.name, body.title, body.description, body.type, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _service.agents.clear()
    return {"name": body.name}


@_api.put(
    "/api/accounts/{row_id}/memories/{name}", dependencies=[Depends(_authorize)]
)
async def _update_bot_memory(
    row_id: str, name: str, body: ProjectMemoryRequest
) -> dict[str, str]:
    account = _find_row(_service.state.data["accounts"], row_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if name != body.name:
        raise HTTPException(status_code=422, detail="Memory name cannot be changed")
    store = _service.bot_memory_store(account)
    try:
        store.get(name)
        store.save(body.name, body.title, body.description, body.type, body.content)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _service.agents.clear()
    return {"name": name}


@_api.delete(
    "/api/accounts/{row_id}/memories/{name}", dependencies=[Depends(_authorize)]
)
async def _delete_bot_memory(row_id: str, name: str) -> dict[str, bool]:
    account = _find_row(_service.state.data["accounts"], row_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    try:
        _service.bot_memory_store(account).delete(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _service.agents.clear()
    return {"deleted": True}


@_api.get("/api/memory-queue", dependencies=[Depends(_authorize)])
async def _memory_queue() -> list[dict[str, Any]]:
    return sorted(
        _service.state.data["memory_queue"],
        key=lambda row: float(row.get("created_at", 0)),
        reverse=True,
    )


@_api.patch("/api/memory-queue/{candidate_id}", dependencies=[Depends(_authorize)])
async def _edit_memory_candidate(
    candidate_id: str, body: ProjectMemoryRequest
) -> dict[str, Any]:
    candidate = _find_row(_service.state.data["memory_queue"], candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Memory candidate not found")
    candidate.update(
        {
            "name": body.name,
            "title": body.title,
            "description": body.description,
            "type": body.type,
            "content": body.content,
        }
    )
    _service.state.save()
    return candidate


@_api.post(
    "/api/memory-queue/{candidate_id}/approve", dependencies=[Depends(_authorize)]
)
async def _approve_memory_candidate(
    candidate_id: str, body: dict[str, str]
) -> dict[str, str]:
    candidate = _find_row(_service.state.data["memory_queue"], candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Memory candidate not found")
    account = _find_row(
        _service.state.data["accounts"], str(candidate.get("account_id") or "")
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Memory account not found")
    name = str(body.get("name") or candidate.get("name") or "").strip()
    store = _service.bot_memory_store(account)
    try:
        store.get(name)
    except FileNotFoundError:
        pass
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        raise HTTPException(status_code=409, detail="Memory already exists")
    try:
        store.save(
            name,
            str(candidate.get("title") or ""),
            str(candidate.get("description") or ""),
            str(candidate.get("type") or "reference"),
            str(candidate.get("content") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _service.state.data["memory_queue"] = [
        row
        for row in _service.state.data["memory_queue"]
        if str(row.get("id")) != candidate_id
    ]
    _service.state.save()
    _service.agents.clear()
    return {"name": name}


@_api.delete(
    "/api/memory-queue/{candidate_id}", dependencies=[Depends(_authorize)]
)
async def _delete_memory_candidate(candidate_id: str) -> dict[str, bool]:
    before = len(_service.state.data["memory_queue"])
    _service.state.data["memory_queue"] = [
        row
        for row in _service.state.data["memory_queue"]
        if str(row.get("id")) != candidate_id
    ]
    _service.state.save()
    return {"deleted": len(_service.state.data["memory_queue"]) < before}


@_api.put("/api/active-role", dependencies=[Depends(_authorize)])
async def _activate_role(body: dict[str, str | None]) -> dict[str, str | None]:
    name = body.get("name")
    if name:
        try:
            _service.roles.get(name)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Role not found") from exc
    _service.state.data["active_role"] = name
    _service.state.data["role"] = None
    _service.state.save()
    _clear_role_agents()
    return {"active": name}


@_api.get("/api/voices", dependencies=[Depends(_authorize)])
async def _voices() -> list[dict[str, object]]:
    return _service.voice.list()


@_api.post("/api/voices", dependencies=[Depends(_authorize)])
async def _upload_voice(body: VoiceUploadRequest) -> dict[str, str]:
    if len(body.data) > (_service.voice.max_bytes * 4 // 3) + 8:
        raise HTTPException(status_code=413, detail="Voice file is too large")
    try:
        data = base64.b64decode(body.data, validate=True)
        path = _service.voice.add(body.name, data)
    except binascii.Error as exc:
        raise HTTPException(status_code=422, detail="Invalid base64 audio") from exc
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Voice file already exists"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"name": path.name}


@_api.post("/api/voices/synthesize", dependencies=[Depends(_authorize)])
async def _synthesize_voice(body: UpdateRequest) -> dict[str, str]:
    try:
        path = await _service.voice.synthesize(
            body.value,
            rate=_service.config.voice_rate,
            volume=_service.config.voice_volume,
            voice_id=_service.config.voice_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"name": path.name}


@_api.delete("/api/voices/{name:path}", dependencies=[Depends(_authorize)])
async def _delete_voice(name: str) -> dict[str, bool]:
    try:
        _service.voice.resolve(name).unlink()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Voice file not found") from exc
    return {"deleted": True}


@_api.get("/api/slang/settings", dependencies=[Depends(_authorize)])
async def _slang_settings() -> dict[str, Any]:
    return {
        "enabled": _service.config.slang_enabled,
        "min_messages": _service.config.slang_min_messages,
        "cooldown_seconds": _service.config.slang_cooldown_seconds,
    }


@_api.put("/api/slang/settings", dependencies=[Depends(_authorize)])
async def _update_slang_settings(body: SlangSettingsRequest) -> dict[str, Any]:
    _service.config.slang_enabled = body.enabled
    _service.config.slang_min_messages = max(3, min(body.min_messages, 100))
    _service.config.slang_cooldown_seconds = max(30, min(body.cooldown_seconds, 86400))
    _service.state.data["slang_settings"] = {
        "enabled": _service.config.slang_enabled,
        "min_messages": _service.config.slang_min_messages,
        "cooldown_seconds": _service.config.slang_cooldown_seconds,
    }
    _service.state.save()
    return await _slang_settings()


_webui_static = Path(__file__).with_name("webui")
if (_webui_static / "assets").is_dir():
    _api.mount(
        "/assets",
        StaticFiles(directory=_webui_static / "assets"),
        name="chatbot-webui-assets",
    )


@_api.get("/", include_in_schema=False)
async def _console() -> FileResponse:
    built_index = _webui_static / "index.html"
    if not built_index.is_file():
        raise HTTPException(
            status_code=503,
            detail="WebUI static files are unavailable; run `npm run build` in webui/.",
        )
    return FileResponse(built_index)


cast("Any", _driver).server_app.mount("/chat-agent", _api)


@_driver.on_startup
async def _initialize_bridge() -> None:
    if _service.mcp_server_url:
        await _service.configure_mcp(_service.mcp_server_url)


@_driver.on_shutdown
async def _close_agents() -> None:
    for task in (*_service.slang_tasks, *_service.memory_tasks):
        task.cancel()
    tasks = (*_service.slang_tasks, *_service.memory_tasks)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.gather(*(agent.close() for agent in _service.agents.values()))
