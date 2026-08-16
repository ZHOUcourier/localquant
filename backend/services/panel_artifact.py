"""研究面板本地 artifact 存储 — 避免全市场面板经 JSON 在前后端来回传输。

全 A 日频面板（5000~6000 只 × 3~5 年）嵌套 JSON 会达到数十/上百 MB。
计算类接口把 DataFrame 面板 pickle 到本地 data/outputs/panel_artifacts，
只向前端返回 token + 元数据 + 受限预览；分析接口按 token 读回面板。
仅限本机可信环境（与工作流节点输出同一信任边界）。
"""

from __future__ import annotations

import pickle
import time
import uuid
from pathlib import Path

import pandas as pd

from backend.config import settings

_ARTIFACT_DIR = settings.output_dir / "panel_artifacts"
_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# 面板 cell 数低于该阈值时，计算接口可以内联返回完整 JSON，方便小样本调试；
# 全市场会自动切换为 token + 预览。
INLINE_CELL_LIMIT = 250_000
PREVIEW_DATES = 10
PREVIEW_STOCKS = 60
# 本地临时 artifact 最长保留 48 小时，过期由后续存储操作顺带清理
_ARTIFACT_TTL_SECONDS = 48 * 3600


def _path(token: str) -> Path:
    return _ARTIFACT_DIR / f"{token}.pkl"


def _cleanup_expired(now: float | None = None) -> None:
    now = now or time.time()
    try:
        for p in _ARTIFACT_DIR.glob("*.pkl"):
            try:
                if now - p.stat().st_mtime > _ARTIFACT_TTL_SECONDS:
                    p.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception:
        pass


def store_panels(panels: dict[str, pd.DataFrame], token: str = "") -> str:
    """把 {name: DataFrame} 面板落盘为本地 artifact，返回 token。"""
    token = token or uuid.uuid4().hex
    _cleanup_expired()
    with open(_path(token), "wb") as f:
        pickle.dump(panels, f, protocol=pickle.HIGHEST_PROTOCOL)
    return token


def load_panels(token: str, required: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """按 token 读回面板；token 仅允许 uuid/hex 字符，防路径穿越。"""
    if not token or not all(c.isalnum() or c == "-" for c in token):
        raise ValueError("无效的面板 token")
    p = _path(token)
    if not p.exists():
        raise ValueError(f"面板 token 不存在或已过期: {token}")
    try:
        with open(p, "rb") as f:
            panels = pickle.load(f)
        if not isinstance(panels, dict):
            raise TypeError("面板 artifact 格式错误")
        for name in required or []:
            if name not in panels:
                raise ValueError(f"面板缺少 {name}")
        return panels
    except Exception as e:
        raise ValueError(f"读取面板 artifact 失败: {e}") from e


def build_panel_response(
    panels: dict[str, pd.DataFrame],
    *,
    inline_names: list[str],
    preview_names: list[str] | None = None,
) -> dict:
    """构造 compute 类接口的响应：小样本内联，大样本 token + 预览。

    panels 的 key 即响应字段名；preview_names 默认与 inline_names 相同。
    """
    token = store_panels(panels)
    total_cells = sum(int(df.size) for df in panels.values())
    preview_names = preview_names or inline_names
    resp: dict = {"panel_token": token, "panel_mode": "artifact", "total_cells": total_cells}

    if total_cells <= INLINE_CELL_LIMIT:
        resp["panel_mode"] = "inline"
        for name in inline_names:
            df = panels.get(name)
            resp[name] = _panel_to_dict(df) if df is not None else {}
    else:
        for name in inline_names:
            resp[name] = {}

    # 预览固定为「最近 N 日 × 前 M 只股票」，与全市场数据量无关
    previews: dict[str, dict] = {}
    for name in preview_names:
        df = panels.get(name)
        if df is None:
            previews[name] = {}
            continue
        tail = df.tail(PREVIEW_DATES)
        cols = list(tail.columns[:PREVIEW_STOCKS])
        previews[name] = _panel_to_dict(tail[cols])
    resp["preview"] = previews

    first = next((v for v in panels.values() if v is not None and not v.empty), None)
    if first is not None:
        resp["dates"] = [str(d.date()) for d in first.index]
        resp["stocks"] = [str(c) for c in first.columns]
        resp["preview_stocks"] = [str(c) for c in first.columns[:PREVIEW_STOCKS]]
        resp["stocks_truncated"] = first.shape[1] > PREVIEW_STOCKS
    return resp


def _panel_to_dict(panel: pd.DataFrame) -> dict:
    """DataFrame → {date_str: {code: value}}，NaN 剔除。仅供受限预览使用。"""
    out: dict[str, dict[str, float]] = {}
    for ts, row in panel.iterrows():
        clean = {str(k): float(v) for k, v in row.items() if pd.notna(v)}
        if clean:
            out[str(ts.date() if hasattr(ts, "date") else ts)] = clean
    return out


def load_token_panel(data: dict | None, token: str, field: str) -> pd.DataFrame | None:
    """从 token 或 dict 解析面板；token 优先。"""
    if token:
        return load_panels(token, [field]).get(field)
    if data:
        frame = pd.DataFrame.from_dict(data, orient="index")
        frame.index = pd.to_datetime(frame.index)
        return frame.sort_index()
    return None
