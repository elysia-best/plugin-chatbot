"""按模型串行化 LLM 调用的 FIFO 闸门。

部分 AI 接口不允许并发请求（例如自托管的小模型或按 QPS 计费的服务）。
本模块在桥接层提供：

- :class:`ModelGate`：按 ``(base_url, model)`` 维度的令牌闸门，未获取到令牌的请求
  按先来后到排队，超过等待时长即放弃。
- :class:`GatedLLM`：包装 :class:`agent.llm.LLMBackend`，在进入真实模型调用前先
  :meth:`ModelGate.acquire`，结束后 :meth:`ModelGate.release`，等待阶段受排队超时
  约束，不吞掉模型自身的异常或超时。

实现放在桥接层，``agent/`` 不引入 NoneBot 或桥接依赖。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from agent.llm import LLMResponse
    from agent.messages import Message

DEFAULT_QUEUE_WAIT_SECONDS = 120.0
MIN_QUEUE_WAIT_SECONDS = 1.0
MAX_QUEUE_WAIT_SECONDS = 600.0
MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 64


def normalize_concurrency(value: Any) -> int | None:
    """把并发上限归一到 ``[1, 64]``，无效值或 ``<= 0`` 视为不限制。"""
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number < MIN_CONCURRENCY:
        return None
    return min(number, MAX_CONCURRENCY)


def _build_token_queue(limit: int) -> asyncio.Queue[None]:
    """构造一个预装满 ``limit`` 个令牌的 FIFO 队列。"""
    queue: asyncio.Queue[None] = asyncio.Queue()
    for _ in range(limit):
        queue.put_nowait(None)
    return queue


def normalize_queue_wait(value: Any) -> float:
    """把排队等待秒数归一到合法范围，缺省回落到 :data:`DEFAULT_QUEUE_WAIT_SECONDS`。"""
    try:
        seconds = float(value)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_QUEUE_WAIT_SECONDS
    if seconds <= 0:
        return DEFAULT_QUEUE_WAIT_SECONDS
    return min(max(seconds, MIN_QUEUE_WAIT_SECONDS), MAX_QUEUE_WAIT_SECONDS)


class ModelQueueTimeoutError(RuntimeError):
    """排队等待超过配置的上限（或 :data:`MAX_QUEUE_WAIT_SECONDS`）。"""

    def __init__(self, wait_seconds: float) -> None:
        super().__init__(
            f"并发排队等待超过 {wait_seconds:g} 秒，放弃本次请求"
        )
        self.wait_seconds = wait_seconds


class ModelGate:
    """FIFO 令牌闸门：同时最多 ``limit`` 个调用者进入临界区。

    ``limit`` 为空或 ``<= 0`` 时不设闸（直通），保持原有的无并发行为。令牌用
    :class:`asyncio.Queue` 装载：``acquire()`` 以 :meth:`asyncio.Queue.get` 取令牌，
    ``release()`` 用 ``put_nowait`` 归还，因此等待顺序由 asyncio 的唤醒顺序保证为
    先来后到。
    """

    def __init__(
        self,
        limit: int | None,
        *,
        queue_wait_seconds: float | None = None,
    ) -> None:
        self.limit = normalize_concurrency(limit)
        self.queue_wait_seconds = normalize_queue_wait(queue_wait_seconds)
        # 无并发闸门时不创建队列，令牌数严格等于 ``limit``。
        self._tokens = (
            _build_token_queue(self.limit) if self.limit is not None else None
        )

    @property
    def unlimited(self) -> bool:
        """是否为无并发闸门。"""
        return self._tokens is None

    async def acquire(self) -> None:
        """阻塞获取一个令牌；等待超过配置时长即抛 :class:`ModelQueueTimeoutError`。"""
        if self._tokens is None:
            return
        try:
            await asyncio.wait_for(
                self._tokens.get(), timeout=self.queue_wait_seconds
            )
        except TimeoutError as exc:
            raise ModelQueueTimeoutError(self.queue_wait_seconds) from exc

    def release(self) -> None:
        """归还令牌；调用方通常在 ``finally`` 里执行。"""
        if self._tokens is None:
            return
        self._tokens.put_nowait(None)


async def run_gated(
    gate: ModelGate,
    func: Callable[[], Awaitable[Any]],
) -> Any:
    """在闸门保护下执行一个异步工厂：FIFO 排队，超时抛 :class:`ModelQueueTimeoutError`。

    供非 ``Agent._llm.complete`` 的临时 LLM 调用复用闸门。无并发闸时直接执行；
    排队超时时 ``func`` 不会被调用。
    """
    if gate.unlimited:
        return await func()
    await gate.acquire()
    try:
        return await func()
    finally:
        gate.release()


class GatedLLM:
    """带并发闸门的 LLM 后端包装器。

    Args:
        inner: 真正发送请求的 LLM 后端（通常是 :class:`agent.llm.LLMClient`）。
        gate: 共享的 :class:`ModelGate` 实例，决定并发上限与排队超时。
    """

    def __init__(self, inner: Any, gate: ModelGate) -> None:
        self._inner = inner
        self.gate = gate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def complete(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """先排队，再调用内层后端；排队超时不进入模型调用。"""
        return await run_gated(
            self.gate,
            lambda: self._inner.complete(messages, tools, system_prompt),
        )
