"""Validated, file-backed role-card management."""

from __future__ import annotations

import re
from pathlib import Path  # noqa: TC003

_NAME_RE = re.compile(r"^[\w\-一-鿿]{1,64}$")
_MODE_TAGS = re.compile(
    r"[\[〔（(]\s*(?:一代|1\s*代|v1|reserved|二代|2\s*代|v2|reserved2)\s*[\]〕）)]",  # noqa: RUF001
    re.IGNORECASE,
)


class RoleCards:
    def __init__(self, root: Path, max_chars: int = 24_000) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_chars = max_chars

    def _path(self, name: str) -> Path:
        if not _NAME_RE.fullmatch(name) or name in {".", ".."}:
            raise ValueError("无效角色名")
        path = (self.root / f"{name}.md").resolve()
        if path.parent != self.root:
            raise ValueError("无效角色名")
        return path

    def list(self) -> list[dict[str, object]]:
        rows = []
        for path in sorted(self.root.glob("*.md"), key=lambda p: p.name.casefold()):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if path.resolve().parent != self.root:
                continue
            rows.append({"name": path.stem, "chars": len(text), "content": text})
        return rows

    def get(self, name: str) -> str:
        return self._path(name).read_text(encoding="utf-8")

    def save(self, name: str, content: str, *, create: bool = False) -> None:
        if len(content) > self.max_chars:
            raise ValueError("角色卡超过字符上限")
        path = self._path(name)
        if create and path.exists():
            raise FileExistsError(name)
        tmp = path.with_suffix(".md.tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

    def rename(self, source: str, destination: str) -> None:
        src, dst = self._path(source), self._path(destination)
        if not src.exists():
            raise FileNotFoundError(source)
        if dst.exists():
            raise FileExistsError(destination)
        src.replace(dst)

    def copy(self, source: str, destination: str) -> None:
        self.save(destination, self.get(source), create=True)

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=False)

    def render(self, name: str | None, mode: str) -> str:
        if not name:
            return ""
        text = self.get(name)
        wanted = {"reserved": "v1", "reserved2": "v2"}.get(mode)
        output: list[str] = []
        current_mode = "all"
        for source_line in text.splitlines():
            line = source_line
            if source_line.startswith("#"):
                tag = _MODE_TAGS.search(source_line)
                current_mode = "all"
                if tag:
                    marker = tag.group().casefold()
                    current_mode = (
                        "v1"
                        if any(x in marker for x in ("一代", "1", "v1", "reserved"))
                        and "reserved2" not in marker
                        else "v2"
                    )
                    line = _MODE_TAGS.sub("", line).rstrip()
            if current_mode in ("all", wanted):
                output.append(line)
        return "\n".join(output).strip()

    @staticmethod
    def inspect(content: str) -> dict[str, object]:
        sections: list[dict[str, object]] = []
        for line in content.splitlines():
            if line.startswith("#"):
                tag = _MODE_TAGS.search(line)
                sections.append(
                    {
                        "heading": _MODE_TAGS.sub("", line).strip(),
                        "mode": tag.group() if tag else "all",
                    }
                )
        return {"chars": len(content), "sections": sections}
