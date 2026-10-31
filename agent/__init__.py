"""agent：一个可编程的类 Claude Code agent（Python 实现）。

对外 export 一组 API，可被 NoneBot 等 asyncio 应用直接 import：
    from agent import Agent, Tool, PermissionRule, ToolCall, Message, AgentResult
    from agent import PermissionMode, LLMClient, LLMResponse, Usage
    from agent.tools import builtin_tools
"""

from __future__ import annotations

from .core import Agent, AgentResult, Status, ToolExecution
from .llm import LLMClient, LLMResponse, Usage
from .messages import Message, ToolCall
from .permissions import (
    PermissionBehavior,
    PermissionContext,
    PermissionMode,
    PermissionRule,
    default_rules,
)
from .store import SessionRecord, SessionStore
from .tool import Tool, ToolContext, ToolHandler

__all__ = [
    "Agent",
    "AgentResult",
    "LLMClient",
    "LLMResponse",
    "Message",
    "PermissionBehavior",
    "PermissionContext",
    "PermissionMode",
    "PermissionRule",
    "SessionRecord",
    "SessionStore",
    "Status",
    "Tool",
    "ToolCall",
    "ToolContext",
    "ToolExecution",
    "ToolHandler",
    "Usage",
    "default_rules",
]
