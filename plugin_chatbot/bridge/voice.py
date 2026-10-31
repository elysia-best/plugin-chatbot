"""Local speech synthesis and a path-confined audio library."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import threading
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
_VOICE_LOCK = threading.Lock()


class VoiceLibrary:
    def __init__(self, root: Path, max_bytes: int, max_text_chars: int) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.max_text_chars = max_text_chars

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

    async def synthesize(
        self, text: str, *, rate: int, volume: float, voice_id: str = ""
    ) -> Path:
        clean = text.strip()
        if not clean or len(clean) > self.max_text_chars:
            raise ValueError("合成文本长度超出限制")
        filename = f"tts-{hashlib.sha256(clean.encode()).hexdigest()[:16]}.wav"
        output = self.root / filename
        output.unlink(missing_ok=True)
        await asyncio.to_thread(
            self._synthesize_sync, clean, output, rate, volume, voice_id
        )
        if output.stat().st_size > self.max_bytes:
            output.unlink(missing_ok=True)
            raise ValueError("合成音频超过大小限制")
        return output

    @staticmethod
    def _synthesize_sync(
        text: str, output: Path, rate: int, volume: float, voice_id: str
    ) -> None:
        try:
            pyttsx3 = importlib.import_module("pyttsx3")
        except ImportError as exc:
            raise RuntimeError(  # noqa: TRY003
                "本地语音合成依赖缺失，请安装 pyttsx3 和系统语音引擎"
            ) from exc
        with _VOICE_LOCK:
            engine = pyttsx3.init()
            engine.setProperty("rate", max(80, min(rate, 300)))
            engine.setProperty("volume", max(0.0, min(volume, 1.0)))
            if voice_id:
                known = {voice.id for voice in engine.getProperty("voices")}
                if voice_id not in known:
                    engine.stop()
                    raise ValueError("配置的 pyttsx3 voice_id 不存在")  # noqa: TRY003
                engine.setProperty("voice", voice_id)
            try:
                engine.save_to_file(text, str(output))
                engine.runAndWait()
            finally:
                engine.stop()
        if not output.exists() or output.stat().st_size == 0:
            output.unlink(missing_ok=True)
            raise RuntimeError("pyttsx3 未生成可用音频文件")  # noqa: TRY003
