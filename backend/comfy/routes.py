# SPDX-License-Identifier: GPL-3.0-or-later
"""ComfyUI 协议路由 — 挂载于 /comfy/api/*、/comfy/ws、/comfy/（静态）

覆盖方案 B.1 清单：
  必须：/object_info /prompt /ws /interrupt /history /queue /system_stats /features
  次要：/view /upload/image /upload/mask /embeddings /extensions /models
        /workflow_templates /userdata* /users /view_metadata /free
"""

import asyncio
import json
import platform
import sys
import uuid as uuid_mod
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, Response

from backend.comfy.adapter import build_object_info, node_to_object_info
from backend.comfy.graph import PromptConversionError, convert_prompt
from backend.comfy.queue_manager import comfy_queue
from backend.comfy.ws import SERVER_FEATURE_FLAGS, ws_manager
from backend.config import settings
from backend.plugins.registry import ALL_WORK_NODES

router = APIRouter()

# userdata（前端设置/工作流草稿等）落盘目录
USERDATA_DIR = Path("./data/comfy_userdata")
UPLOAD_DIR = Path("./data/comfy_input")


# ---------------------------------------------------------------------------
# 节点定义
# ---------------------------------------------------------------------------


@router.get("/object_info")
async def object_info():
    return build_object_info()


@router.get("/object_info/{node_class}")
async def object_info_one(node_class: str):
    node_cls = ALL_WORK_NODES.get(node_class)
    if node_cls is None:
        return {}
    return {node_class: node_to_object_info(node_cls)}


# ---------------------------------------------------------------------------
# 提交 / 队列 / 中断
# ---------------------------------------------------------------------------


@router.post("/prompt")
async def post_prompt(request: Request):
    body = await request.json()
    prompt = body.get("prompt")
    if not isinstance(prompt, dict) or not prompt:
        return Response(
            content=json.dumps(
                {
                    "error": {
                        "type": "no_prompt",
                        "message": "No prompt provided",
                        "details": "",
                        "extra_info": {},
                    },
                    "node_errors": {},
                }
            ),
            status_code=400,
            media_type="application/json",
        )

    try:
        nodes, links = convert_prompt(prompt)
    except PromptConversionError as e:
        return Response(
            content=json.dumps(
                {
                    "error": {
                        "type": "prompt_outputs_failed_validation",
                        "message": str(e),
                        "details": "",
                        "extra_info": {},
                    },
                    "node_errors": e.node_errors,
                },
                ensure_ascii=False,
            ),
            status_code=400,
            media_type="application/json",
        )

    prompt_id = str(uuid_mod.uuid4())
    extra_data = body.get("extra_data") or {}
    client_id = body.get("client_id") or extra_data.get("client_id")
    number = comfy_queue.enqueue(prompt_id, prompt, extra_data, client_id, nodes, links)
    return {"prompt_id": prompt_id, "number": number, "node_errors": {}}


@router.get("/prompt")
async def get_prompt():
    return {"exec_info": {"queue_remaining": comfy_queue.queue_remaining}}


@router.get("/queue")
async def get_queue():
    return comfy_queue.queue_state()


@router.post("/queue")
async def post_queue(request: Request):
    body = await request.json()
    if body.get("clear"):
        comfy_queue.clear_pending()
    if body.get("delete"):
        comfy_queue.delete_pending(body["delete"])
    return {}


@router.post("/interrupt")
async def interrupt():
    comfy_queue.interrupt()
    return {}


@router.post("/free")
async def free():
    """ComfyUI 释放显存/模型接口 — 本项目无模型常驻，直接返回"""
    return {}


# ---------------------------------------------------------------------------
# 历史
# ---------------------------------------------------------------------------


@router.get("/history")
async def get_history(max_items: int | None = Query(default=None)):
    return comfy_queue.history(max_items)


@router.get("/history/{prompt_id}")
async def get_history_one(prompt_id: str):
    return comfy_queue.history_one(prompt_id)


@router.post("/history")
async def post_history(request: Request):
    body = await request.json()
    if body.get("clear"):
        comfy_queue.clear_history()
    if body.get("delete"):
        comfy_queue.delete_history(body["delete"])
    return {}


# ---------------------------------------------------------------------------
# 启动握手：system_stats / features / extensions / embeddings / models
# ---------------------------------------------------------------------------


@router.get("/system_stats")
async def system_stats():
    """真实系统信息（psutil），无 GPU 时仅报告 CPU 设备 — 零模拟数据"""
    import psutil

    vm = psutil.virtual_memory()
    devices = [
        {
            "name": "cpu",
            "type": "cpu",
            "index": 0,
            "vram_total": vm.total,
            "vram_free": vm.available,
            "torch_vram_total": 0,
            "torch_vram_free": 0,
        }
    ]
    try:
        import torch

        torch_version = torch.__version__
        if torch.backends.mps.is_available():
            devices.insert(
                0,
                {
                    "name": "mps",
                    "type": "mps",
                    "index": 0,
                    "vram_total": vm.total,
                    "vram_free": vm.available,
                    "torch_vram_total": 0,
                    "torch_vram_free": 0,
                },
            )
    except Exception:
        torch_version = ""

    return {
        "system": {
            "os": platform.system().lower(),
            "ram_total": vm.total,
            "ram_free": vm.available,
            "comfyui_version": f"localquant-{settings.version}",
            "required_frontend_version": "1.47.10",
            "python_version": sys.version,
            "pytorch_version": torch_version,
            "embedded_python": False,
            "argv": [],
        },
        "devices": devices,
    }


@router.get("/features")
async def features():
    return SERVER_FEATURE_FLAGS


# ---------------------------------------------------------------------------
# 用户设置（落盘 userdata/comfy.settings.json，与 ComfyUI 设置 API 契约一致）
# ---------------------------------------------------------------------------


def _load_settings() -> dict[str, Any]:
    f = _userdata_path("comfy.settings.json")
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _store_settings(data: dict[str, Any]) -> None:
    f = _userdata_path("comfy.settings.json")
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# 设置写锁：设置对话一次保存多个键时，前端并发发多个 POST，
# 无锁的 read-modify-write 会丢失部分键（用户反映“设置没保存住”）。
_settings_lock = asyncio.Lock()


@router.get("/settings")
async def get_settings():
    return _load_settings()


@router.get("/settings/{setting_id}")
async def get_setting(setting_id: str):
    return _load_settings().get(setting_id)


@router.post("/settings")
async def post_settings(request: Request):
    payload = await request.json()
    async with _settings_lock:
        data = _load_settings()
        data.update(payload)
        _store_settings(data)
    return Response(status_code=200)


@router.post("/settings/{setting_id}")
async def post_setting(setting_id: str, request: Request):
    value = await request.json()
    async with _settings_lock:
        data = _load_settings()
        data[setting_id] = value
        _store_settings(data)
    return Response(status_code=200)


@router.get("/i18n")
async def i18n():
    """自定义节点翻译（本项目节点名本身即中文，无需额外词条）"""
    return {}


@router.get("/extensions")
async def extensions():
    # 返回 localquant 自定义前端扩展（节点代码查看/编辑 + AI 改写）。
    # 前端以 fileURL(e)=/comfy+e 动态 import，故路径以 /extensions/ 开头。
    return ["/extensions/localquant/node_tools.js"]


@router.get("/embeddings")
async def embeddings():
    return []


@router.get("/models")
async def models():
    return []


@router.get("/models/{folder}")
async def models_folder(folder: str):
    return []


@router.get("/workflow_templates")
async def workflow_templates():
    return {}


@router.get("/view_metadata/{folder}")
async def view_metadata(folder: str):
    return {}


# ---------------------------------------------------------------------------
# /view 与上传（次要，B.5）：本项目产物为 DataFrame，报告在 Vue 外壳侧查看
# ---------------------------------------------------------------------------


@router.get("/view")
async def view(
    filename: str = Query(...),
    subfolder: str = Query(default=""),
    type: str = Query(default="output"),
):
    base = UPLOAD_DIR if type == "input" else settings.output_dir
    target = (base / subfolder / filename).resolve()
    if not str(target).startswith(str(base.resolve())) or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(target)


@router.post("/upload/image")
@router.post("/upload/mask")
async def upload_image(image: UploadFile):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / Path(image.filename or "upload.bin").name
    dest.write_bytes(await image.read())
    return {"name": dest.name, "subfolder": "", "type": "input"}


# ---------------------------------------------------------------------------
# users / userdata（单用户 + 文件落盘，让前端设置可持久化）
# ---------------------------------------------------------------------------


@router.get("/users")
async def users():
    return {"storage": "server", "migrated": True}


@router.post("/users")
async def create_user():
    return {"error": "single-user mode"}


def _userdata_path(file: str) -> Path:
    USERDATA_DIR.mkdir(parents=True, exist_ok=True)
    target = (USERDATA_DIR / file).resolve()
    if not str(target).startswith(str(USERDATA_DIR.resolve())):
        raise HTTPException(status_code=403, detail="invalid path")
    return target


@router.get("/userdata")
async def list_userdata(
    dir: str = Query(default=""),
    recurse: bool = Query(default=False),
    split: bool = Query(default=False),
    full_info: bool = Query(default=False),
):
    base = _userdata_path(dir) if dir else USERDATA_DIR
    if not base.exists():
        return []
    pattern = "**/*" if recurse else "*"
    results: list[Any] = []
    for f in base.glob(pattern):
        if not f.is_file():
            continue
        rel = str(f.relative_to(USERDATA_DIR if not dir else base))
        if full_info:
            stat = f.stat()
            results.append(
                {"path": rel, "size": stat.st_size, "modified": stat.st_mtime}
            )
        elif split:
            results.append(rel.split("/"))
        else:
            results.append(rel)
    return results


@router.get("/userdata/{file:path}")
async def get_userdata(file: str):
    target = _userdata_path(file)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(target)


@router.post("/userdata/{file:path}")
async def save_userdata(file: str, request: Request):
    target = _userdata_path(file)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(await request.body())
    stat = target.stat()
    return {"path": file, "size": stat.st_size, "modified": stat.st_mtime}


@router.delete("/userdata/{file:path}")
async def delete_userdata(file: str):
    target = _userdata_path(file)
    if target.is_file():
        target.unlink()
    return Response(status_code=204)


@router.post("/userdata/{file:path}/move/{dest:path}")
async def move_userdata(file: str, dest: str):
    src = _userdata_path(file)
    dst = _userdata_path(dest)
    if not src.is_file():
        raise HTTPException(status_code=404, detail="not found")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    stat = dst.stat()
    return {"path": dest, "size": stat.st_size, "modified": stat.st_mtime}


# ---------------------------------------------------------------------------
# 内部接口（日志面板等，避免前端报错）
# ---------------------------------------------------------------------------

internal_router = APIRouter()


@internal_router.get("/logs")
async def internal_logs():
    return ""


@internal_router.get("/logs/raw")
async def internal_logs_raw():
    return {"entries": [], "size": 0}


@internal_router.patch("/logs/subscribe")
async def internal_logs_subscribe():
    return Response(status_code=200)


@internal_router.get("/folder_paths")
async def internal_folder_paths():
    return {}


@internal_router.get("/files/{directory}")
async def internal_files(directory: str):
    return []


# ---------------------------------------------------------------------------
# WebSocket：/comfy/ws
# ---------------------------------------------------------------------------


async def websocket_endpoint(ws: WebSocket):
    client_id = ws.query_params.get("clientId")
    sid = await ws_manager.connect(ws, client_id)
    # 连接即下发 status（含 sid），与 ComfyUI 行为一致
    await ws_manager.send(
        "status",
        {
            "status": {"exec_info": {"queue_remaining": comfy_queue.queue_remaining}},
            "sid": sid,
        },
        sid,
    )
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("type") == "feature_flags":
                await ws_manager.send("feature_flags", SERVER_FEATURE_FLAGS, sid)
    except WebSocketDisconnect:
        ws_manager.disconnect(sid)
    except Exception:
        ws_manager.disconnect(sid)


# ---------------------------------------------------------------------------
# 挂载入口（main.py 调用）
# ---------------------------------------------------------------------------


def mount_comfy(app) -> None:
    """注册协议路由 + WS + 托管官方前端静态资源于 /comfy/"""
    app.include_router(router, prefix="/comfy/api", tags=["comfy"])
    app.include_router(router, prefix="/api", include_in_schema=False)  # 兼容裸 /api
    app.include_router(
        internal_router, prefix="/comfy/internal", include_in_schema=False
    )
    app.add_api_websocket_route("/comfy/ws", websocket_endpoint)
    app.add_api_websocket_route("/ws", websocket_endpoint)

    # 静态兑底：前端会拉取内置工作流模板与 user.css（本项目不提供），
    # 返回空集/空样式避免 404 与“模板列表”空弹窗遮挡画布（须在静态挂载前注册）
    @app.get("/comfy/templates/index.json", include_in_schema=False)
    @app.get("/comfy/templates/index.zh.json", include_in_schema=False)
    @app.get("/comfy/templates/index_logo.json", include_in_schema=False)
    @app.get("/comfy/templates/fuse_options.json", include_in_schema=False)
    async def _empty_templates():
        return []

    @app.get("/comfy/user.css", include_in_schema=False)
    async def _empty_user_css():
        return Response(content="", media_type="text/css")

    # localquant 自定义前端扩展（节点代码/AI）—— 必须在静态挂载前注册
    _EXT_DIR = Path(__file__).parent / "extensions"

    @app.get("/comfy/extensions/localquant/{filename}", include_in_schema=False)
    async def _localquant_extension(filename: str):
        target = (_EXT_DIR / filename).resolve()
        if target.parent != _EXT_DIR.resolve() or not target.is_file():
            raise HTTPException(status_code=404, detail="extension not found")
        return FileResponse(target, media_type="text/javascript")

    # 官方前端静态资源（comfyui-frontend-package，锚定 1.47.10）
    try:
        import comfyui_frontend_package
        from fastapi.staticfiles import StaticFiles

        static_dir = Path(comfyui_frontend_package.__file__).parent / "static"
        if static_dir.exists():
            app.mount(
                "/comfy",
                StaticFiles(directory=static_dir, html=True),
                name="comfy-frontend",
            )
    except ImportError:
        from loguru import logger

        logger.warning(
            "comfyui_frontend_package 未安装，/comfy/ 前端不可用（协议接口不受影响）"
        )
