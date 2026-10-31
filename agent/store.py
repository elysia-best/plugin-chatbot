"""会话存储：多 chat + workspace 级 JSONL 持久化。

参考 claude-code 的会话转录模型（每会话一个 .jsonl，逐条追加），
但存储目录设为 workspace 级别：<workspace>/.agent/sessions/<chat_id>.jsonl。
"""

from __future__ import annotations

import contextlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .messages import Message


@dataclass
class SessionRecord:
    """一个会话的元信息。"""

    chat_id: str
    alias: str | None = None
    title: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    message_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "alias": self.alias,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SessionRecord":
        return cls(
            chat_id=d["chat_id"],
            alias=d.get("alias"),
            title=d.get("title"),
            created_at=d.get("created_at", 0.0),
            updated_at=d.get("updated_at", 0.0),
            message_count=d.get("message_count", 0),
        )


class SessionStore:
    """会话存储：每个 chat 一个 .jsonl，别名映射存 alias.json。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._alias_file = self.root / "alias.json"
        self._chat_cache: dict[str, list[Message]] = {}
        self._write_cursor: dict[str, int] = {}
        self._aliases: dict[str, str] = {}  # alias -> chat_id
        self._load_aliases()

    # --- 路径 ---

    def _chat_path(self, chat_id: str) -> Path:
        return self.root / f"{chat_id}.jsonl"

    def _record_path(self, chat_id: str) -> Path:
        return self.root / f"{chat_id}.meta.json"

    def _load_aliases(self) -> None:
        if self._alias_file.exists():
            try:
                data = json.loads(self._alias_file.read_text(encoding="utf-8"))
                self._aliases = dict(data.get("alias_to_chat", {}))
            except (OSError, ValueError):
                self._aliases = {}

    def _save_aliases(self) -> None:
        with contextlib.suppress(OSError):
            self._alias_file.write_text(
                json.dumps(
                    {"alias_to_chat": self._aliases}, ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            )

    # --- 创建/查询 ---

    def new_chat(
        self, alias: str | None = None, title: str | None = None
    ) -> SessionRecord:
        chat_id = uuid.uuid4().hex
        rec = SessionRecord(chat_id=chat_id, alias=alias, title=title)
        if alias:
            self._aliases[alias] = chat_id
            self._save_aliases()
        self._write_cursor[chat_id] = 0
        self._chat_cache[chat_id] = []
        return rec

    def resolve(self, chat_id_or_alias: str) -> str | None:
        """用 alias 或直接 UUID 引用解析出 chat_id。

        同时识别磁盘已有文件和内存中已创建（未落盘）的 chat。
        """
        if chat_id_or_alias in self._aliases:
            return self._aliases[chat_id_or_alias]
        if self._chat_path(chat_id_or_alias).exists():
            return chat_id_or_alias
        if chat_id_or_alias in self._chat_cache:
            return chat_id_or_alias
        return None

    def exists(self, chat_id: str) -> bool:
        resolved = self.resolve(chat_id)
        if resolved is None:
            return False
        return self._chat_path(resolved).exists() or resolved in self._chat_cache

    def get(self, chat_id: str) -> SessionRecord | None:
        resolved = self.resolve(chat_id)
        if not resolved:
            return None
        rec = self._read_record(resolved)
        if rec:
            return rec
        # 内存中已有但未落盘
        if resolved in self._chat_cache:
            return SessionRecord(chat_id=resolved)
        return None

    def list(self) -> list[SessionRecord]:
        records: list[SessionRecord] = []
        for f in sorted(self.root.glob("*.meta.json")):
            chat_id = f.stem.removesuffix(".meta")
            rec = self._read_record(chat_id)
            if rec:
                records.append(rec)
        return records

    def delete(self, chat_id: str) -> bool:
        resolved = self.resolve(chat_id)
        if not resolved:
            return False
        for p in (self._chat_path(resolved), self._record_path(resolved)):
            if p.exists():
                p.unlink()
        self._chat_cache.pop(resolved, None)
        self._write_cursor.pop(resolved, None)
        # 清理 alias
        to_remove = [a for a, c in self._aliases.items() if c == resolved]
        for a in to_remove:
            del self._aliases[a]
        self._save_aliases()
        return True

    # --- 读写消息 ---

    def cache(self, chat_id: str) -> list[Message]:
        """返回该 chat 的消息列表（内部引用，权威来源）。

        已加载则直接返回；否则从磁盘加载到缓存。调用方可直接 append。
        """
        resolved = self.resolve(chat_id)
        if not resolved:
            resolved = chat_id
        if resolved not in self._chat_cache:
            messages: list[Message] = []
            path = self._chat_path(resolved)
            if path.exists():
                for raw in path.read_text(encoding="utf-8").splitlines():
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        if "m" in item:
                            messages.append(Message.from_dict(item["m"]))
                    except (ValueError, KeyError, TypeError):
                        continue
            self._chat_cache[resolved] = messages
            self._write_cursor[resolved] = len(messages)
        return self._chat_cache[resolved]

    def load_messages(self, chat_id: str) -> list[Message]:
        return list(self.cache(chat_id))

    def append(self, chat_id: str, message: Message) -> None:
        self.cache(chat_id).append(message)

    def save(self, chat_id: str) -> None:
        """把该 chat 的未落盘消息追加写入 .jsonl。"""
        resolved = self.resolve(chat_id)
        if not resolved:
            return
        messages = self._chat_cache.get(resolved, [])
        start = self._write_cursor.get(resolved, 0)
        new_msgs = messages[start:]
        if new_msgs:
            path = self._chat_path(resolved)
            with path.open("a", encoding="utf-8") as f:
                for m in new_msgs:
                    f.write(
                        json.dumps(
                            {"t": time.time(), "m": m.to_dict()}, ensure_ascii=False
                        )
                        + "\n"
                    )
            self._write_cursor[resolved] = len(messages)
        self._touch_record(resolved, len(messages))

    def replace(self, chat_id: str, messages: list[Message]) -> None:
        """Atomically replace a chat transcript, for example after compaction."""
        resolved = self.resolve(chat_id) or chat_id
        path = self._chat_path(resolved)
        temp = path.with_suffix(".jsonl.tmp")
        with temp.open("w", encoding="utf-8") as stream:
            for message in messages:
                stream.write(
                    json.dumps(
                        {"t": time.time(), "m": message.to_dict()},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        temp.replace(path)
        cached = self._chat_cache.setdefault(resolved, [])
        cached[:] = messages
        self._write_cursor[resolved] = len(messages)
        self._touch_record(resolved, len(messages))

    def save_all(self) -> None:
        for chat_id in list(self._chat_cache.keys()):
            self.save(chat_id)

    def _touch_record(self, chat_id: str, message_count: int) -> None:
        rec = self._read_record(chat_id) or SessionRecord(chat_id=chat_id)
        rec.message_count = message_count
        rec.updated_at = time.time()
        with contextlib.suppress(OSError):
            self._record_path(chat_id).write_text(
                json.dumps(rec.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _read_record(self, chat_id: str) -> SessionRecord | None:
        p = self._record_path(chat_id)
        if not p.exists():
            return None
        try:
            return SessionRecord.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def record_alias(self, chat_id: str, alias: str) -> None:
        self._aliases[alias] = chat_id
        self._save_aliases()
