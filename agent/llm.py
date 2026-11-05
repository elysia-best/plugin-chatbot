"""LLM 客户端：OpenAI-compatible /chat/completions。

基于官方 openai SDK（AsyncOpenAI），流式消费。
支持 base_url / api_key / model 从环境变量读取。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import AsyncOpenAI

from .errors import ContextOverflowError, is_context_overflow, parse_context_limit
from .messages import Message, ToolCall

MAX_IMAGES_PER_REQUEST = 50


class LLMBackend(Protocol):
    """LLM 后端接口，便于注入 mock 或自定义实现。

    LLMClient 实现该接口；测试可注入 ScriptedLLM 等替身。
    """

    async def complete(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse: ...


@dataclass
class Usage:
    """token 用量汇总。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def merge(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens


@dataclass
class LLMResponse:
    """一次 LLM 调用的结果。"""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    usage: Usage = field(default_factory=Usage)


class LLMClient:
    """OpenAI-compatible 客户端封装。"""

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float | None = 0.7,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        timeout: float = 120.0,
        client: Any | None = None,
        *,
        allow_environment_fallback: bool = True,
    ) -> None:
        self.model = model or (
            os.getenv("OPENAI_MODEL", "") if allow_environment_fallback else ""
        )
        base = base_url or (
            os.getenv("OPENAI_BASE_URL") if allow_environment_fallback else None
        ) or None
        key = api_key or (
            os.getenv("OPENAI_API_KEY") if allow_environment_fallback else None
        ) or "EMPTY"
        self.temperature = temperature
        self.max_tokens = max_tokens
        effort = (
            reasoning_effort
            if reasoning_effort is not None
            else (
                os.getenv("OPENAI_REASONING_EFFORT", "")
                if allow_environment_fallback
                else ""
            )
        )
        self.reasoning_effort = effort.strip() or None
        # client 参数便于测试注入 mock
        self._client = client or AsyncOpenAI(
            base_url=base, api_key=key, timeout=timeout, max_retries=0
        )

    def _tool_schemas(self, tools: list[Any]) -> list[dict[str, Any]]:
        """把 Tool 对象转成 OpenAI tool 参数。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]

    async def complete(  # noqa: C901, PLR0912, PLR0915
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """一次流式对话调用，返回聚合后的内容 + 工具调用。"""
        # system prompt 作为第一条消息，避免重复注入
        payload_messages: list[dict[str, Any]] = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        payload_messages.extend(m.to_openai() for m in messages)
        _limit_request_images(payload_messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if tools:
            kwargs["tools"] = self._tool_schemas(tools)
        if self.max_tokens:
            kwargs["max_completion_tokens"] = self.max_tokens
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort

        try:
            try:
                stream = await self._client.chat.completions.create(**kwargs)
            except Exception as exc:
                if "stream_options" not in str(exc).casefold():
                    raise
                kwargs.pop("stream_options")
                stream = await self._client.chat.completions.create(**kwargs)

            content_parts: list[str] = []
            tool_calls: dict[int, ToolCall] = {}
            finish_reason: str | None = None
            usage = Usage()

            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    u = chunk.usage
                    if u.prompt_tokens:
                        usage.prompt_tokens += u.prompt_tokens
                    if u.completion_tokens:
                        usage.completion_tokens += u.completion_tokens
                    if u.total_tokens:
                        usage.total_tokens += u.total_tokens
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if getattr(delta, "content", None):
                    content_parts.append(delta.content)
                for tc in getattr(delta, "tool_calls", None) or []:
                    idx = tc.index
                    if idx not in tool_calls:
                        tool_calls[idx] = ToolCall(
                            id=tc.id or "", name="", arguments={}
                        )
                    if tc.id:
                        tool_calls[idx].id = tc.id
                    fn = getattr(tc, "function", None)
                    if fn:
                        if fn.name:
                            tool_calls[idx].name = fn.name
                        if fn.arguments:
                            # 流式 arguments 分片，需要累积再解析
                            _merge_args(tool_calls[idx], fn.arguments)
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
        except Exception as exc:
            if is_context_overflow(exc):
                raise ContextOverflowError(
                    str(exc), limit=parse_context_limit(exc)
                ) from exc
            raise

        # 排序按 index
        ordered = [tool_calls[i] for i in sorted(tool_calls)]
        return LLMResponse(
            content="".join(content_parts),
            tool_calls=ordered,
            finish_reason=finish_reason,
            usage=usage,
        )


def _merge_args(tc: ToolCall, fragment: str) -> None:
    """把流式 JSON 参数分片累积后解析。"""
    import json

    current = tc.arguments.get("_raw", "")
    current += fragment
    tc.arguments["_raw"] = current
    try:
        parsed = json.loads(current)
        if isinstance(parsed, dict):
            tc.arguments = parsed
    except json.JSONDecodeError:
        pass


def _limit_request_images(messages: list[dict[str, Any]]) -> None:
    """Keep the newest images within provider limits without mutating history."""
    image_locations: list[tuple[int, int]] = []
    for message_index, message in enumerate(messages):
        content = message.get("content")
        if isinstance(content, list):
            image_locations.extend(
                (message_index, block_index)
                for block_index, block in enumerate(content)
                if isinstance(block, dict)
                and block.get("type") in {"image_url", "input_image"}
            )

    excess = len(image_locations) - MAX_IMAGES_PER_REQUEST
    if excess <= 0:
        return
    to_remove: dict[int, set[int]] = {}
    for message_index, block_index in image_locations[:excess]:
        to_remove.setdefault(message_index, set()).add(block_index)
    for message_index, indexes in to_remove.items():
        content = messages[message_index]["content"]
        messages[message_index]["content"] = [
            block for index, block in enumerate(content) if index not in indexes
        ]
