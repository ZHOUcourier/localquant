# SPDX-License-Identifier: GPL-3.0-or-later
"""WebSocket 连接管理 — ComfyUI /ws 协议

消息格式：{"type": <类型>, "data": {...}}（与方案 B.3 映射表一致）
连接建立后立即下发 status（含 sid）；客户端可发 feature_flags 协商。
"""

import uuid
from typing import Any

from fastapi import WebSocket
from loguru import logger

# 服务端能力声明（feature_flags 协商响应）
SERVER_FEATURE_FLAGS: dict[str, Any] = {
    "supports_preview_metadata": False,
    "max_upload_size": 100 * 1024 * 1024,
}


class WSManager:
    """管理所有 ComfyUI 前端 WS 连接，按 sid 定向或广播推送"""

    def __init__(self) -> None:
        self._clients: dict[str, WebSocket] = {}

    async def connect(self, ws: WebSocket, client_id: str | None) -> str:
        await ws.accept()
        sid = client_id or uuid.uuid4().hex
        self._clients[sid] = ws
        return sid

    def disconnect(self, sid: str) -> None:
        self._clients.pop(sid, None)

    async def send(self, event_type: str, data: dict, sid: str | None = None) -> None:
        """sid 为 None 时广播；定向发送失败自动清理连接"""
        message = {"type": event_type, "data": data}
        targets = (
            [(sid, self._clients[sid])]
            if sid and sid in self._clients
            else list(self._clients.items())
        )
        for cid, ws in targets:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.debug(f"WS 推送失败({cid})，移除连接: {e}")
                self.disconnect(cid)


ws_manager = WSManager()
