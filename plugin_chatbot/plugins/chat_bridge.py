"""NoneBot message entrypoint and authenticated management API."""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from nonebot import get_driver, get_plugin_config, logger, on_message
from nonebot.adapters import Bot, Event  # noqa: TC002
from nonebot_plugin_alconna import Image, Target, UniMessage, get_target, image_fetch
from pydantic import BaseModel

from plugin_chatbot.bridge import BridgeConfig, BridgeService
from plugin_chatbot.bridge.service import IncomingMessage

if TYPE_CHECKING:
    from plugin_chatbot.bridge.service import Mode

MAX_ROLE_CHARS = 6000
MAX_INITIAL_PROMPT_CHARS = 4000
MAX_SLANG_TERM_CHARS = 100
MAX_IMAGES_PER_MESSAGE = 8
MAX_SIMULATION_PROMPT_CHARS = 20_000
MESSAGE_LOG_PREVIEW_CHARS = 120


class Settings(BaseModel):
    """Configuration read from NoneBot's plugin configuration."""

    agent_model: str = ""
    agent_base_url: str = ""
    agent_api_key: str = ""
    agent_reasoning_effort: str = ""
    agent_workspace: str = ""
    bridge_state_dir: str = ""
    bridge_owner_ids: str | int | list[str | int] = ""
    bridge_allowed_groups: str | int | list[str | int] = ""
    bridge_allowed_private: str | int | list[str | int] = ""
    bridge_mode: str = "chat"
    bridge_max_message_chars: int = 500
    bridge_max_messages_per_minute: int = 6
    bridge_group_batch_seconds: float = 1.0
    max_context: int = 262_144
    compact_rate: float = 0.8
    bridge_max_media_bytes: int = 8 * 1024 * 1024
    bridge_console_token: str = ""
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


def _as_ids(value: Any) -> set[str]:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                pass
        if isinstance(value, str):
            return {part.strip() for part in value.split(",") if part.strip()}
    if isinstance(value, int) and not isinstance(value, bool):
        return {str(value)}
    if isinstance(value, (list, tuple, set)):
        return {
            str(part).strip()
            for part in value
            if isinstance(part, (str, int))
            and not isinstance(part, bool)
            and str(part).strip()
        }
    return set()


_settings = get_plugin_config(Settings)
_root = Path(__file__).resolve().parents[2]
_workspace = Path(_settings.agent_workspace or _root).resolve()
_state_dir = Path(_settings.bridge_state_dir or (_root / ".agent" / "bridge")).resolve()
_service = BridgeService(
    BridgeConfig(
        state_dir=_state_dir,
        workspace=_workspace,
        model=_settings.agent_model,
        base_url=_settings.agent_base_url,
        api_key=_settings.agent_api_key,
        reasoning_effort=_settings.agent_reasoning_effort.strip(),
        owner_ids=_as_ids(_settings.bridge_owner_ids),
        allowed_groups=_as_ids(_settings.bridge_allowed_groups),
        allowed_private=_as_ids(_settings.bridge_allowed_private),
        mode=cast(
            "Mode",
            _settings.bridge_mode
            if _settings.bridge_mode
            in {"chat", "closed-agent", "reserved", "reserved2"}
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
    keys = ("name", "title", "group_name", "guild_name", "channel_name")
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
    for source in (event, target.extra):
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


@_message.handle()
async def _handle_message(bot: Bot, event: Event) -> None:
    user_id = str(event.get_user_id())
    if user_id == str(getattr(bot, "self_id", "")):
        return
    try:
        target: Target = get_target(event, bot)
    except (AttributeError, TypeError, ValueError):
        return
    kind = "private" if target.private else "group"
    peer_id = target.id if kind == "private" else (target.parent_id or target.id)
    name_method = getattr(event, "get_user_name", None)
    user_name = _name_value(name_method() if callable(name_method) else "") or user_id
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


@_api.get("/api/status", dependencies=[Depends(_authorize)])
async def _status() -> dict[str, Any]:
    return _service.snapshot()


@_api.put("/api/simulation-prompts/{mode}", dependencies=[Depends(_authorize)])
async def _set_simulation_prompt(
    mode: str, body: SimulationPromptRequest
) -> dict[str, str]:
    if mode not in {"reserved", "reserved2"}:
        raise HTTPException(
            status_code=422, detail="Mode must be reserved or reserved2"
        )
    if len(body.value) > MAX_SIMULATION_PROMPT_CHARS:
        raise HTTPException(status_code=422, detail="Simulation prompt is too long")
    _service.state.data["simulation_prompts"][mode] = body.value
    _service.state.save()
    _service.agents.clear()
    return {"mode": mode}


@_api.get("/api/simulation-prompts", dependencies=[Depends(_authorize)])
async def _simulation_prompts() -> dict[str, str]:
    return _service.state.data["simulation_prompts"]


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


class SimulationPromptRequest(BaseModel):
    value: str


@_api.put("/api/mode", dependencies=[Depends(_authorize)])
async def _set_mode(body: UpdateRequest) -> dict[str, str]:
    if body.value not in {"chat", "closed-agent", "reserved", "reserved2"}:
        raise HTTPException(status_code=422, detail="Invalid mode")
    if body.value == "closed-agent" and not _service.config.owner_ids:
        raise HTTPException(status_code=409, detail="Configure bridge_owner_ids first")
    _service.state.data["mode"] = body.value
    _service.agents.clear()
    _service.state.save()
    return {"mode": body.value}


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
    _service.store.cache(record["chat_id"]).clear()
    _service.store.save(record["chat_id"])
    _service.agents.pop(conversation_key, None)
    _service.state.save()
    return {"reset": True}


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
async def _get_role(name: str, mode: str = "chat") -> dict[str, Any]:
    if mode not in {"chat", "closed-agent", "reserved", "reserved2"}:
        raise HTTPException(status_code=422, detail="Invalid mode")
    try:
        content = _service.roles.get(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Role not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "name": name,
        "content": content,
        "rendered": _service.roles.render(name, mode),
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


@_api.get("/", include_in_schema=False)
async def _console() -> FileResponse:
    return FileResponse(Path(__file__).with_name("console.html"))


cast("Any", _driver).server_app.mount("/chat-agent", _api)

_wake_tasks: list[asyncio.Task[None]] = []


@_driver.on_startup
async def _start_wake_scheduler() -> None:
    async def run() -> None:
        while True:
            await asyncio.sleep(5)
            if _service.state.data["mode"] == "reserved2":
                await _service.run_due_wakes()

    _wake_tasks.append(asyncio.create_task(run(), name="chat-agent-wake-scheduler"))


@_driver.on_shutdown
async def _close_agents() -> None:
    for task in _wake_tasks:
        task.cancel()
    for task in _wake_tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    for task in _service.slang_tasks:
        task.cancel()
    if _service.slang_tasks:
        await asyncio.gather(*_service.slang_tasks, return_exceptions=True)
    await asyncio.gather(*(agent.close() for agent in _service.agents.values()))
