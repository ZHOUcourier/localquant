"""后台任务生命周期管理

FastAPI 路由里常见的 `asyncio.create_task(...)` 写法如果不保存引用，事件循环
只持有任务的弱引用，请求返回后任务可能被垃圾回收，表现为「后台任务永远不执行」。
本模块统一保存任务引用，任务完成后自动释放，避免内存累积。
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

_background_tasks: set[asyncio.Task] = set()


def spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """创建后台任务并持有强引用，完成后自动从集合移除"""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
