"""A path-confined audio library for voice messages."""

from __future__ import annotations

from pathlib import Path

_AUDIO_SUFFIXES = {
    ".aac",
    ".amr",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".oga",
    ".opus",
    ".silk",
    ".slk",
    ".spx",
    ".wav",
    ".wma",
}


class VoiceLibrary:
    def __init__(self, root: Path, max_bytes: int) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes

    def list(self) -> list[dict[str, object]]:
        rows = []
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and path.suffix.lower() in _AUDIO_SUFFIXES:
                size = path.stat().st_size
                if size <= self.max_bytes and path.resolve().is_relative_to(self.root):
                    rows.append(
                        {"name": path.relative_to(self.root).as_posix(), "bytes": size}
                    )
        return rows

    def resolve(self, name: str) -> Path:
        rel = Path(name)
        if rel.is_absolute() or any(part in {"..", ""} for part in rel.parts):
            raise ValueError("语音文件名必须是语音库内的相对路径")
        path = (self.root / rel).resolve()
        if (
            not path.is_relative_to(self.root)
            or path.suffix.lower() not in _AUDIO_SUFFIXES
        ):
            raise ValueError("目标不在语音库内或格式不支持")
        if not path.is_file() or path.stat().st_size > self.max_bytes:
            raise ValueError("语音文件不存在或超过大小限制")
        return path

    def add(self, name: str, data: bytes) -> Path:
        filename = Path(name).name
        if (
            not filename
            or filename != name
            or "/" in filename
            or "\\" in filename
            or Path(filename).suffix.lower() not in _AUDIO_SUFFIXES
        ):
            raise ValueError("语音文件名或格式无效")
        if not data or len(data) > self.max_bytes:
            raise ValueError("语音文件为空或超过大小限制")
        path = (self.root / filename).resolve()
        if path.parent != self.root:
            raise ValueError("语音文件必须保存在语音库目录")
        if path.exists():
            raise FileExistsError(filename)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_bytes(data)
        temp.replace(path)
        return path
