"""工具基类与工具调用接口。

Tool 是一个可组合的单元：名称、描述、input_schema（JSON Schema）、
以及一个异步 handler。handler 接收解析后的参数字典和工具上下文。
category 用于权限判定区分读/写/执行。
"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

ToolCategory = Literal["read", "write", "exec", "net"]


@dataclass
class ToolContext:
    """传给工具 handler 的执行上下文。"""

    workspace: str
    additional_dirs: list[str] = field(default_factory=list)
    timeout: float = 60.0
    search_callback: Callable[[str], Awaitable[str]] | None = None

    def __post_init__(self) -> None:
        from pathlib import Path

        self.workspace = str(Path(self.workspace).resolve())
        self.additional_dirs = [str(Path(d).resolve()) for d in self.additional_dirs]


ToolHandler = Callable[[dict[str, Any], ToolContext], Awaitable[str]]


@dataclass
class Tool:
    """内置/自定义工具。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    category: ToolCategory = "exec"
    path_field: str | None = None
    command_field: str | None = None

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def extract_path(self, args: dict[str, Any]) -> str | None:
        if self.path_field and self.path_field in args:
            return str(args[self.path_field])
        for k in ("file_path", "path", "pattern"):
            if k in args:
                return str(args[k])
        return None

    def extract_command(self, args: dict[str, Any]) -> str | None:
        if self.command_field and self.command_field in args:
            return str(args[self.command_field])
        if "command" in args:
            return str(args["command"])
        return None

    async def call(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return await self.handler(args, ctx)
