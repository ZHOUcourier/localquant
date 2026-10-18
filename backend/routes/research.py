"""研究假设、冻结协议、验证证据与人工复核接口。"""

from fastapi import APIRouter, HTTPException

from backend.models.research import ReviewRequest, RunRequest, StudyCreate, TrialCreate
from backend.services import research_registry as registry
from backend.services.research_service import run_trial

router = APIRouter()


async def _call(fn, *args):
    try:
        return await fn(*args)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研究记录不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/studies")
async def list_studies():
    return await registry.list_studies()


@router.post("/studies")
async def create_study(req: StudyCreate):
    return await _call(registry.create_study, req)


@router.get("/studies/{study_id}")
async def get_study(study_id: str):
    result = await _call(registry.get_study, study_id)
    if result is None:
        raise HTTPException(status_code=404, detail="研究记录不存在")
    return result


@router.post("/studies/{study_id}/trials")
async def register_trial(study_id: str, req: TrialCreate):
    return await _call(registry.register_trial, study_id, req)


@router.post("/trials/{trial_id}/run")
async def run_research_trial(trial_id: str, req: RunRequest):
    return await _call(run_trial, trial_id, req.phase)


@router.post("/studies/{study_id}/review")
async def review_study(study_id: str, req: ReviewRequest):
    return await _call(registry.review_study, study_id, req)


@router.get("/guidance")
async def guidance():
    return {
        "principles": [
            "金融数据只来自 Windows QMT 本地缓存；材料摘要不是可替代的行情数据源。",
            "协议、方向、成本、基准和试验预算预注册；失败与人工/LLM变体也保留记录。",
            "验证集用于筛选；最终留出只允许人工选定一个候选，结果看过后不能再改参数复用。",
            "原始因子、Barra-like残差与组合增量分别回答不同问题，中性化不等于纯Alpha。",
            "预警只建议复核，不自动下单；不显著不等于死亡，缺数据不等于零风险。",
        ],
        "roadmap": [
            {"period": "1–2 月", "objective": "QMT 数据与低复杂度基线", "acceptance": "Windows QMT 日线、复权、行业/股本点位及历史股票池覆盖可核验；冻结成本和基准", "do_not": "不接替代行情、不用当前成分冒充历史完整股票池"},
            {"period": "3–4 月", "objective": "成本后样本外证伪", "acceptance": "全部候选登记、主检验预算校正、三轨对照与完整标签；无证据则停止该研究族", "do_not": "不因验证集好看反复调参后称独立验证"},
            {"period": "5–6 月", "objective": "最终留出与影子跟踪", "acceptance": "人工封存一个候选，检查成本压力与实际信号时序；真实成交能力未接入时只做后续数据跟踪", "do_not": "不将未发生的模拟成交宣称实盘，不自动配置真实资金"},
            {"period": "7–9 月", "objective": "市场状态与失效复核", "acceptance": "足够新增成熟样本、固定复核网格、序贯误报预算；状态条件策略优于未条件化对照才保留", "do_not": "不凭单次IC转负退役，不用全样本拟合状态"},
            {"period": "10–12 月", "objective": "组合增量与容量复盘", "acceptance": "不同机制候选能在成本后贡献增量；结合真实资金预算、成交量与实际执行偏差评估容量", "do_not": "无盘口和成交证据不编容量数字，不先堆深度RL或大规模盲挖"},
        ],
        "audit_checklist": [
            "每季度及标签/成交/数据复权/选样逻辑变化后执行对抗审计。",
            "报告代码位置、具体虚高或虚低场景、已知答案及对应pytest用例，不把新功能混成修复。",
            "检查T收盘→T+1收盘成交→其后收益；诊断IC与可执行收益标签分开。",
            "检查缺失收益不拼成完整标签、参考数据不向历史回填、样本内外参数不串用。",
            "检查试验预算、最终留出锁定、失败记录、重复监测不增加观察证据。",
            "检查零数据/恒定序列/秩亏/费用加倍/状态缺失，未知项应为null而非漂亮的0。",
            "回归通过只证明实现与口径；盈利、容量与真实成交验收等待QMT和执行证据。",
        ],
    }
