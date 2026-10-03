"""QuantZone（宽舟科技）因子数据平台集成 — 对拍与因子值拉取（Beta）

定位：
1. 拉取 QZ 因子值（因子库 2600+，免费版每日 512MB 下载配额）；
2. 「对拍」：同股票同日期对比本地公式值与 QZ 官方因子值，快速区分
   「本地实现口径差」（时段对齐 / 竞价 bar / 归一化）与「数据差」（行情源）。

密钥：QZ_ACCESS_KEY / QZ_SIGN_SECRET / QZ_BASE_URL（.env，gitignored）。
ukey 口径：QZ 查询接受 '600519.XSHG' 风格，返回裸代码 '600519'；
本地代码为 '600519.SH'，服务内做双向映射。

对拍公式须为「原始值」公式（不带 RANK/中性化），例如价量熵对拍：
    qz_factor = feat_single_amt_ratio_entropy_30m
    local_formula = ID_PV_ENTROPY(m_close, m_volume, 30)
注意 QZ 因子名含 amt（成交额）而文档计算步骤用 volume，对拍结果可判定口径。
"""

from __future__ import annotations

import threading
from datetime import UTC

import numpy as np
import pandas as pd

_init_lock = threading.Lock()
_initialized = False

# 本地无分钟缓存时的对拍预览样本池（流动性好的沪深代表性标的）
DEFAULT_PREVIEW_CODES = [
    "600519.SH", "000858.SZ", "601318.SH", "000001.SZ", "600036.SH",
    "000333.SZ", "600276.SH", "002415.SZ", "601899.SH", "600900.SH",
]


class QuantZoneError(RuntimeError):
    pass


def is_configured() -> bool:
    from backend.config import settings

    return bool(settings.qz_access_key and settings.qz_sign_secret)


def _client():
    """初始化并返回 quantzone 模块（模块级单例，幂等）"""
    global _initialized
    try:
        import quantzone as qz
    except ImportError as e:  # pragma: no cover
        raise QuantZoneError("quantzone 未安装 — 请先 uv sync 安装依赖") from e
    from backend.config import settings

    if not is_configured():
        raise QuantZoneError(
            "QuantZone 未配置 — 请在 .env 设置 QZ_ACCESS_KEY / QZ_SIGN_SECRET"
        )
    with _init_lock:
        if not _initialized:
            qz.init(
                access_key=settings.qz_access_key,
                sign_secret=settings.qz_sign_secret,
                base_url=settings.qz_base_url,
            )
            _initialized = True
    return qz


def get_quota() -> dict:
    """配额概况（免费版：daily_quota_bytes=512MB/日）"""
    quota = _client().get_quota()
    return dict(quota) if isinstance(quota, dict) else {"raw": str(quota)}


def list_factors(keyword: str = "") -> list[dict]:
    """因子库清单（factorname/startDate/endDate），可按关键词过滤"""
    factors = _client().list_factors()
    if keyword:
        kw = keyword.lower()
        factors = [f for f in factors if kw in str(f.get("factorname", "")).lower()]
    return factors


# ── ukey 映射 ────────────────────────────────────────────────────


def to_qz_ukey(local_code: str) -> str | None:
    """'600519.SH' → '600519.XSHG'；'000858.SZ' → '000858.XSHE'；北交所等返回 None"""
    code = local_code.strip()
    num, _, suffix = code.partition(".")
    if not num.isdigit():
        return num if num else None
    if suffix.upper() == "SH" or (not suffix and num.startswith("6")):
        return f"{num}.XSHG"
    if suffix.upper() == "SZ" or (not suffix and not num.startswith("6")):
        return f"{num}.XSHE"
    return None


def _bare_code(ukey: str) -> str:
    return str(ukey).split(".")[0]


# ── 因子值拉取 ───────────────────────────────────────────────────


def get_factor_wide(
    factor: str,
    codes: list[str],
    start_date: str = "",
    end_date: str = "",
) -> pd.DataFrame:
    """拉取 QZ 因子值并转为宽表 DataFrame(index=date, columns=裸代码)"""
    ukeys = [u for u in (to_qz_ukey(c) for c in codes) if u]
    if not ukeys:
        raise QuantZoneError("无有效 ukey（仅支持沪/深代码）")
    # QZ 服务端要求必须带日期区间（缺省返回 422），空区间默认近 45 天
    from datetime import datetime, timedelta

    now = datetime.now(tz=UTC).date()
    if not start_date and not end_date:
        end_date = str(now + timedelta(days=1))
        start_date = str(now - timedelta(days=45))
    elif not start_date:
        start_date = str(pd.Timestamp(end_date) - timedelta(days=45))
    elif not end_date:
        end_date = str(now + timedelta(days=1))
    kwargs: dict = {
        "ukeys": ukeys,
        "factor": factor,
        "start_date": start_date,
        "end_date": end_date,
    }
    raw = _client().get_factors(**kwargs)
    if raw is None or len(raw) == 0:
        return pd.DataFrame()
    narrow = raw.rename(columns={"DataDate": "date", "x": "value"})
    wide = narrow.pivot_table(index="date", columns="ukey", values="value")
    wide.index = pd.to_datetime(wide.index)
    wide.columns = [_bare_code(c) for c in wide.columns]
    return wide.sort_index().sort_index(axis=1)


# ── 对拍 ─────────────────────────────────────────────────────────


def _eval_local_formula(
    formula: str, codes: list[str], start_date: str, end_date: str
) -> tuple[pd.DataFrame, list[str]]:
    """本地 5m 缓存上求值原始公式 → (日频面板, 实际有数据的裸代码列表)"""
    from backend.services.factor_operators import eval_factor_formula
    from backend.services.intraday_cleaner import load_intraday_panels
    from backend.services.intraday_operators import (
        ID_LAST,
        build_intraday_namespace,
    )

    loaded = load_intraday_panels(
        codes=codes, period="5m", start_date=start_date, end_date=end_date
    )
    ns = build_intraday_namespace(loaded["panels"], loaded["meta"])
    factor = eval_factor_formula(formula, ns)
    if isinstance(factor, pd.Series):
        factor = factor.to_frame()
    if not isinstance(factor, pd.DataFrame) or factor.empty:
        raise QuantZoneError("本地公式未产出有效面板")
    idx = pd.to_datetime(factor.index)
    if (idx.normalize() != idx).any():  # 分钟级结果折叠到日
        factor = ID_LAST(factor, 0)
    factor.index = pd.to_datetime(factor.index).normalize()
    local_codes = [_bare_code(c) for c in factor.columns]
    factor.columns = local_codes
    return factor.sort_index(), local_codes


def reconcile(
    qz_factor: str,
    local_formula: str,
    codes: list[str] | None = None,
    start_date: str = "",
    end_date: str = "",
    max_codes: int = 20,
) -> dict:
    """本地公式 vs QZ 官方因子值逐点对拍

    Returns:
        {ok, verdict, n_points, metrics{n, corr, spearman, mean_abs_diff,
        max_abs_diff, match_ratio}, sample[], local_missing, notes[]}
    """
    from backend.services import market_data

    notes: list[str] = []
    if not qz_factor or not local_formula:
        raise QuantZoneError("qz_factor 与 local_formula 均不能为空")

    if not codes:
        codes = market_data.list_cached_codes("5m", exclude_indices=True)[:max_codes]
    codes = codes[:max_codes]
    if not codes:
        # 本地无 5m 缓存且未指定股票池：用默认样本池仅预览 QZ 因子值
        codes = DEFAULT_PREVIEW_CODES[:max_codes]
        notes.append(
            "本地无 5m 分钟缓存且未指定股票池 — 使用默认样本池仅预览 QZ 因子值，"
            "下载分钟行情后可做完整对拍"
        )

    # QZ 侧
    qz_wide = get_factor_wide(qz_factor, codes, start_date, end_date)
    qz_only = qz_wide.empty
    if qz_only:
        return {
            "ok": False,
            "message": f"QZ 未返回 {qz_factor} 数据（检查因子名/日期区间/配额）",
        }

    # 本地侧（数据缺失不阻断：仍返回 QZ 预览，标注 local_missing）
    local_missing = ""
    local_wide = pd.DataFrame()
    try:
        local_wide, local_codes = _eval_local_formula(
            local_formula, codes, start_date, end_date
        )
        common = [c for c in local_codes if c in qz_wide.columns]
        if not common:
            local_missing = "本地与 QZ 无共同代码"
        local_wide = local_wide[[c for c in local_wide.columns if c in qz_wide.columns]]
        qz_wide = qz_wide[common] if common else qz_wide
    except Exception as e:
        local_missing = f"本地求值失败：{e}"

    if local_wide.empty:
        preview = qz_wide.iloc[:5, :4]
        return {
            "ok": True,
            "verdict": "local_missing",
            "qz_factor": qz_factor,
            "local_formula": local_formula,
            "n_points": 0,
            "metrics": {},
            "sample": [],
            "qz_preview": [
                {
                    "date": str(d)[:10],
                    "code": str(c),
                    "value": float(preview.loc[d, c]),
                }
                for d in preview.index
                for c in preview.columns
                if pd.notna(preview.loc[d, c])
            ][:10],
            "local_missing": local_missing
            or "本地无 5m 分钟缓存 — 请先在数据管理下载分钟行情",
            "notes": notes,
        }

    joined = local_wide.stack().rename("local").to_frame().join(
        qz_wide.stack().rename("qz"), how="inner"
    ).dropna()
    n = len(joined)
    if n < 5:
        return {
            "ok": True,
            "verdict": "insufficient_overlap",
            "qz_factor": qz_factor,
            "local_formula": local_formula,
            "n_points": n,
            "metrics": {},
            "sample": [],
            "local_missing": local_missing,
            "notes": ["重叠样本不足 5 个（日期区间/股票池交集太小）"] + notes,
        }

    a, b = joined["local"].to_numpy(), joined["qz"].to_numpy()
    diff = a - b
    scale = float(np.nanmedian(np.abs(b)))
    rel_diff = np.abs(diff) / (scale if scale > 1e-12 else 1.0)
    corr = float(np.corrcoef(a, b)[0, 1]) if np.std(a) > 0 and np.std(b) > 0 else 0.0
    spearman = float(
        pd.Series(a).rank().corr(pd.Series(b).rank())
    )
    metrics = {
        "n": int(n),
        "corr": round(corr, 6),
        "spearman": round(spearman, 6),
        "mean_abs_diff": float(np.mean(np.abs(diff))),
        "max_abs_diff": float(np.max(np.abs(diff))),
        "median_rel_diff": float(np.median(rel_diff)),
        "match_ratio_rel1pct": float(np.mean(rel_diff <= 0.01)),
    }
    verdict = (
        "match"
        if corr > 0.999 and metrics["match_ratio_rel1pct"] > 0.95
        else ("direction_match" if corr > 0.9 else "mismatch")
    )
    if verdict != "match" and "amt" in qz_factor:
        notes.append(
            "QZ 因子名含 amt（可能为成交额口径）而本地公式用 volume — "
            "若持续 mismatch，尝试把公式中的 m_volume 换成 m_amount"
        )
    sample_idx = joined.sample(min(8, n), random_state=0).index
    sample = [
        {"date": str(d)[:10], "code": str(c), "local": float(joined.loc[(d, c), "local"]), "qz": float(joined.loc[(d, c), "qz"])}
        for d, c in sample_idx
    ]
    return {
        "ok": True,
        "verdict": verdict,
        "qz_factor": qz_factor,
        "local_formula": local_formula,
        "n_points": n,
        "metrics": metrics,
        "sample": sample,
        "local_missing": local_missing,
        "notes": notes,
    }
