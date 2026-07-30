# SPDX-License-Identifier: GPL-3.0-or-later
"""ComfyUI 协议适配层

让官方 Comfy-Org/ComfyUI_frontend（托管于 /comfy/）以为自己连接的是标准
ComfyUI 后端：
  - /comfy/api/object_info  节点定义（反射 ALL_WORK_NODES，见 adapter.py）
  - /comfy/api/prompt       提交图入队（API 格式 → runner nodes/links，见 graph.py）
  - /comfy/ws               执行进度推送（见 ws.py / queue_manager.py）
  - 其余握手/杂项接口见 routes.py

协议参考：ComfyUI（GPL-3.0）server.py 的路由契约。
"""
