r"""本地表情包库：内容审核标注、原子落盘与关键词检索。

入口函数：:meth:`MemeLibrary.save` — 写入图片并登记检索元数据。

--------------------------------------------------------------------------
整体调用流程图
--------------------------------------------------------------------------

parse_annotation(content, suffix)                       → MemeAnnotation
    │
    │  §1 解析模型输出并规范化
    ├── _extract_json_object(content)                   → dict
    ├── _clean_text(value, limit)                       → str
    └── normalize_keywords(values, name, summary, suffix) → 5~8 个关键词

MemeLibrary.save(data, suffix, annotation=...)
    │
    │  §2 校验 + 生成唯一文件名
    ├── _image_suffix(data) / safe_meme_name(name)      → str
    └── _next_path(stem, suffix)                        → Path（图片）
    │
    │  §3 原子落盘
    ├── temp.replace(path)                              → 图片文件
    └── _write_index(records)                           → memes.json

MemeLibrary.search(keywords, limit=8)                   → list[dict]
    │
    │  §4 检索
    ├── _query_terms(keywords)                          → 归一化查询词
    ├── _records()                                      → 与磁盘对账后的索引
    └── _match_score(terms, record)                     → 相关度分值

--------------------------------------------------------------------------
目录结构
--------------------------------------------------------------------------

    <root>/
    ├── memes.json          关键词索引（原子替换写入）
    ├── 开心点赞.png
    └── 紫发俏皮少女.gif
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import re
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "MemeAnnotation",
    "MemeLibrary",
    "MemeRecord",
    "decode_image_data_url",
    "image_mimetype",
    "normalize_keywords",
    "parse_annotation",
    "safe_meme_name",
]

_NAME_RE = re.compile(r"[^\w\-\u4e00-\u9fff]+", re.UNICODE)
_SPLIT_RE = re.compile(r"[\s,，、;；/|]+")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
_WRITE_LOCK = threading.Lock()
_WEBP_HEADER_SIZE = 12
_INDEX_FILENAME = "memes.json"
_MIN_KEYWORDS = 5
_MAX_KEYWORDS = 8
_KEYWORD_MAX_CHARS = 12
_NAME_MAX_CHARS = 16
_SUMMARY_MAX_CHARS = 40
_REASON_MAX_CHARS = 100
_DEFAULT_SEARCH_LIMIT = 8
_ALLOWED_SUFFIXES = frozenset({".png", ".jpg", ".gif", ".webp"})
_MIMETYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
_PADDING_TAGS = ("表情包", "图片", "收藏")


# ═══════════════════════════════════════════════════════════════════════════
# §1 解析模型输出并规范化
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class MemeAnnotation:
    """视觉模型的审核结论与检索标注。

    Attributes:
        allowed: 是否通过内容安全审核。
        name: 简短中文名称（不含扩展名）。
        keywords: 5~8 个检索关键词。
        summary: 一句话画面/用途简介。
        reason: 审核结论的简短原因。
    """

    allowed: bool
    name: str
    keywords: tuple[str, ...]
    summary: str
    reason: str


@dataclass(frozen=True, slots=True)
class MemeRecord:
    """索引中的一行，对应磁盘上的一张图片。"""

    file: str
    name: str
    keywords: tuple[str, ...]
    summary: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        """返回交给模型选择的精简记录。"""
        return {
            "name": self.name,
            "file": self.file,
            "keywords": list(self.keywords),
            "summary": self.summary,
            "bytes": self.size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemeRecord:
        """从索引行还原记录，缺失字段按空值处理。"""
        keywords = data.get("keywords")
        items = keywords if isinstance(keywords, list) else []
        return cls(
            file=str(data["file"]),
            name=str(data.get("name") or Path(str(data["file"])).stem),
            keywords=tuple(str(item) for item in items if isinstance(item, str)),
            summary=str(data.get("summary") or ""),
            size=int(data.get("bytes") or 0),
        )


def decode_image_data_url(value: str, max_bytes: int) -> tuple[bytes, str]:
    """解码本轮消息中的内嵌图片，返回字节与允许的扩展名。

    Args:
        value: `data:image/...;base64,...` 形式的 URL。
        max_bytes: 允许的最大字节数。

    Returns:
        (图片字节, 扩展名)。

    Raises:
        ValueError: URL 不是合法的内嵌图片、编码无效、为空或超限。
    """
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
    return data, _image_suffix(data)


def _image_suffix(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(data) >= _WEBP_HEADER_SIZE and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("仅允许 PNG、JPEG、GIF 或 WebP 图片")  # noqa: TRY003


def image_mimetype(suffix: str) -> str:
    """返回图片扩展名对应的 MIME 类型。"""
    return _MIMETYPES.get(suffix.casefold(), "application/octet-stream")


def safe_meme_name(value: str) -> str:
    """把模型生成的名称转成安全的文件名主干。"""
    name = _NAME_RE.sub("-", value.strip()).strip("-_")[:48].strip("-_")
    if not name or name in {".", ".."}:
        raise ValueError("审核模型未能生成有效的语义名称")
    return name


def _clean_text(value: Any, limit: int) -> str:
    """去控制字符、裁剪长度，避免模型输出污染索引。"""
    text = _CONTROL_RE.sub(" ", str(value) if value is not None else "").strip()
    return " ".join(text.split())[:limit]


def _extract_json_object(content: str) -> dict[str, Any]:
    """从可能带 Markdown 围栏的输出中取出第一个 JSON 对象。"""
    text = content.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("审核模型未返回 JSON 对象")  # noqa: TRY003
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("审核模型返回的 JSON 无效") from exc  # noqa: TRY003
    if not isinstance(payload, dict):
        raise TypeError("审核模型返回的 JSON 无效")  # noqa: TRY003
    return payload


def normalize_keywords(
    values: Any, *, name: str, summary: str, suffix: str
) -> tuple[str, ...]:
    """规范化检索关键词，保证去重后正好落在 5~8 个。

    Args:
        values: 模型返回的关键词列表，或逗号/空白分隔的字符串。
        name: 简短名称，关键词不足时作为补充来源。
        summary: 简短简介，关键词不足时作为补充来源。
        suffix: 图片扩展名，用于补充「动图 / 静态图」标签。

    Returns:
        5~8 个去重后的关键词；关键词与名称都为空时返回空元组。
    """
    raw: list[str] = []
    if isinstance(values, str):
        raw = _SPLIT_RE.split(values)
    elif isinstance(values, Iterable):
        for item in values:
            if isinstance(item, str):
                raw.extend(_SPLIT_RE.split(item))
    if not any(term.strip() for term in raw) and not name.strip():
        return ()
    keywords: list[str] = []
    seen: set[str] = set()

    def add_all(candidates: Iterable[str], *, stop_at: int) -> None:
        for value in candidates:
            term = _clean_text(value, _KEYWORD_MAX_CHARS)
            key = term.casefold()
            if not term or key in seen or len(keywords) >= stop_at:
                continue
            seen.add(key)
            keywords.append(term)

    add_all(raw, stop_at=_MAX_KEYWORDS)
    if len(keywords) < _MIN_KEYWORDS:
        motion = "动图" if suffix.casefold() == ".gif" else "静态图"
        add_all(
            [name, *_SPLIT_RE.split(summary), motion, *_PADDING_TAGS, "聊天"],
            stop_at=_MIN_KEYWORDS,
        )
    return tuple(keywords)


def parse_annotation(content: str, *, suffix: str) -> MemeAnnotation:
    """解析视觉模型的审核 + 图像识别输出。

    Args:
        content: 模型返回的文本，允许包裹 Markdown 代码围栏。
        suffix: 图片扩展名，用于关键词补齐。

    Returns:
        归一化后的 :class:`MemeAnnotation`。

    Raises:
        ValueError: 输出不是 JSON 对象、缺少合法结论或名称无效。
    """
    payload = _extract_json_object(content)
    decision = str(payload.get("decision") or "").strip().casefold()
    if decision not in {"allow", "reject"}:
        raise ValueError("审核结论缺失")
    allowed = decision == "allow"
    name = _clean_text(payload.get("name"), _NAME_MAX_CHARS)
    if allowed:
        safe_meme_name(name)
    summary = _clean_text(payload.get("summary"), _SUMMARY_MAX_CHARS)
    return MemeAnnotation(
        allowed=allowed,
        name=name,
        keywords=normalize_keywords(
            payload.get("keywords"), name=name, summary=summary, suffix=suffix
        ),
        summary=summary,
        reason=_clean_text(payload.get("reason"), _REASON_MAX_CHARS),
    )


# ═══════════════════════════════════════════════════════════════════════════
# §2 校验 + 生成唯一文件名
# ═══════════════════════════════════════════════════════════════════════════


class MemeLibrary:
    """把审核通过的表情包与关键词索引一起保存在本地目录。"""

    def __init__(self, root: Path, max_bytes: int) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.index_path = self.root / _INDEX_FILENAME

    def _next_path(self, stem: str, suffix: str) -> Path:
        index = 1
        while True:
            extra = "" if index == 1 else f"-{index}"
            path = self.root / f"{stem}{extra}{suffix}"
            if not path.exists():
                return path
            index += 1

    def _image_paths(self) -> Iterator[Path]:
        for path in sorted(self.root.iterdir(), key=lambda item: item.name.casefold()):
            if (
                path.is_file()
                and path.suffix.casefold() in _ALLOWED_SUFFIXES
                and path.stat().st_size <= self.max_bytes
            ):
                yield path

    def save(self, data: bytes, suffix: str, *, annotation: MemeAnnotation) -> Path:
        """保存图片并登记关键词索引。

        Args:
            data: 图片原始字节。
            suffix: 与字节内容一致的扩展名。
            annotation: 已通过审核的标注结果。

        Returns:
            新写入的图片路径。

        Raises:
            ValueError: 格式、数据、审核结论或名称不合法。
        """
        if suffix not in _ALLOWED_SUFFIXES:
            raise ValueError("图片格式不支持")
        if not data or len(data) > self.max_bytes or _image_suffix(data) != suffix:
            raise ValueError("图片数据无效或超过大小限制")
        if not annotation.allowed:
            raise ValueError("图片未通过审核")
        stem = safe_meme_name(annotation.name)
        with _WRITE_LOCK:
            path = self._next_path(stem, suffix)
            temp = path.with_suffix(path.suffix + ".tmp")
            try:
                with temp.open("xb") as output:
                    output.write(data)
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
            record = MemeRecord(
                file=path.name,
                name=annotation.name,
                keywords=annotation.keywords,
                summary=annotation.summary,
                size=len(data),
            )
            try:
                self._write_index([*self._read_index(), record])
            except OSError:
                path.unlink(missing_ok=True)
                raise
        return path

    # ═══ §3 原子落盘 ═══

    def _read_index(self) -> list[MemeRecord]:
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = []
        rows = payload if isinstance(payload, list) else []
        records: list[MemeRecord] = []
        for item in rows:
            if isinstance(item, dict):
                with contextlib.suppress(KeyError, TypeError, ValueError):
                    records.append(MemeRecord.from_dict(item))
        return records

    def _write_index(self, records: list[MemeRecord]) -> None:
        temp = self.index_path.with_suffix(".json.tmp")
        with temp.open("w", encoding="utf-8") as output:
            json.dump(
                [record.to_dict() for record in records],
                output,
                ensure_ascii=False,
                indent=2,
            )
        temp.replace(self.index_path)

    def _records(self) -> list[MemeRecord]:
        """读索引并与磁盘对账：补登旧文件，丢弃已删除的记录。"""
        known = {record.file: record for record in self._read_index()}
        records: list[MemeRecord] = []
        for path in self._image_paths():
            record = known.get(path.name)
            size = path.stat().st_size
            if record is not None and record.size == size:
                records.append(record)
                continue
            stem = path.stem
            records.append(
                MemeRecord(
                    file=path.name,
                    name=stem,
                    keywords=normalize_keywords(
                        [*_SPLIT_RE.split(stem), stem],
                        name=stem,
                        summary="",
                        suffix=path.suffix,
                    ),
                    summary="",
                    size=size,
                )
            )
        return records

    def _resolve_path(self, filename: str) -> Path:
        candidate = Path(filename)
        if (
            candidate.name != filename
            or candidate.is_absolute()
            or ".." in candidate.parts
        ):
            raise ValueError("表情包名称无效")
        path = (self.root / candidate).resolve()
        if (
            not path.is_relative_to(self.root)
            or path.suffix.casefold() not in _ALLOWED_SUFFIXES
            or not path.is_file()
            or path.stat().st_size > self.max_bytes
        ):
            raise ValueError("表情包不存在或格式无效")
        return path

    def resolve(self, name: str) -> Path:
        """按完整文件名或简短名称定位图片，阻止目录穿越。

        Args:
            name: 完整文件名（含扩展名）或索引中的简短名称。

        Returns:
            图片路径。

        Raises:
            ValueError: 名称无效、不唯一或文件不可用。
        """
        label = str(name).strip()
        if not label:
            raise ValueError("表情包名称无效")
        if Path(label).suffix.casefold() in _ALLOWED_SUFFIXES:
            return self._resolve_path(label)
        matches = [record for record in self._records() if record.name == label]
        if len(matches) > 1:
            raise ValueError("同名表情包不唯一，请使用完整文件名")
        if matches:
            return self._resolve_path(matches[0].file)
        for suffix in sorted(_ALLOWED_SUFFIXES):
            with contextlib.suppress(ValueError):
                return self._resolve_path(label + suffix)
        raise ValueError("表情包不存在或格式无效")

    def list(self) -> list[dict[str, Any]]:
        """返回全部表情包的精简目录，供模型选择。"""
        return [record.to_dict() for record in self._records()]

    # ═══ §4 检索 ═══

    def search(
        self, keywords: Any, *, limit: int = _DEFAULT_SEARCH_LIMIT
    ) -> list[dict[str, Any]]:
        """按关键词检索表情包，返回按相关度排序的精简记录。

        Args:
            keywords: 关键词列表，或逗号/空白分隔的字符串。
            limit: 最多返回的条数。

        Returns:
            命中的记录；无查询词时退化为按文件名排序的目录前 `limit` 条。
        """
        terms = _query_terms(keywords)
        records = self._records()
        if not terms:
            return [record.to_dict() for record in records[:limit]]
        scored = [
            (score, record)
            for record in records
            if (score := _match_score(terms, record)) > 0
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1].file.casefold()))
        return [record.to_dict() for _, record in scored[:limit]]


def _query_terms(keywords: Any) -> tuple[str, ...]:
    if isinstance(keywords, str):
        raw = _SPLIT_RE.split(keywords)
    elif isinstance(keywords, Iterable):
        raw = []
        for item in keywords:
            if isinstance(item, str):
                raw.extend(_SPLIT_RE.split(item))
    else:
        raw = []
    terms = {term.strip().casefold() for term in raw if term.strip()}
    return tuple(sorted(terms))[:_MAX_KEYWORDS]


def _match_score(terms: tuple[str, ...], record: MemeRecord) -> int:
    keywords = [keyword.casefold() for keyword in record.keywords]
    text = f"{record.name} {record.summary} {record.file}".casefold()
    score = 0
    for term in terms:
        if any(term == keyword for keyword in keywords):
            score += 3
        elif any(term in keyword for keyword in keywords):
            score += 2
        elif term in text:
            score += 1
    return score
