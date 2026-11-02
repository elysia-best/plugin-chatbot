"""消息模型。

复刻 claude-code 的消息/工具调用表示，使用 OpenAI Chat Completions
消息格式（role / content / tool_calls / tool_call_id）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

Role = Literal["system", "user", "assistant", "tool"]
MessageContent: TypeAlias = str | list[dict[str, Any]] | None


@dataclass
class ToolCall:
    """模型发起的一次工具调用。"""

    id: str
    name: str
    arguments: dict[str, Any]

    @classmethod
    def from_openai(cls, raw: Any) -> "ToolCall":
        if isinstance(raw, dict):
            function = raw.get("function") or {}
            raw_args = raw.get("arguments", function.get("arguments"))
            name = raw.get("name") or function.get("name", "")
            call_id = raw.get("id", "")
        else:
            function = getattr(raw, "function", None)
            raw_args = getattr(raw, "arguments", None)
            if raw_args is None and function is not None:
                raw_args = getattr(function, "arguments", None)
            name = getattr(function, "name", None) or getattr(raw, "name", "")
            call_id = getattr(raw, "id", "")

        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                args = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}
        return cls(
            id=call_id or "",
            name=name or "",
            arguments=args,
        )

    def to_openai_tool_call(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": _json_dumps(self.arguments)},
        }

    def to_dict(self) -> dict[str, Any]:
        """序列化为可 JSON 落盘的字典。"""
        return {"id": self.id, "name": self.name, "arguments": self.arguments}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ToolCall":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            arguments=d.get("arguments", {}) or {},
        )


@dataclass
class Message:
    """一条对话消息（OpenAI 格式）。"""

    role: Role
    content: MessageContent = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    @property
    def is_tool_result(self) -> bool:
        return self.role == "tool"

    def to_openai(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": self.role}
        if self.name:
            msg["name"] = self.name
        if self.content is not None:
            msg["content"] = self.content
        if self.role == "tool":
            msg["tool_call_id"] = self.tool_call_id or ""
        if self.tool_calls:
            msg["tool_calls"] = [tc.to_openai_tool_call() for tc in self.tool_calls]
        return msg

    @classmethod
    def from_openai(cls, raw: dict[str, Any]) -> "Message":
        role = raw.get("role", "user")
        content = raw.get("content")
        if isinstance(content, list):
            content = [item for item in content if isinstance(item, dict)]
        tool_calls = None
        if raw.get("tool_calls"):
            tool_calls = [
                ToolCall.from_openai(tc)
                for tc in raw["tool_calls"]
            ]
        return cls(
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=raw.get("tool_call_id"),
            name=raw.get("name"),
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为可 JSON 落盘的字典（区别于 to_openai 的线上格式）。"""
        d: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls is not None:
            d["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            d["name"] = self.name
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Message":
        tool_calls = None
        if d.get("tool_calls"):
            tool_calls = [ToolCall.from_dict(tc) for tc in d["tool_calls"]]
        return cls(
            role=d.get("role", "user"),
            content=d.get("content"),
            tool_calls=tool_calls,
            tool_call_id=d.get("tool_call_id"),
            name=d.get("name"),
        )


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)
