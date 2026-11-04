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
        if value.get("type") in {"image_url", "input_image"}:
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


def estimate_message_tokens(messages: list[Message]) -> int:
    """Return a conservative estimate, treating each image as about 1k tokens."""
    total = 0
    for message in messages:
        total += 8 + _estimate_value(message.to_dict())
    return total
