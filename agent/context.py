"""Context-size estimation for text and multimodal Agent messages."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .messages import Message

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _estimate_value(value: Any) -> int:
    if isinstance(value, list):
        return sum(_estimate_value(item) for item in value)
    if isinstance(value, dict):
        kind = value.get("type")
        if isinstance(kind, str) and kind in {"image_url", "input_image"}:
            image = value.get("image_url", value)
            url = image.get("url", "") if isinstance(image, dict) else ""
            return 1024 + _estimate_value(url[:100])
        return sum(
            _estimate_value(key) + _estimate_value(item)
            for key, item in value.items()
        )
    if value is None:
        return 0
    text = str(value)
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return cjk + (other + 3) // 4


def estimate_text_tokens(text: str) -> int:
    """估算纯文本 token 数（CJK 每字约 1 token，其余约 4 字符 1 token）。"""
    return _estimate_value(text)


def estimate_json_tokens(value: Any) -> int:
    """估算任意 JSON 结构（含键名）的 token 数。"""
    return _estimate_value(value)


def estimate_message_tokens(messages: list[Message]) -> int:
    """Return a conservative estimate, treating each image as about 1k tokens."""
    total = 0
    for message in messages:
        total += 8 + _estimate_value(message.to_dict())
    return total
