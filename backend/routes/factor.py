"""因子路由 — 直接调用本地因子研究服务"""

import asyncio
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
from backend.services import market_data, tasks
from backend.services.factor_research import factor_research

router = APIRouter()


async def _spawn_provenance(
    kind: str,
    entity_name: str,
    params: dict,
    metrics: dict | None = None,
    entity_id: str = "",
    notes: str = "",
    source: str = "research_local",
):
    """后台异步落一条溯源记录，失败不阻断主请求"""
    try:
        from backend.services.provenance import record_provenance

        await record_provenance(
            kind=kind,
            entity_id=entity_id,
            entity_name=entity_name,
            params=params or {},
            metrics=metrics,
            notes=notes,
            source=source,
        )
    except Exception:
        logger.debug("因子研究溯源记录失败（非致命）", exc_info=True)


def _align_factor_return(
    factor_df: pd.DataFrame, return_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """把因子与收益面板对齐到共同的日期与股票上。

    因子/收益面板可能来自不同来源（compute 接口、工作流节点、手工构造），
    日期索引错位时 IC/分层会把「未来日期」当 NaN 匹配，产生 500/空结果。
    统一在入口对齐：共同日期、共同股票，按日期升序。
    """
    common_dates = factor_df.index.intersection(return_df.index).sort_values()
    common_codes = factor_df.columns.intersection(return_df.columns)
    if len(common_dates) == 0 or len(common_codes) == 0:
        raise ValueError("因子与收益面板无共同日期或共同股票，请检查输入面板")
    return (
        factor_df.loc[common_dates, common_codes].sort_index(),
        return_df.loc[common_dates, common_codes].sort_index(),
    )


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


def _resolve_panel(data: dict, token: str, field: str) -> pd.DataFrame:
    """解析面板：优先使用本地 artifact token，兼容原有嵌套 dict 传输。"""
    from backend.services.panel_artifact import load_token_panel

    if token:
        df = load_token_panel(data, token, field)
        if df is None:
            raise HTTPException(status_code=400, detail=f"面板 token 无效：{field}")
        return df
    df = _dict_to_df(data or {})
    df.index = pd.to_datetime(df.index)
    return df


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
            codes=req.stock_pool
            or market_data.list_cached_codes("1d", exclude_indices=True),
            start_date=req.start_date,
            end_date=req.end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    close = panels["close"]
    # 待注入的参考面板：市值 / 换手率（无股本快照则为 None，不注入避免误导取值）
    aug = dict(panels)
    try:
        from backend.services import reference_data

        mc = reference_data.build_market_cap_panel(close)
        if mc is not None:
            aug["market_cap"] = mc
        turn = reference_data.build_turnover_panel(panels.get("volume"), close)
        if turn is not None:
            aug["turnover"] = turn
        industry_map = reference_data.load_industry_map()
    except Exception:
        logger.debug("市值/换手率/行业面板不可用，跳过注入", exc_info=True)
        mc, turn, industry_map = None, None, None
    # 基本面公告日点位：仅股票代码区间内已有快照记录的字段注入，避免 fund_xxx 无从取值
    fundamental_panels = {}
    try:
        from backend.services.fundamental import build_fundamental_panels

        fundamental_panels = build_fundamental_panels(
            list(close.columns), close.index
        ) or {}
    except Exception:
        fundamental_panels = {}
    # 构建公式求值命名空间：基础字段 + vwap/returns + 全部量化算子
    # （RANK/DELAY/DELTA/CORR/TS_RANK/DECAYLINEAR 等，大小写均可），
    # 使因子库中的 Alpha101/Alpha191 公式可直接运行。
    from backend.services.factor_operators import build_operator_namespace

    eval_ctx = build_operator_namespace(
        aug,
        industry_map=industry_map,
        fundamental={f"fund_{f}": p for f, p in fundamental_panels.items()},
    )

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

    # 收益面板统一为前向填充口径（与因子研究页/工作流节点一致）：
    # 停牌/缺口期间收益为 0，复牌日跳空收益计入。build_return_panel 保留完整
    # 日期索引（首日为 0），再与因子面板对齐，避免日期错位产生 NaN 截面。
    returns = market_data.build_return_panel(close)
    factor, returns = _align_factor_return(factor, returns)

    from backend.services.panel_artifact import build_panel_response

    # 全市场面板不要整表 JSON 回传：小样本内联，大样本落本地 artifact +
    # 受限预览；下游分析接口接受同一 token。
    return build_panel_response(
        {"factor_data": factor, "return_data": returns},
        inline_names=["factor_data", "return_data"],
    )


@router.post("/ic-analysis")
async def ic_analysis(req: ICAnalysisRequest):
    try:
        factor_df = _resolve_panel(req.factor_data, req.factor_token, "factor_data")
        return_df = _resolve_panel(req.return_data, req.return_token, "return_data")
        factor_df, return_df = _align_factor_return(factor_df, return_df)
        result = factor_research.ic_analysis(factor_df, return_df, req.periods)
        tasks.spawn(
            _spawn_provenance(
                "factor_ic",
                f"IC分析·periods={req.periods}",
                {
                    "periods": req.periods,
                    "n_stocks": int(factor_df.shape[1]),
                    "n_dates": int(factor_df.shape[0]),
                },
                {"ic_mean": float(result.get("summary", {}).get("ic_mean", 0.0))},
            )
        )
        return result
    except Exception as e:
        logger.error(f"IC分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"IC分析失败: {e}")


@router.post("/quantile")
async def quantile_analysis(req: QuantileRequest):
    try:
        factor_df = _resolve_panel(req.factor_data, req.factor_token, "factor_data")
        return_df = _resolve_panel(req.return_data, req.return_token, "return_data")
        factor_df, return_df = _align_factor_return(factor_df, return_df)
        result = factor_research.quantile_analysis(factor_df, return_df, req.n_groups)
        tasks.spawn(
            _spawn_provenance(
                "factor_quantile",
                f"分层分析·groups={req.n_groups}",
                {
                    "n_groups": req.n_groups,
                    "n_stocks": int(factor_df.shape[1]),
                    "n_dates": int(factor_df.shape[0]),
                },
                None,
            )
        )
        return result
    except Exception as e:
        logger.error(f"分层分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"分层分析失败: {e}")


@router.post("/decay")
async def factor_decay(req: ICAnalysisRequest):
    """因子衰减：IC 随持有期增长的变化（与因子分析节点同源）"""
    try:
        factor_df = _resolve_panel(req.factor_data, req.factor_token, "factor_data")
        return_df = _resolve_panel(req.return_data, req.return_token, "return_data")
        factor_df, return_df = _align_factor_return(factor_df, return_df)
        max_period = max(req.periods) if req.periods else 20
        return factor_research.factor_decay(factor_df, return_df, max_period)
    except Exception as e:
        logger.error(f"因子衰减分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"因子衰减分析失败: {e}")


@router.post("/turnover")
async def factor_turnover(req: ICAnalysisRequest):
    """因子换手率（与因子分析节点同源）"""
    try:
        factor_df = _resolve_panel(req.factor_data, req.factor_token, "factor_data")
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
        factor_df = _resolve_panel(req.factor_data, req.factor_token, "factor_data")
        return_df = _resolve_panel(req.return_data, req.return_token, "return_data")
        factor_df, return_df = _align_factor_return(factor_df, return_df)
        res = factor_research.full_factor_analysis(
            factor_df, return_df, n_groups=req.n_groups
        )
        tasks.spawn(
            _spawn_provenance(
                "factor_full",
                f"完整因子分析·groups={req.n_groups}",
                {
                    "n_groups": req.n_groups,
                    "n_stocks": int(factor_df.shape[1]),
                    "n_dates": int(factor_df.shape[0]),
                },
                res.get("summary") or None,
            )
        )
        return res
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
        factor_df = _resolve_panel(req.factor_data, req.factor_token, "factor_data")
        return_df = _resolve_panel(req.return_data, req.return_token, "return_data")
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
            df = _resolve_panel(data, "", f"factor_data")
            factors[name] = df
        for name, token in req.factor_tokens.items():
            factors[name] = _resolve_panel({}, token, "factor_data")
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
            factors[name] = _resolve_panel(data, "", "factor_data")
        for name, token in req.factor_tokens.items():
            factors[name] = _resolve_panel({}, token, "factor_data")
        result = factor_research.multi_factor_combine(factors)
        # 合成结果可能也是全市场面板：同样走 artifact 而非大 JSON
        from backend.services.panel_artifact import build_panel_response

        return build_panel_response(
            {"factor_data": result.fillna(0)},
            inline_names=["factor_data"],
        )
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
    """加入因子池（仅允许本地 QMT 样本重算且达到最小样本门槛的因子）"""
    try:
        await factor_research.add_to_pool(factor_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True}


# ── 因子批量扫描（P1）────────────────────────────────────────


class FactorScanRequest(BaseModel):
    factor_ids: list[int] = []  # 指定因子；与 category_codes 二选一
    category_codes: list[str] = []  # 按类别批量
    limit: int = 100  # 扫描上限
    start_date: str = ""
    end_date: str = ""
    periods: list[int] = [1, 5, 10, 20]
    max_workers: int = 4
    stock_pool: list[str] = []  # 留空=全部本地股票缓存；内存不足时可分块扫描


@router.post("/scan")
async def scan_factors(req: FactorScanRequest):
    """批量扫描因子 IC（SSE 逐因子进度）— 面板只加载一次，结果覆盖更新 + 历史快照

    事件：scan_start / factor_done / scan_done（详见服务层 docstring）。
    """
    if not req.factor_ids and not req.category_codes:
        raise HTTPException(status_code=400, detail="请选择要扫描的因子（factor_ids 或 category_codes）")
    if req.limit < 1 or req.limit > 500:
        raise HTTPException(status_code=400, detail="limit 需在 1~500 之间")

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        factor_research.scan_factors_stream(
            factor_ids=req.factor_ids,
            category_codes=req.category_codes,
            limit=req.limit,
            start_date=req.start_date,
            end_date=req.end_date,
            periods=req.periods,
            max_workers=req.max_workers,
            stock_pool=req.stock_pool,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 因子样本外验证（walk-forward，P5）───────────────────────


class WalkForwardRequest(BaseModel):
    factor_data: dict | None = None  # {date: {code: value}}；与 formula 二选一
    return_data: dict | None = None
    formula: str = ""  # 提供时走本地行情求值（无需预计算面板）
    start_date: str = ""
    end_date: str = ""
    train_days: int = 252
    test_days: int = 63
    n_splits: int = 3
    period: int = 1
    n_groups: int = 5


@router.post("/validation")
async def walk_forward(req: WalkForwardRequest):
    """因子样本外验证：滚动锚定 train/test 分割，输出每折 in-sample 与 OOS 指标"""
    try:
        if req.formula:
            res = factor_research.eval_formula_on_local(
                req.formula, req.start_date, req.end_date
            )
            if not res.get("ok"):
                raise HTTPException(status_code=400, detail=res.get("message", "公式求值失败"))
            factor_df, return_data, mask = (
                res["factor_df"],
                res["return_data"],
                res.get("mask"),
            )
        else:
            if not req.factor_data or not req.return_data:
                raise HTTPException(
                    status_code=400, detail="需提供 formula（本地求值）或 factor_data/return_data 面板"
                )
            factor_df = _dict_to_df(req.factor_data)
            return_data = _dict_to_df(req.return_data)
            mask = None
        result = factor_research.walk_forward_validation(
            factor_df,
            return_data,
            train_days=req.train_days,
            test_days=req.test_days,
            n_splits=req.n_splits,
            period=req.period,
            n_groups=req.n_groups,
            mask=mask,
        )
        # 溯源
        await _spawn_provenance(
            kind="factor",
            entity_id="validation",
            entity_name="walk-forward",
            params=req.model_dump(),
            metrics=result.get("aggregate", {}),
            notes=result.get("message", ""),
            source="validation",
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"样本外验证失败: {e}")
        raise HTTPException(status_code=400, detail=f"样本外验证失败: {e}")


# ── 因子生命周期 / 拥挤度（P2）──────────────────────────────


class ExportPanelRequest(BaseModel):
    """因子面板导出（研究交付：离线复核/交付同事）"""

    formula: str = ""
    factor_id: int = 0  # 与 formula 二选一（优先 formula）
    start_date: str = ""
    end_date: str = ""
    stock_pool: list[str] = []


@router.post("/export-panel")
async def export_factor_panel(req: ExportPanelRequest):
    """导出因子值面板 CSV（index=日期, columns=股票）与前瞻收益面板

    在本地缓存行情上重算因子并返回两份 CSV（factor_values.csv / return_data.csv），
    供离线复核、交付验证与外部工具分析。返回 JSON 的 data_urls 为可直接
    curl/浏览器下载的链接（GET /api/factor/export-file/{token}）。
    """
    import secrets

    from backend.services.factor_research import extract_formula

    formula = (req.formula or "").strip()
    if not formula and req.factor_id:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT description FROM preset_factors WHERE id = ?", (req.factor_id,)
            )
            row = await cursor.fetchone()
        finally:
            await db.close()
        if not row:
            raise HTTPException(status_code=404, detail="因子不存在")
        formula = extract_formula(row["description"])
    if not formula:
        raise HTTPException(status_code=400, detail="无可解析公式（请提供 formula 或有效的 factor_id）")

    codes = req.stock_pool or market_data.list_cached_codes("1d", exclude_indices=True)
    if not codes:
        raise HTTPException(status_code=404, detail=market_data.no_cache_error_detail("因子导出"))
    res = await asyncio.to_thread(
        factor_research.eval_formula_on_local, formula, req.start_date, req.end_date
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("message", "公式求值失败"))
    factor_df = res["factor_df"]
    return_data = res["return_data"]

    token = secrets.token_hex(8)
    from backend.services.market_data import panel_to_dict

    _EXPORT_BUCKET[token] = {
        "factor_values": panel_to_dict(factor_df),
        "return_data": panel_to_dict(return_data),
        "data_date": res.get("data_date"),
        "n_stocks": int(factor_df.shape[1]),
        "n_dates": int(factor_df.shape[0]),
    }
    return {
        "ok": True,
        "factor_id": req.factor_id,
        "data_date": res.get("data_date"),
        "n_stocks": int(factor_df.shape[1]),
        "n_dates": int(factor_df.shape[0]),
        "data_urls": {
            "factor_values": f"/api/factor/export-file/{token}?part=factor_values",
            "return_data": f"/api/factor/export-file/{token}?part=return_data",
        },
    }


_EXPORT_BUCKET: dict[str, dict] = {}


@router.get("/export-file/{token}")
async def export_file(token: str, part: str = "factor_values"):
    """下载导出的 CSV 数据（token 由 /export-panel 生成，内存暂存）"""
    from fastapi.responses import StreamingResponse

    payload = _EXPORT_BUCKET.get(token)
    if not payload or part not in ("factor_values", "return_data"):
        raise HTTPException(status_code=404, detail="导出数据不存在或已过期")
    import io

    df = pd.DataFrame(payload[part])
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    def _generate():
        buf = io.StringIO()
        df.to_csv(buf)
        yield buf.getvalue()

    fname = f"{part}.csv"
    return StreamingResponse(
        _generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/health")
async def factor_health(category_code: str = "", min_snapshots: int = 2):
    """因子体检：基于 IC 历史快照的生命周期阶段与 IC 趋势"""
    return await factor_research.factor_health(
        category_code=category_code or None, min_snapshots=min_snapshots
    )


@router.post("/health/crowding")
async def factor_crowding():
    """因子池拥挤度：池内因子两两截面相关（均值 |ρ|，TTL 6h 缓存）"""
    return await factor_research.pool_crowding()


# ── 日内高频（分钟级）因子研究 ─────────────────────────────────────────


class IntradayComputeRequest(BaseModel):
    formula: str = ""
    stock_pool: list[str] = []
    start_date: str = ""
    end_date: str = ""
    period: str = "5m"  # 1m/5m/15m/30m/60m


@router.post("/intraday/compute")
async def intraday_compute(req: IntradayComputeRequest):
    """分钟因子计算：分钟面板 →（清洗）→ 公式求值 → 自动折叠为日频因子面板

    公式环境：m_close/m_volume 等分钟字段 + ID_* 聚合算子（ID_LAST/ID_MEAN/
    ID_SLICE...）+ M_* 分钟序列算子 + 现成高频因子（TAIL_RET/RV/JUMP_DAY/
    AMIHUD5/VWAP_DEV/VOLUME_CLOCK/AUC_VOL_RATIO/LIMIT_UP_TIME/OVERNIGHT_RET/
    INTRADAY_RET）。结果为分钟级时自动 ID_LAST 折叠到日。
    """
    from backend.services.intraday_cleaner import load_intraday_panels
    from backend.services.intraday_operators import (
        ID_LAST,
        build_intraday_namespace,
    )

    formula = (req.formula or "").strip()
    if not formula:
        raise HTTPException(status_code=400, detail="分钟因子公式为空")

    try:
        loaded = load_intraday_panels(
            codes=req.stock_pool,
            period=req.period,
            start_date=req.start_date,
            end_date=req.end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    panels, meta = loaded["panels"], loaded["meta"]
    ns = build_intraday_namespace(panels, meta)
    lines = [
        ln
        for ln in formula.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    try:
        if len(lines) > 1:
            exec("\n".join(lines[:-1]), {"__builtins__": {}}, ns)  # noqa: S102
            factor = eval(lines[-1], {"__builtins__": {}}, ns)  # noqa: S307
        else:
            factor = eval(formula, {"__builtins__": {}}, ns)  # noqa: S307
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"分钟因子公式计算失败: {e}")

    if isinstance(factor, pd.Series):
        factor = factor.to_frame(name="factor")
    if not isinstance(factor, pd.DataFrame) or factor.empty:
        raise HTTPException(status_code=400, detail="分钟公式未产出有效面板")

    # 结果仍为分钟级（datetime index 含时间）→ 自动折叠为日频
    collapsed = False
    idx = pd.to_datetime(factor.index)
    if (idx.normalize() != idx).any():
        factor = ID_LAST(factor, 0)
        collapsed = True
        idx = pd.to_datetime(factor.index)

    factor = factor.sort_index()
    close = panels["close"]
    daily_close = close.groupby(close.index.normalize()).last().sort_index()
    daily_close = daily_close.reindex(factor.index, method="ffill").ffill()
    return_data = daily_close.pct_change()

    # 面板健康提示：一字/半日占比
    n_stocks = len(factor.columns)
    one_line_pct = half_pct = None
    if meta:
        one_lines = 0
        halfs = 0
        total = 0
        for code, m in meta.items():
            if code not in factor.columns:
                continue
            total += len(m)
            one_lines += int(m["one_line"].fillna(False).sum()) if "one_line" in m.columns else 0
            halfs += int(m["is_half"].fillna(False).sum()) if "is_half" in m.columns else 0
        if total:
            one_line_pct = round(one_lines / total, 4)
            half_pct = round(halfs / total, 4)

    return {
        "ok": True,
        "period": loaded["period"],
        "cleaned": loaded["cleaned"],
        "n_stocks": n_stocks,
        "start": str(factor.index[0].date()),
        "end": str(factor.index[-1].date()),
        "n_days": len(factor.index),
        "collapsed_to_daily": collapsed,
        "one_line_pct": one_line_pct,
        "half_day_pct": half_pct,
        "missing": loaded["missing"],
        "factor_data": market_data.panel_to_dict(factor),
        "return_data": market_data.panel_to_dict(return_data),
        "note": (
            "分钟面板已清洗（竞价 bar 剔除/半日标记/一字板标记）；因子为日频口径，"
            "下游 IC/分层/回测与日频因子完全同构"
        ),
    }


_DEFAULT_IC_TIMES = ["09:45", "10:30", "11:15", "14:00", "14:45", "14:55"]


class IntradayIcByTimeRequest(BaseModel):
    formula: str = ""
    stock_pool: list[str] = []
    start_date: str = ""
    end_date: str = ""
    period: str = "5m"
    times: list[str] = []  # 采样时刻 HH:MM；空=默认 6 时刻


@router.post("/intraday/ic-by-time")
async def intraday_ic_by_time(req: IntradayIcByTimeRequest):
    """时刻 IC 曲线：同一公式在不同日内时刻采截面，对同一次日收益算 RankIC

    回答「该因子的信息在一天里哪个时点最强」——直接指导执行时点选择
    （如尾盘动量在 14:45 的 IC 显著高于 10:30，则回测应选尾盘执行）。
    每时刻 = 仅用该时刻前（含）的分钟 bar 求因子 → 折叠到日 → RankIC。
    """
    from backend.services.intraday_cleaner import load_intraday_panels
    from backend.services.intraday_operators import (
        ID_LAST,
        build_intraday_namespace,
    )

    formula = (req.formula or "").strip()
    if not formula:
        raise HTTPException(status_code=400, detail="分钟因子公式为空")
    times = req.times or _DEFAULT_IC_TIMES
    times = sorted(set(times))

    try:
        loaded = load_intraday_panels(
            codes=req.stock_pool,
            period=req.period,
            start_date=req.start_date,
            end_date=req.end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    panels, meta = loaded["panels"], loaded["meta"]

    full_close = panels["close"]
    daily_close = full_close.groupby(full_close.index.normalize()).last().sort_index()
    return_data = daily_close.pct_change()

    out: list[dict] = []
    for t in times:
        t_panels = {
            f: p[p.index.strftime("%H:%M") <= t] for f, p in panels.items()
        }
        if t_panels.get("close") is None or t_panels["close"].empty:
            out.append({"time": t, "ic": None, "rank_ic": None, "n_days": 0, "note": "该时刻前无分钟 bar"})
            continue
        ns = build_intraday_namespace(t_panels, meta)
        try:
            factor = eval(formula, {"__builtins__": {}}, ns)  # noqa: S307
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"时刻 {t} 公式计算失败: {e}"
            )
        if isinstance(factor, pd.Series):
            factor = factor.to_frame(name="factor")
        if not isinstance(factor, pd.DataFrame) or factor.empty:
            continue
        idx = pd.to_datetime(factor.index)
        if (idx.normalize() != idx).any():
            factor = ID_LAST(factor, 0)
        factor = factor.sort_index()

        ics: list[float] = []
        dates = factor.index
        for i in range(len(dates) - 1):
            f = factor.loc[dates[i]].dropna()
            nxt = dates[i + 1]
            if nxt not in return_data.index:
                continue
            r = return_data.loc[nxt].dropna()
            common = f.index.intersection(r.index)
            if len(common) > 10:
                ics.append(f[common].rank().corr(r[common].rank()))
        v = np.array([x for x in ics if x is not None and not np.isnan(x)])
        if len(v) == 0:
            out.append({"time": t, "ic": None, "rank_ic": None, "n_days": 0, "note": "截面样本不足"})
            continue
        out.append(
            {
                "time": t,
                "ic": round(float(v.mean()), 5),
                "rank_ic": round(float(v.mean()), 5),
                "icir": round(float(v.mean() / v.std(ddof=1)), 3)
                if len(v) > 1 and v.std(ddof=1) > 0
                else 0.0,
                "positive_ratio": round(float((v > 0).mean()), 4),
                "n_days": int(len(v)),
            }
        )

    return {
        "ok": True,
        "period": loaded["period"],
        "formula": formula,
        "times": out,
        "n_stocks": int(len(panels["close"].columns)),
        "data_start": str(daily_close.index[0].date()),
        "data_end": str(daily_close.index[-1].date()),
        "note": (
            "每个时刻的因子值只用该时刻前（含）的分钟 bar 计算（meta 类因子如 "
            "AUC_VOL_RATIO/LIMIT_UP_TIME 使用全日 meta，与时刻无关）；"
            "收益口径统一为次日收益（T 因子 vs T+1 收益），时刻间可比"
        ),
    }
