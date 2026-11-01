"""权限与安全判定。

镜像 claude-code 的权限模型（PermissionMode / PermissionRule / 危险路径保护）：
- PermissionMode: default / acceptEdits / bypassPermissions / dontAsk / plan
- 规则: allow / deny / ask，按 tool 名称 + 可选路径/命令 pattern 匹配
- 工作区: 主目录 + additional_dirs，用 realpath 归一化做前缀判断（含 symlink）
- 危险文件/目录（.git/ .env .vscode/ ~/.ssh 等）即使 bypass 也强制 ask
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .tool import ToolCategory

PermissionMode = Literal[
    "default", "acceptEdits", "bypassPermissions", "dontAsk", "plan"
]
PermissionBehavior = Literal["allow", "deny", "ask"]


# 危险目录（相对路径段），保护其不被自动编辑
DANGEROUS_DIRS = (
    ".git",
    ".env",
    ".vscode",
    ".idea",
    ".claude",
    ".ssh",
    ".venv",
    "node_modules",
)
# 危险文件
DANGEROUS_FILES = (
    ".gitconfig",
    ".gitmodules",
    ".bashrc",
    ".bash_profile",
    ".zshrc",
    ".profile",
    ".env",
    ".mcp.json",
)


def _resolve(path: str) -> str:
    """绝对化并解析 symlink，等价于 _resolve(p)。"""
    return str(Path(path).resolve())


@dataclass
class PermissionRule:
    """一条权限规则。

    pattern 可匹配 tool 名（"Bash"）、tool 名 + 内容（"Read(./a.txt)"）
    或路径通配（"./src/**"）。为空表示整类工具。
    """

    tool: str
    behavior: PermissionBehavior = "allow"
    pattern: str | None = None
    source: str = "user"  # user / session / cli

    def matches(
        self, tool_name: str, path: str | None = None, command: str | None = None
    ) -> bool:
        if tool_name != self.tool and self.tool not in ("*", "all"):
            return False
        if self.pattern is None:
            return True
        candidates: list[str] = []
        if path:
            candidates.append(path)
        if command:
            candidates.append(command)
        if not candidates:
            return False
        return any(_wildcard_match(self.pattern, cand) for cand in candidates)


def _wildcard_match(pattern: str, value: str) -> bool:
    pat = pattern.replace("\\", "/")
    val = value.replace("\\", "/")
    pat = pat.replace("/**/", "/[^/]*/")
    if pat.endswith("/**"):
        pat = pat[:-3] + "/.*"
    regex = re.escape(pat).replace(r"\*", ".*").replace(r"\?", ".")
    return re.fullmatch(regex, val) is not None


@dataclass
class PermissionContext:
    """权限上下文：模式 + 规则 + 工作区目录。"""

    mode: PermissionMode = "default"
    workspace: str | None = None
    additional_dirs: list[str] = field(default_factory=list)
    rules: list[PermissionRule] = field(default_factory=list)
    session_allowed_dirs: list[str] = field(default_factory=list)

    def all_workspace_dirs(self) -> list[str]:
        dirs: list[str] = []
        if self.workspace:
            dirs.append(os.path.realpath(self.workspace))
        dirs.extend(os.path.realpath(d) for d in self.additional_dirs)
        return dirs

    def in_workspace(self, path: str) -> bool:
        real = _resolve(path)
        for base in self.all_workspace_dirs():
            base_real = os.path.realpath(base)
            try:
                if os.path.commonpath([real, base_real]) == base_real:
                    return True
            except ValueError:
                continue
        return False

    def in_session_allowed(self, path: str) -> bool:
        real = _resolve(path)
        for base in self.session_allowed_dirs:
            base_real = os.path.realpath(base)
            try:
                if os.path.commonpath([real, base_real]) == base_real:
                    return True
            except ValueError:
                continue
        return False

    def _find_rule(
        self, tool_name: str, path: str | None = None, command: str | None = None
    ) -> PermissionRule | None:
        for rule in self.rules:
            if rule.matches(tool_name, path, command):
                return rule
        return None

    def check(  # noqa: C901, PLR0911
        self,
        tool_name: str,
        path: str | None = None,
        command: str | None = None,
        category: ToolCategory = "exec",
    ) -> PermissionBehavior:
        """按 claude-code 优先级判定：deny > 规则 > 模式默认。

        返回 allow / deny / ask。
        """
        rule = self._find_rule(tool_name, path, command)
        if rule and rule.behavior == "deny":
            return "deny"

        if path and self._is_dangerous_path(path):
            return "ask"

        if rule and rule.behavior == "allow":
            return "allow"
        if rule and rule.behavior == "ask":
            return "ask"

        if self.mode == "bypassPermissions":
            return "allow"
        if self.mode == "dontAsk":
            return "deny"

        if self.mode == "acceptEdits":
            if path and (self.in_workspace(path) or self.in_session_allowed(path)):
                return "allow"
            if path:
                return "ask"
            return "ask"

        # default / plan
        if path:
            # 读操作在工作区内放行；写仍需 ask
            if category == "read" and (
                self.in_workspace(path) or self.in_session_allowed(path)
            ):
                return "allow"
            if category == "read":
                return "ask"
            return "ask"
        # 无 path（如 Bash / 网络）默认 ask
        return "ask"

    def _is_dangerous_path(self, path: str) -> bool:
        real = _resolve(path)
        parts = Path(real).parts
        for p in parts:
            low = p.lower()
            if low in DANGEROUS_DIRS:
                return True
        name = Path(real).name.lower()
        return name in DANGEROUS_FILES


def default_rules() -> list[PermissionRule]:
    """默认规则集：只对只读安全工具自动放行。

    写/命令类工具不设规则，由 PermissionMode 决定
    （default/plan → ask，acceptEdits → 工作区内放行，
    bypassPermissions → 放行，dontAsk → 拒绝）。
    """
    return [
        PermissionRule(tool="Read", behavior="allow"),
        PermissionRule(tool="Glob", behavior="allow"),
        PermissionRule(tool="Grep", behavior="allow"),
        PermissionRule(tool="WebFetch", behavior="allow"),
        PermissionRule(tool="ProjectMemoryRead", behavior="allow"),
    ]
