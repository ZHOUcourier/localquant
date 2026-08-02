"""因子路由 — 直接调用本地因子研究服务"""

import time
import uuid

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from backend.database import get_db
from backend.models.factor import (
    AlphaLensRequest,
    CorrelationRequest,
    FactorCreate,
    ICAnalysisRequest,
    NeutralizeRequest,
    QuantileRequest,
)
from backend.services import market_data
from backend.services.factor_research import factor_research

router = APIRouter()


# 因子编写参考（字段 + 算子）— 供前端「变量参考」面板展示，与求值环境对齐
_FACTOR_REFERENCE = {
    "fields": [
        {"name": "open / OPEN", "desc": "开盘价", "available": True},
        {"name": "high / HIGH", "desc": "最高价", "available": True},
        {"name": "low / LOW", "desc": "最低价", "available": True},
        {"name": "close / CLOSE", "desc": "收盘价", "available": True},
        {"name": "volume / VOLUME", "desc": "成交量", "available": True},
        {"name": "amount / AMOUNT", "desc": "成交额", "available": True},
        {
            "name": "vwap / VWAP",
            "desc": "成交均价（≈amount/volume）",
            "available": True,
        },
        {"name": "returns", "desc": "日收益率", "available": True},
        {"name": "adv20", "desc": "20 日平均成交量", "available": True},
        {
            "name": "turnover / market_cap",
            "desc": "换手率 / 市值（需已下载股本快照）",
            "available": False,
        },
        {
            "name": "fund_eps / fund_pb / fund_pe / fund_roe / FUND_*",
            "desc": "基本面字段（需先下载财务数据；公告时间对齐，无前视）",
            "available": False,
        },
    ],
    "operator_groups": [
        {
            "group": "逐元素",
            "ops": ["ABS(X)", "LOG(X)", "SIGN(X)", "POWER(X,N)", "SIGNEDPOWER(X,N)"],
        },
        {
            "group": "截面",
            "ops": ["RANK(X) 排名分位数", "SCALE(X,a) 缩放", "ZSCORE(X) 标准化"],
        },
        {
            "group": "时序",
            "ops": [
                "DELAY(X,N) 延后",
                "DELTA(X,N) 差分",
                "MA(X,N) 均值",
                "SUM(X,N)",
                "STD(X,N) 标准差",
                "TS_MAX/TS_MIN(X,N)",
                "TS_RANK(X,N) 时序排名",
                "DECAYLINEAR(X,N) 衰减加权",
                "EMA/WMA/SMA(X,N)",
                "RETURNS(X,N)",
                "COUNT(cond,N)",
            ],
        },
        {
            "group": "双序列",
            "ops": ["MAX(A,B)", "MIN(A,B)", "MEAN(A,B)", "IF(cond,A,B)"],
        },
        {
            "group": "双面板滚动",
            "ops": [
                "CORR(A,B,N) 滚动相关",
                "COV(A,B,N) 协方差",
                "SUMIF(cond,B,N)",
                "REGBETA/REGRESI(A,B,N) 回归",
            ],
        },
        {
            "group": "技术指标",
            "ops": [
                "ADV(VOLUME,N)",
                "RSI(X,N)",
                "MACD/MACD_DIF/MACD_DEA(close)",
                "BOLL_UPPER/MID/LOWER(close,20,2)",
                "ATR(high,low,close,N)",
                "CCI(high,low,close,N)",
                "WR(close,high,low,N)",
                "BIAS(close,N)",
                "KDJ_K/D/J(close,high,low)",
                "OBV(close,volume)",
            ],
        },
    ],
    "examples": [
        {"title": "20 日动量排名", "formula": "RANK((CLOSE / DELAY(CLOSE, 20)) - 1)"},
        {"title": "价量相关性", "formula": "CORRELATION(CLOSE, VOLUME, 20)"},
        {
            "title": "Alpha101 #40",
            "formula": "((-1 * RANK(STDDEV(HIGH, 10))) * CORRELATION(HIGH, VOLUME, 10))",
        },
    ],
}


@router.get("/reference")
async def factor_reference():
    """因子编写参考：可用字段、算子与示例（与公式求值环境一致）

    turnover/market_cap 的可用性根据参考数据快照现状动态标注（需已下载股本快照）。
    """
    from backend.services import reference_data

    ref_status = reference_data.reference_status()
    cap_ready = ref_status.get("capital", {}).get("rows", 0) > 0
    ind_ready = ref_status.get("industry", {}).get("rows", 0) > 0
    from backend.services import fundamental
    fund_ready = fundamental.snapshot_status()["ready"]

    result = dict(_FACTOR_REFERENCE)
    fields = [dict(f) for f in _FACTOR_REFERENCE["fields"]]
    for f in fields:
        if f["name"] == "turnover / market_cap":
            f["available"] = cap_ready
        elif f["name"].startswith("fund_"):
            f["available"] = fund_ready
        elif f["name"] == "INDUSTRY_NEUTRALIZE":
            f["available"] = ind_ready
    result["fields"] = fields
    return result


def _dict_to_df(d: dict) -> pd.DataFrame:
    """将 {date: {code: value}} 嵌套字典转为 DataFrame (index=date, columns=stocks)"""
    return pd.DataFrame.from_dict(d, orient="index")


class FactorComputeRequest(BaseModel):
    mode: str = "formula"  # formula | code
    formula: str = ""
    code: str = ""
    stock_pool: list[str] = []
    start_date: str = ""
    end_date: str = ""


@router.post("/compute")
async def compute_factor(req: FactorComputeRequest):
    """基于本地行情数据计算因子值，同时返回远期收益供 IC/分层分析使用"""
    try:
        panels = market_data.load_price_panels(
            codes=req.stock_pool,
            start_date=req.start_date,
            end_date=req.end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    close = panels["close"]
    # 构建公式求值命名空间：基础字段 + vwap/returns + 全部量化算子
    # （RANK/DELAY/DELTA/CORR/TS_RANK/DECAYLINEAR 等，大小写均可），
    # 使因子库中的 Alpha101/Alpha191 公式可直接运行。
    from backend.services.factor_operators import build_operator_namespace

    eval_ctx = build_operator_namespace(panels)

    try:
        if req.mode == "formula":
            if not req.formula.strip():
                raise ValueError(
                    "因子公式为空，请输入表达式，如: RANK(close / DELAY(close, 5) - 1)"
                )
            # 支持多行公式：取最后一个非空表达式作为因子值（对齐官网中间变量写法）
            formula_lines = [
                ln
                for ln in req.formula.strip().splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            if len(formula_lines) > 1:
                exec_ctx = dict(eval_ctx)
                exec("\n".join(formula_lines[:-1]), {"__builtins__": {}}, exec_ctx)  # noqa: S102
                factor = eval(formula_lines[-1], {"__builtins__": {}}, exec_ctx)  # noqa: S307
            else:
                factor = eval(req.formula, {"__builtins__": {}}, eval_ctx)  # noqa: S307
        else:
            if not req.code.strip():
                raise ValueError("因子代码为空")
            exec_ctx = dict(eval_ctx)
            exec(req.code, {"__builtins__": __builtins__}, exec_ctx)  # noqa: S102
            fn = exec_ctx.get("compute_factor")
            if callable(fn):
                factor = fn(close=close, volume=panels.get("volume"))
            else:
                factor = exec_ctx.get("factor_data")
            if factor is None:
                raise ValueError("代码未定义 compute_factor 函数或 factor_data 变量")
        if isinstance(factor, pd.Series):
            factor = factor.to_frame()
        if not isinstance(factor, pd.DataFrame):
            raise ValueError(
                f"因子计算结果应为 DataFrame，得到 {type(factor).__name__}"
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"因子计算失败: {e}")
        raise HTTPException(status_code=400, detail=f"因子计算失败: {e}")

    factor = factor.dropna(how="all")
    if factor.empty:
        raise HTTPException(
            status_code=400, detail="因子计算结果为空（可能回看期超过数据长度）"
        )

    # 次日收益（T 日因子对齐 T+1 收益由 IC 分析接口内部处理）
    returns = close.pct_change()

    return {
        "dates": [str(d.date()) for d in factor.index],
        "stocks": list(factor.columns),
        "factor_data": market_data.panel_to_dict(factor),
        "return_data": market_data.panel_to_dict(returns),
    }


@router.post("/ic-analysis")
async def ic_analysis(req: ICAnalysisRequest):
    try:
        factor_df = _dict_to_df(req.factor_data)
        return_df = _dict_to_df(req.return_data)
        factor_df.index = pd.to_datetime(factor_df.index)
        return_df.index = pd.to_datetime(return_df.index)
        result = factor_research.ic_analysis(factor_df, return_df, req.periods)
        return result
    except Exception as e:
        logger.error(f"IC分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"IC分析失败: {e}")


@router.post("/quantile")
async def quantile_analysis(req: QuantileRequest):
    try:
        factor_df = _dict_to_df(req.factor_data)
        return_df = _dict_to_df(req.return_data)
        factor_df.index = pd.to_datetime(factor_df.index)
        return_df.index = pd.to_datetime(return_df.index)
        result = factor_research.quantile_analysis(factor_df, return_df, req.n_groups)
        return result
    except Exception as e:
        logger.error(f"分层分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"分层分析失败: {e}")


@router.post("/decay")
async def factor_decay(req: ICAnalysisRequest):
    """因子衰减：IC 随持有期增长的变化（与因子分析节点同源）"""
    try:
        factor_df = _dict_to_df(req.factor_data)
        return_df = _dict_to_df(req.return_data)
        factor_df.index = pd.to_datetime(factor_df.index)
        return_df.index = pd.to_datetime(return_df.index)
        max_period = max(req.periods) if req.periods else 20
        return factor_research.factor_decay(factor_df, return_df, max_period)
    except Exception as e:
        logger.error(f"因子衰减分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"因子衰减分析失败: {e}")


@router.post("/turnover")
async def factor_turnover(req: ICAnalysisRequest):
    """因子换手率（与因子分析节点同源）"""
    try:
        factor_df = _dict_to_df(req.factor_data)
        factor_df.index = pd.to_datetime(factor_df.index)
        return factor_research.turnover_analysis(factor_df)
    except Exception as e:
        logger.error(f"换手率分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"换手率分析失败: {e}")


@router.post("/analysis")
async def full_analysis(req: QuantileRequest):
    """完整单因子分析报告（与工作流「因子分析」节点同源、同口径）

    返回数据卡指标、分组绩效表、分组/超额累计收益、IC 与 Rank_IC 的
    时序/累计/分布/自相关/衰减、最新一期因子值排名。
    """
    try:
        factor_df = _dict_to_df(req.factor_data)
        return_df = _dict_to_df(req.return_data)
        factor_df.index = pd.to_datetime(factor_df.index)
        return_df.index = pd.to_datetime(return_df.index)
        return factor_research.full_factor_analysis(
            factor_df, return_df, n_groups=req.n_groups
        )
    except Exception as e:
        logger.error(f"因子分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"因子分析失败: {e}")


@router.post("/alphalens")
async def alphalens_analysis(req: AlphaLensRequest):
    """AlphaLens 式因子分析（调用 alphalens-reloaded）：行业分组 IC/分层收益、
    因子加权多空组合、分位数换手率、因子秩自相关（与自研 factor_research 互补）
    """
    from backend.services.alphalens_analysis import full_alphalens_analysis

    try:
        factor_df = _dict_to_df(req.factor_data)
        return_df = _dict_to_df(req.return_data)
        factor_df.index = pd.to_datetime(factor_df.index)
        return_df.index = pd.to_datetime(return_df.index)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"数据解析失败: {e}")
    try:
        return full_alphalens_analysis(
            factor_df,
            return_df,
            periods=req.periods,
            quantiles=req.quantiles,
            sector_map=req.sector_map or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"AlphaLens 分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"AlphaLens 分析失败: {e}")


@router.post("/neutralize")
async def neutralize(req: NeutralizeRequest):
    try:
        factor_df = _dict_to_df(req.factor_data)
        industry_df = _dict_to_df(req.industry_data)
        market_cap_df = _dict_to_df(req.market_cap_data)
        factor_df.index = pd.to_datetime(factor_df.index)
        industry_df.index = pd.to_datetime(industry_df.index)
        market_cap_df.index = pd.to_datetime(market_cap_df.index)
        result = factor_research.neutralize(factor_df, industry_df, market_cap_df)
        return result.fillna("").to_dict(orient="index")
    except Exception as e:
        logger.error(f"中性化失败: {e}")
        raise HTTPException(status_code=500, detail=f"中性化失败: {e}")


@router.post("/correlation")
async def correlation(req: CorrelationRequest):
    try:
        factors = {}
        for name, data in req.factors.items():
            df = _dict_to_df(data)
            df.index = pd.to_datetime(df.index)
            factors[name] = df
        result = factor_research.factor_correlation(factors)
        return result
    except Exception as e:
        logger.error(f"相关性分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"相关性分析失败: {e}")


@router.post("/combine")
async def combine_factors(req: CorrelationRequest):
    """多因子合成 — 复用 CorrelationRequest 结构传入 factors"""
    try:
        factors = {}
        for name, data in req.factors.items():
            df = _dict_to_df(data)
            df.index = pd.to_datetime(df.index)
            factors[name] = df
        result = factor_research.multi_factor_combine(factors)
        return result.fillna(0).to_dict(orient="index")
    except Exception as e:
        logger.error(f"因子合成失败: {e}")
        raise HTTPException(status_code=500, detail=f"因子合成失败: {e}")


@router.get("/library")
async def list_factors():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM factors ORDER BY created_at DESC")
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


@router.post("/library")
async def register_factor(req: FactorCreate):
    factor_id = str(uuid.uuid4())
    now = int(time.time() * 1000)
    db = await get_db()
    # 同名因子版本自增（保留历史行，不覆盖），便于查看/回滚历史公式
    cursor = await db.execute(
        "SELECT MAX(version) FROM factors WHERE name = ?", (req.name,)
    )
    row = await cursor.fetchone()
    next_version = (row[0] or 0) + 1
    await db.execute(
        "INSERT INTO factors (id, name, description, category, formula, code, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            factor_id,
            req.name,
            req.description,
            req.category,
            req.formula,
            req.code,
            next_version,
            now,
            now,
        ),
    )
    await db.commit()
    await db.close()

    # 注册后自动跑一次本地分析并存入实验表（最佳努力；数据不足则跳过，不阻断注册）
    analysis = {"ok": False, "message": "未分析"}
    try:
        formula = (req.formula or "").strip()
        if formula:
            analysis = factor_research.analyze_formula_on_local(formula)
            if analysis.get("ok"):
                from backend.models.experiment import ExperimentCreate
                from backend.services.experiment_service import experiment_service

                await experiment_service.create(
                    ExperimentCreate(
                        source="factor",
                        source_id=factor_id,
                        name=f"{req.name} v{next_version}",
                        note="注册时自动指标快照",
                        tags=["factor", "register"],
                        params={"formula": formula, "version": next_version},
                        metrics=analysis["metrics"],
                    )
                )
    except Exception as e:
        logger.warning(f"自建因子注册分析快照失败（不影响注册）: {e}")

    return {
        "id": factor_id,
        "name": req.name,
        "version": next_version,
        "analysis": analysis,
    }


@router.get("/library/{name}/versions")
async def factor_versions(name: str):
    """同名因子的历史版本列表（按版本降序），供查看/回滚"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM factors WHERE name = ? ORDER BY version DESC", (name,)
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


@router.delete("/library/{factor_id}")
async def delete_factor(factor_id: str):
    db = await get_db()
    await db.execute("DELETE FROM factors WHERE id = ?", (factor_id,))
    await db.commit()
    await db.close()
    return {"deleted": factor_id}


# ── 预置因子路由 ─────────────────────────────────────────────────────


@router.get("/preset")
async def list_preset_factors(
    page: int = 1,
    page_size: int = 30,
    category_code: str = None,
    sort_field: str = None,
    sort_order: str = "desc",
    search: str = None,
):
    """预置因子分页列表"""
    result = await factor_research.list_preset_factors(
        page=page,
        page_size=page_size,
        category_code=category_code,
        sort_field=sort_field,
        sort_order=sort_order,
        search=search,
    )
    return result


@router.get("/preset/categories")
async def list_preset_categories():
    """预置因子分类列表"""
    return await factor_research.get_preset_factor_categories()


@router.get("/preset/pool")
async def get_factor_pool():
    """获取因子池列表"""
    return await factor_research.get_pool()


@router.delete("/preset/pool/{factor_id}")
async def remove_from_pool(factor_id: int):
    """从因子池移除"""
    await factor_research.remove_from_pool(factor_id)
    return {"success": True}


@router.get("/preset/{factor_id}")
async def get_preset_factor(factor_id: int):
    """单个预置因子详情（含公式文本/LaTeX/代码）"""
    factor = await factor_research.get_preset_factor_detail(factor_id)
    if not factor:
        raise HTTPException(status_code=404, detail="因子不存在")
    return factor


@router.get("/preset/{factor_id}/history")
async def get_preset_factor_history(factor_id: int):
    """因子 IC 指标历史快照（每次重算覆盖前自动留存）"""
    return await factor_research.get_factor_ic_history(factor_id)


@router.post("/preset/{factor_id}/recalculate")
async def recalculate_preset_factor(factor_id: int):
    """手动重算因子 IC（覆盖更新，旧值存入历史快照）"""
    factor = await factor_research.recalculate_preset_factor(factor_id)
    if not factor:
        raise HTTPException(status_code=404, detail="因子不存在")
    return factor


@router.post("/preset/{factor_id}/add-to-pool")
async def add_to_pool(factor_id: int):
    """加入因子池"""
    await factor_research.add_to_pool(factor_id)
    return {"success": True}
