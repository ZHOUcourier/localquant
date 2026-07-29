"""AI 路由 — 基于 OpenAI 兼容接口的 AI 辅助能力

两个场景，提示词均在后端预置：
- /node-code   修改节点代码（明确告知 AI 节点结构、能改什么、不能改什么）
- /workflow    自然语言生成/修改工作流 JSON（附带全部可用节点目录与格式约束）

所有主流厂商（OpenAI/DeepSeek/Moonshot/通义/智谱）均走 OpenAI 兼容
chat/completions 协议，自定义服务填 Base URL 即可。
"""

import json
import re
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings

router = APIRouter()

# 各厂商预置：默认 Base URL 与默认模型（前端也有一份用于展示）
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "moonshot": {"base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    "custom": {"base_url": "", "model": ""},
}


def _resolve_ai_config() -> tuple[str, str, str]:
    """解析当前生效的 (base_url, api_key, model)，未配置时抛 400"""
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=400, detail="未配置 AI API Key，请到「设置 → AI 配置」中填写"
        )
    preset = PROVIDER_PRESETS.get(settings.ai_provider, PROVIDER_PRESETS["custom"])
    base_url = (settings.openai_base_url or preset["base_url"]).rstrip("/")
    model = settings.ai_model or preset["model"]
    if not base_url:
        raise HTTPException(
            status_code=400, detail="未配置 AI Base URL，请到「设置 → AI 配置」中填写"
        )
    if not model:
        raise HTTPException(
            status_code=400, detail="未配置 AI 模型名称，请到「设置 → AI 配置」中填写"
        )
    return base_url, settings.openai_api_key, model


async def _chat(system: str, user: str, temperature: float = 0.2) -> str:
    """调用 OpenAI 兼容 chat/completions，返回文本内容"""
    base_url, api_key, model = _resolve_ai_config()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"AI 服务请求失败: {e}")
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"AI 服务返回错误 (HTTP {resp.status_code}): {resp.text[:300]}",
        )
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        raise HTTPException(
            status_code=502, detail=f"AI 响应格式异常: {resp.text[:300]}"
        )


def _strip_code_fence(text: str) -> str:
    """去掉 AI 可能包裹的 markdown 代码块围栏"""
    text = text.strip()
    m = re.match(r"^```[a-zA-Z0-9]*\n([\s\S]*?)\n?```$", text)
    return m.group(1) if m else text


# ---------------------------------------------------------------------------
# 场景 1：修改节点代码
# ---------------------------------------------------------------------------

NODE_CODE_SYSTEM = """你是 LocalQuant 量化投研平台的工作流节点开发专家。用户会提供一个节点的完整 Python 源码和修改要求，你需要输出修改后的完整源码。

## 节点代码结构（务必遵守）
一个节点文件由三部分组成：
1. **输入模型**：Pydantic BaseModel，定义节点的输入参数。可用 @ui(...) 装饰器为字段指定前端控件：
   - date_picker（日期）/ text_field（文本）/ code_editor（代码）/ combobox（下拉，配 options）/ number_field（数字）
   - {"input_type": "None"} 表示该字段仅通过上游节点连线输入，不渲染控件
   - DataFrame 类型字段需要 model_config = ConfigDict(arbitrary_types_allowed=True)
2. **输出模型**：Pydantic BaseModel，定义输出字段（下游节点通过连线消费这些字段）
3. **节点类**：用 @work_node(name=显示名, group=分组, box_color=颜色, description=描述) 装饰、继承 BaseWorkNode，实现三个方法：
   - input_model() / output_model()：返回上述两个 Model 类
   - run(self, input)：节点计算逻辑，返回输出模型实例

## 修改规则
- 只修改与用户要求相关的代码，其余部分原样保留（包括注释与空行）
- 不要改动 @work_node 装饰的节点类的类名（系统依赖类名识别节点来源）
- 需要新参数时：加到输入模型并配好 @ui 控件类型；需要新输出时：加到输出模型并在 run() 中赋值
- 保持所有 import 完整，代码必须可直接运行
- 输出字典/曲线类结果时保持 JSON 可序列化（键转 str、值转 float）

## 输出格式
只输出修改后的完整 Python 源码。不要输出任何解释、说明或 markdown 代码块围栏。"""


class NodeCodeRequest(BaseModel):
    source: str
    instruction: str
    node_name: Optional[str] = None


@router.post("/node-code")
async def ai_modify_node_code(body: NodeCodeRequest):
    """AI 修改节点代码：返回修改后的完整源码（前端填入编辑器，由用户确认保存）"""
    if not body.instruction.strip():
        raise HTTPException(status_code=400, detail="请描述要如何修改该节点")
    user = (
        f"节点：{body.node_name or '未知'}\n\n"
        f"## 当前源码\n{body.source}\n\n"
        f"## 修改要求\n{body.instruction}"
    )
    content = await _chat(NODE_CODE_SYSTEM, user)
    return {"source": _strip_code_fence(content)}


# ---------------------------------------------------------------------------
# 场景 2：生成 / 修改工作流
# ---------------------------------------------------------------------------

WORKFLOW_SYSTEM_TEMPLATE = """你是 LocalQuant 量化投研平台的工作流编排专家。根据用户的自然语言需求，生成（或在现有基础上修改）一个可执行的工作流 JSON。

## 可用节点目录
每个节点包含：类名（name，连线与生成时使用）、显示名、输入字段、输出字段。
{node_catalog}

## 输出 JSON 格式（严格遵守）
{{
  "name": "工作流名称",
  "nodes": [
    {{"uuid": "n1", "name": "节点类名", "title": "节点显示标题", "positionX": 80, "positionY": 120, "static_input_data": {{"参数名": "参数值"}}}}
  ],
  "links": [
    {{"uuid": "l1", "previous_node_uuid": "n1", "output_field_name": "上游输出字段名", "next_node_uuid": "n2", "input_field_name": "下游输入字段名"}}
  ]
}}

## 编排规则
- nodes[].name 必须是节点目录中存在的类名；static_input_data 的键必须是该节点输入字段名
- 连线的 output_field_name / input_field_name 必须分别是上游输出字段和下游输入字段，且类型语义匹配（如 DataFrame 接 DataFrame）
- 标注为「仅连线输入」的字段必须通过 links 提供，不要放进 static_input_data
- 布局：从左到右按执行顺序排列，positionX 每列间隔约 300，positionY 分支间隔约 220
- 工作流必须是无环 DAG
- 只输出 JSON，不要输出任何解释文字或 markdown 代码块围栏。"""


def _build_node_catalog() -> str:
    """把注册表节点压缩成给 AI 的目录文本"""
    from backend.plugins.registry import ALL_WORK_NODES

    lines: list[str] = []
    for cls in ALL_WORK_NODES.values():
        try:
            schema = cls().get_schema()
        except Exception:
            continue
        inputs = []
        for key, prop in (
            (schema.get("input_schema") or {}).get("properties", {}).items()
        ):
            ui_type = (prop.get("ui") or {}).get("input_type", "text_field")
            mark = "仅连线输入" if ui_type == "None" else ui_type
            default = prop.get("default")
            default_str = f", 默认={default!r}" if default not in (None, "") else ""
            inputs.append(f"{key}({mark}{default_str})")
        outputs = list(
            ((schema.get("output_schema") or {}).get("properties", {})).keys()
        )
        lines.append(
            f"- {schema['name']}（{schema['display_name']}，{schema['group']}）"
            f" 输入: {', '.join(inputs) or '无'} | 输出: {', '.join(outputs) or '无'}"
        )
    return "\n".join(lines)


class WorkflowAIRequest(BaseModel):
    instruction: str
    current_workflow: Optional[dict[str, Any]] = None  # 现有画布（可选，用于修改场景）


@router.post("/workflow")
async def ai_generate_workflow(body: WorkflowAIRequest):
    """AI 生成/修改工作流：返回 {name, nodes, links}，由前端应用到画布"""
    if not body.instruction.strip():
        raise HTTPException(status_code=400, detail="请描述想要构建的工作流")

    system = WORKFLOW_SYSTEM_TEMPLATE.format(node_catalog=_build_node_catalog())
    user = body.instruction
    if body.current_workflow and body.current_workflow.get("nodes"):
        user = (
            f"## 当前画布上的工作流\n{json.dumps(body.current_workflow, ensure_ascii=False)}\n\n"
            f"## 修改要求\n{body.instruction}"
        )

    content = _strip_code_fence(await _chat(system, user))
    try:
        wf = json.loads(content)
    except Exception:
        raise HTTPException(
            status_code=502, detail=f"AI 返回的不是合法 JSON: {content[:300]}"
        )

    # 校验节点类名有效
    from backend.plugins.registry import ALL_WORK_NODES

    nodes = wf.get("nodes", [])
    links = wf.get("links", [])
    invalid = [n.get("name") for n in nodes if n.get("name") not in ALL_WORK_NODES]
    if invalid:
        raise HTTPException(status_code=502, detail=f"AI 使用了不存在的节点: {invalid}")

    return {"name": wf.get("name", "AI 生成的工作流"), "nodes": nodes, "links": links}


@router.get("/status")
async def ai_status():
    """AI 配置状态（供前端判断是否已可用）"""
    preset = PROVIDER_PRESETS.get(settings.ai_provider, PROVIDER_PRESETS["custom"])
    return {
        "configured": bool(
            settings.openai_api_key
            and (settings.openai_base_url or preset["base_url"])
            and (settings.ai_model or preset["model"])
        ),
        "provider": settings.ai_provider,
        "model": settings.ai_model or preset["model"],
    }


# ---------------------------------------------------------------------------
# 场景 3：因子 AI 分析建议
# ---------------------------------------------------------------------------

FACTOR_ADVICE_SYSTEM = """你是量化因子研究专家。用户会提供一个选股因子的名称、公式与回测指标，请给出专业、简洁的分析与建议。

输出要求（Markdown，中文，控制在 400 字以内）：
## 因子逻辑解读
用通俗语言解释公式在捕捉什么市场现象（动量/反转/量价背离等）
## 指标评价
逐项点评 IC 均值、ICIR、年化收益、回撤、换手率的强弱（给出行业经验参考区间）
## 使用建议
适合的使用场景（单因子/多因子合成/中性化后使用）、适合的调仓周期、风险提示

只基于给定数据分析，缺失的指标说明数据不足即可，不要编造数值。"""


class FactorAdviceRequest(BaseModel):
    factor_name: str
    factor_code: Optional[str] = None
    formula: Optional[str] = None
    description: Optional[str] = None
    metrics: dict[str, Any] = {}


@router.post("/factor-advice")
async def ai_factor_advice(body: FactorAdviceRequest):
    """AI 分析单个因子：解读公式逻辑 + 点评指标 + 使用建议"""
    metrics_text = "\n".join(
        f"- {k}: {v}" for k, v in body.metrics.items() if v is not None
    )
    user = (
        f"因子名称：{body.factor_name}（{body.factor_code or ''}）\n"
        f"因子公式：{body.formula or '未提供'}\n"
        f"因子描述：{body.description or '无'}\n"
        f"回测指标：\n{metrics_text or '无'}"
    )
    content = await _chat(FACTOR_ADVICE_SYSTEM, user, temperature=0.4)
    return {"advice": content}


# ---------------------------------------------------------------------------
# 场景 5：因子综合分析报告（对应工作流「因子分析」节点与因子研究页）
# ---------------------------------------------------------------------------

FACTOR_REPORT_SYSTEM = """你是量化因子研究专家。用户会提供一个因子的完整单因子分析报告指标（IC / Rank_IC 统计、分层绩效、多空组合、换手率、单调性等），请给出专业、精炼的综合分析。

输出要求（Markdown，中文，500 字以内）：
## 因子有效性
根据 IC 均值 / ICIR / t 统计量 / p 值 判断预测能力的显著性与稳定性（给出行业经验参考区间）
## 分层与多空
点评分层单调性、多空组合年化与夏普、超额收益与信息比率
## 交易成本与实用性
结合换手率、最大回撤，给出调仓周期与使用建议（单因子 / 多因子合成 / 中性化后使用）
## 风险提示
只基于给定数据分析，缺失的指标说明数据不足即可，不要编造数值。"""


class FactorReportRequest(BaseModel):
    factor_name: Optional[str] = None
    summary: dict[str, Any] = {}
    group_perf: list[dict[str, Any]] = []


@router.post("/factor-report")
async def ai_factor_report(body: FactorReportRequest):
    """AI 解读因子综合分析报告（供因子分析节点与因子研究页共用）"""
    if not body.summary:
        raise HTTPException(status_code=400, detail="暂无报告指标可分析，请先计算因子")
    summary_text = "\n".join(f"- {k}: {v}" for k, v in body.summary.items())
    perf_lines = []
    for row in body.group_perf[:8]:
        g = row.get("group", "")
        ar = row.get("annualizedReturn")
        sr = row.get("sharpeRatio")
        ir = row.get("informationRatio")
        tr = row.get("turnoverRate")
        perf_lines.append(f"- {g}: 年化={ar}, 夏普={sr}, 信息比率={ir}, 换手率={tr}")
    user = (
        f"因子名称：{body.factor_name or '当前因子'}\n\n"
        f"## 关键指标\n{summary_text}\n\n"
        f"## 分组绩效\n{chr(10).join(perf_lines) or '无'}"
    )
    content = await _chat(FACTOR_REPORT_SYSTEM, user, temperature=0.4)
    return {"analysis": content}


# ---------------------------------------------------------------------------
# 场景 4：数据探索 AI（自然语言 → SQL / 结果解读）
# ---------------------------------------------------------------------------

EXPLORE_SQL_SYSTEM = """你是 DuckDB SQL 专家。用户会用自然语言描述对本地行情数据的查询需求，你输出一条可直接执行的 DuckDB SELECT 语句。

## 数据结构
- 行情数据以 Parquet 存储，每只股票一个文件：data/cache/1d/000001_SZ.parquet（文件名即股票代码，'.' 换成 '_'）
- 典型列：open, high, low, close, volume, amount；日期在索引列（可用 read_parquet 后的隐式列名，建议 SELECT *）
- 多文件查询：read_parquet('data/cache/1d/*.parquet', filename=true)，filename 列可提取股票代码
{tables_info}

## 要求
- 只输出一条 SELECT 语句，不要任何解释或 markdown 围栏
- 结果行数用 LIMIT 控制在 500 以内"""

EXPLORE_INSIGHT_SYSTEM = """你是量化数据分析师。用户会提供一段查询结果数据（列名+前若干行），请用中文给出简洁的数据解读：关键统计特征、异常点、可能的投研含义。控制在 250 字以内，不要编造数据中不存在的信息。"""


class ExploreSQLRequest(BaseModel):
    question: str


class ExploreInsightRequest(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    context: Optional[str] = None


@router.post("/explore-sql")
async def ai_explore_sql(body: ExploreSQLRequest):
    """自然语言生成 DuckDB SQL（由前端填入 SQL 面板执行）"""
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="请描述查询需求")
    # 把本地可用数据表信息注入提示词
    from backend.routes.explorer import list_tables

    tables = (await list_tables()).get("tables", [])
    if tables:
        lines = [
            f"- 周期 {t['period']}：{t['stock_count']} 只股票，列 {t['columns']}，区间 {t['sample_range']}"
            for t in tables
        ]
        tables_info = "## 当前本地数据\n" + "\n".join(lines)
    else:
        tables_info = "## 当前本地数据\n（暂无缓存数据）"
    system = EXPLORE_SQL_SYSTEM.format(tables_info=tables_info)
    content = _strip_code_fence(await _chat(system, body.question))
    return {"sql": content}


@router.post("/explore-insight")
async def ai_explore_insight(body: ExploreInsightRequest):
    """AI 解读查询结果数据"""
    if not body.columns:
        raise HTTPException(status_code=400, detail="无结果数据可分析")
    sample = body.rows[:50]
    user = (
        (f"查询背景：{body.context}\n" if body.context else "")
        + f"列：{body.columns}\n数据（前 {len(sample)} 行）：\n"
        + "\n".join(str(r) for r in sample)
    )
    content = await _chat(EXPLORE_INSIGHT_SYSTEM, user, temperature=0.3)
    return {"insight": content}
