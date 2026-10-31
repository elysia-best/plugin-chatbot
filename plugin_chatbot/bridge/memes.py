"""Safety-conscious local storage for reviewed chat memes."""

from __future__ import annotations

import base64
import binascii
import re
import threading
from pathlib import Path
from typing import Any

_NAME_RE = re.compile(r"[^\w\-\u4e00-\u9fff]+", re.UNICODE)
_WRITE_LOCK = threading.Lock()
_WEBP_HEADER_SIZE = 12


def decode_image_data_url(value: str, max_bytes: int) -> tuple[bytes, str]:
    if not value.startswith("data:image/") or "," not in value:
        raise ValueError("只支持本轮收到的内嵌图片")
    header, encoded = value.split(",", 1)
    if ";base64" not in header:
        raise ValueError("图片编码格式无效")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("图片数据无效") from exc
    if not data or len(data) > max_bytes:
        raise ValueError("图片为空或超过大小限制")
    suffix = _image_suffix(data)
    return data, suffix


def _image_suffix(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if (
        len(data) >= _WEBP_HEADER_SIZE
        and data[:4] == b"RIFF"
        and data[8:12] == b"WEBP"
    ):
        return ".webp"
    raise ValueError("仅允许 PNG、JPEG、GIF 或 WebP 图片")  # noqa: TRY003


def safe_meme_name(value: str) -> str:
    name = _NAME_RE.sub("-", value.strip()).strip("-_")[:48].strip("-_")
    if not name or name in {".", ".."}:
        raise ValueError("审核模型未能生成有效的语义名称")
    return name


class MemeLibrary:
    def __init__(self, root: Path, max_bytes: int) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes

    def save(self, name: str, data: bytes, suffix: str) -> Path:
        if suffix not in {".png", ".jpg", ".gif", ".webp"}:
            raise ValueError("图片格式不支持")
        if not data or len(data) > self.max_bytes or _image_suffix(data) != suffix:
            raise ValueError("图片数据无效或超过大小限制")
        stem = safe_meme_name(name)
        with _WRITE_LOCK:
            index = 1
            while True:
                extra = "" if index == 1 else f"-{index}"
                path = self.root / f"{stem}{extra}{suffix}"
                if not path.exists():
                    break
                index += 1
            temp = path.with_suffix(path.suffix + ".tmp")
            try:
                with temp.open("xb") as output:
                    output.write(data)
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
        return path

    def resolve(self, name: str) -> Path:
        candidate = Path(name)
        if candidate.name != name or candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("表情包名称无效")
        path = (self.root / candidate).resolve()
        if (
            not path.is_relative_to(self.root)
            or path.suffix.lower() not in {".png", ".jpg", ".gif", ".webp"}
            or not path.is_file()
            or path.stat().st_size > self.max_bytes
        ):
            raise ValueError("表情包不存在或格式无效")
        return path

    def list(self) -> list[dict[str, Any]]:
        return [
            {"name": path.name, "bytes": path.stat().st_size}
            for path in sorted(
                self.root.iterdir(), key=lambda item: item.name.casefold()
            )
            if (
                path.is_file()
                and path.suffix.lower() in {".png", ".jpg", ".gif", ".webp"}
                and path.stat().st_size <= self.max_bytes
            )
        ]
