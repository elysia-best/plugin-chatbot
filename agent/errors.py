"""上下文超限错误的识别与真实上限解析。

不同 provider 的报错文案差异很大，这里统一做两件事：
1. 判断异常是否属于「请求超出模型上下文」；
2. 尽可能从报错里解析出模型的真实上下文上限，用于自我校准。
"""

from __future__ import annotations

import re
from typing import Any

# 只有明确的上下文超限措辞才算命中，避免把鉴权/参数错误误判为超限。
_OVERFLOW_MARKERS = (
    "context_length_exceeded",
    "context length exceeded",
    "maximum context length",
    "context window",
    "too many tokens",
    "prompt is too long",
    "input is too long",
    "reduce the length",
    "maximum number of tokens",
    "range of input length",
    "上下文长度",
    "输入过长",
)

_LIMIT_PATTERNS = (
    re.compile(r"maximum context length is\s*([\d,_\.]+)", re.IGNORECASE),
    re.compile(r"context length of\s*([\d,_\.]+)", re.IGNORECASE),
    re.compile(r"context window[^0-9]{0,40}([\d,_\.]+)", re.IGNORECASE),
    re.compile(r"allocated\s*([\d,_\.]+)\s*tokens", re.IGNORECASE),
    re.compile(r"maximum number of tokens[^0-9]{0,40}([\d,_\.]+)", re.IGNORECASE),
)

# DashScope 等 provider 会返回 "Range of input length should be [1, 129024]"
_RANGE_PATTERN = re.compile(
    r"input length[^\[\]]{0,40}\[\s*[\d,_\.]+\s*,\s*([\d,_\.]+)\s*\]",
    re.IGNORECASE,
)

_MIN_LIMIT = 256
_MAX_LIMIT = 10_000_000


class ContextOverflowError(RuntimeError):
    """provider 判定本次请求超出模型上下文上限。"""

    def __init__(self, message: str, limit: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.limit = limit


def _error_text(exc: BaseException) -> str:
    parts: list[str] = [str(exc)]
    for attr in ("message", "code", "body", "param"):
        value = getattr(exc, attr, None)
        if value not in (None, ""):
            parts.append(str(value))
    response: Any = getattr(exc, "response", None)
    text = getattr(response, "text", None)
    if isinstance(text, str):
        parts.append(text[:2000])
    return " ".join(parts).casefold()


def is_context_overflow(exc: BaseException) -> bool:
    """判断异常是否为上下文超限。"""
    if isinstance(exc, ContextOverflowError):
        return True
    text = _error_text(exc)
    return any(marker in text for marker in _OVERFLOW_MARKERS)


def _to_limit(raw: str) -> int | None:
    digits = re.sub(r"[,_\.]", "", raw)
    try:
        value = int(digits)
    except (TypeError, ValueError):
        return None
    return value if _MIN_LIMIT <= value <= _MAX_LIMIT else None


def parse_context_limit(exc: BaseException) -> int | None:
    """从报错文本里解析模型真实上下文上限，解析不出则返回 None。"""
    text = _error_text(exc)
    match = _RANGE_PATTERN.search(text)
    if match:
        limit = _to_limit(match.group(1))
        if limit is not None:
            return limit
    for pattern in _LIMIT_PATTERNS:
        match = pattern.search(text)
        if match:
            limit = _to_limit(match.group(1))
            if limit is not None:
                return limit
    return None
