"""智能体节点 — RAG/技能/智能体/MCP/提示词/钉钉等"""

from typing import Optional, Type

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui

# ────────────────────────── 通用 I/O ──────────────────────────


class AgentTextIO(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    text: str = Field(default="", title="文本输出")
    metadata: dict = Field(default_factory=dict, title="元数据")


class AgentConfigInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    model_name: str = Field(default="gpt-4", title="模型名称")
    temperature: float = Field(default=0.7, title="温度")
    max_tokens: int = Field(default=2048, title="最大Token数")
    api_key: str = Field(default="", title="API Key")
    api_base: str = Field(default="", title="API Base URL")


# ============================================================
# 35. 研报 RAG 节点
# ============================================================


@ui(
    query={"input_type": "text_field", "placeholder": "检索问题"},
    doc_source={"input_type": "text_field", "placeholder": "文档来源路径/URL"},
    top_k={"input_type": "number_field"},
    data={"input_type": "None"},
)
class ReportRAGInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    query: str = Field(default="", title="检索问题")
    doc_source: str = Field(default="", title="文档来源")
    top_k: int = Field(default=5, title="返回条数")
    model_name: str = Field(default="gpt-4", title="模型")


@work_node(name="研报 RAG", group="07-智能体", box_color="#795548")
class ReportRAGNode(BaseWorkNode):
    """研报 RAG 检索增强生成节点"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return ReportRAGInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return AgentTextIO

    def run(self, input: ReportRAGInput) -> Optional[BaseModel]:
        if not input.query.strip():
            return AgentTextIO(text="", metadata={"error": "检索问题为空"})

        # 预留 RAG 接口 — 实际实现需要连接向量数据库
        metadata = {
            "type": "report_rag",
            "query": input.query,
            "doc_source": input.doc_source,
            "top_k": input.top_k,
            "model": input.model_name,
            "status": "interface_reserved",
            "message": "RAG 接口已预留，需配置向量数据库和 Embedding 模型",
        }
        return AgentTextIO(text=f"[研报RAG] 查询: {input.query}", metadata=metadata)


# ============================================================
# 36. RAG 节点
# ============================================================


@ui(
    query={"input_type": "text_field", "placeholder": "检索问题"},
    knowledge_base={"input_type": "text_field", "placeholder": "知识库名称/路径"},
    top_k={"input_type": "number_field"},
    data={"input_type": "None"},
)
class RAGInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    query: str = Field(default="", title="检索问题")
    knowledge_base: str = Field(default="", title="知识库")
    top_k: int = Field(default=5, title="返回条数")
    model_name: str = Field(default="gpt-4", title="模型")


@work_node(name="RAG", group="07-智能体", box_color="#795548")
class RAGNode(BaseWorkNode):
    """通用 RAG 检索增强生成节点"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return RAGInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return AgentTextIO

    def run(self, input: RAGInput) -> Optional[BaseModel]:
        if not input.query.strip():
            return AgentTextIO(text="", metadata={"error": "检索问题为空"})

        metadata = {
            "type": "rag",
            "query": input.query,
            "knowledge_base": input.knowledge_base,
            "top_k": input.top_k,
            "model": input.model_name,
            "status": "interface_reserved",
            "message": "RAG 接口已预留，需配置向量数据库",
        }
        return AgentTextIO(text=f"[RAG] 查询: {input.query}", metadata=metadata)


# ============================================================
# 37. 技能集合节点
# ============================================================


@ui(
    skill_names={"input_type": "text_field", "placeholder": "技能名称(逗号分隔)"},
)
class SkillSetInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    skill_names: str = Field(default="", title="技能名称(逗号分隔)")
    description: str = Field(default="", title="技能集合描述")


class SkillSetOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    skills: list = Field(default_factory=list, title="技能列表")


@work_node(name="技能集合", group="07-智能体", box_color="#795548")
class SkillSetNode(BaseWorkNode):
    """技能集合节点 — 聚合多个技能"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return SkillSetInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return SkillSetOutput

    def run(self, input: SkillSetInput) -> Optional[BaseModel]:
        skills = [s.strip() for s in input.skill_names.split(",") if s.strip()]
        return SkillSetOutput(data=input.data, skills=skills)


# ============================================================
# 38. 智能体节点
# ============================================================


@ui(
    system_prompt={"input_type": "code_editor", "language": "markdown"},
    model_name={
        "input_type": "combobox",
        "options": ["gpt-4", "gpt-4o", "gpt-3.5-turbo", "claude-3", "qwen-max"],
    },
    temperature={"input_type": "number_field"},
    data={"input_type": "None"},
)
class AgentInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    system_prompt: str = Field(default="你是一个量化投资助手。", title="系统提示词")
    user_message: str = Field(default="", title="用户消息")
    model_name: str = Field(default="gpt-4", title="模型")
    temperature: float = Field(default=0.7, title="温度")
    max_tokens: int = Field(default=2048, title="最大Token")
    api_key: str = Field(default="", title="API Key")
    api_base: str = Field(default="", title="API Base URL")


@work_node(name="智能体", group="07-智能体", box_color="#795548")
class AgentNode(BaseWorkNode):
    """通用智能体节点"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return AgentInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return AgentTextIO

    def run(self, input: AgentInput) -> Optional[BaseModel]:
        if not input.api_key.strip():
            return AgentTextIO(
                text="[智能体] 请配置 API Key",
                metadata={"status": "no_api_key", "model": input.model_name},
            )

        try:
            import openai

            client = openai.OpenAI(
                api_key=input.api_key, base_url=input.api_base or None
            )
            response = client.chat.completions.create(
                model=input.model_name,
                messages=[
                    {"role": "system", "content": input.system_prompt},
                    {"role": "user", "content": input.user_message},
                ],
                temperature=input.temperature,
                max_tokens=input.max_tokens,
            )
            text = response.choices[0].message.content or ""
            return AgentTextIO(
                text=text,
                metadata={"model": input.model_name, "usage": str(response.usage)},
            )
        except ImportError:
            return AgentTextIO(
                text="[智能体] 请安装 openai: pip install openai",
                metadata={"error": "missing openai"},
            )
        except Exception as e:
            return AgentTextIO(
                text=f"[智能体] 调用失败: {e}", metadata={"error": str(e)}
            )


# ============================================================
# 39. 极速智能体节点
# ============================================================


@ui(
    system_prompt={"input_type": "code_editor", "language": "markdown"},
    model_name={
        "input_type": "combobox",
        "options": ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo", "qwen-turbo"],
    },
    data={"input_type": "None"},
)
class FastAgentInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    system_prompt: str = Field(
        default="你是一个量化投资助手，请快速简洁回答。", title="系统提示词"
    )
    user_message: str = Field(default="", title="用户消息")
    model_name: str = Field(default="gpt-4o-mini", title="模型")
    temperature: float = Field(default=0.3, title="温度")
    max_tokens: int = Field(default=1024, title="最大Token")
    api_key: str = Field(default="", title="API Key")
    api_base: str = Field(default="", title="API Base URL")


@work_node(name="极速智能体", group="07-智能体", box_color="#795548")
class FastAgentNode(BaseWorkNode):
    """极速智能体 — 使用轻量模型快速响应"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FastAgentInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return AgentTextIO

    def run(self, input: FastAgentInput) -> Optional[BaseModel]:
        if not input.api_key.strip():
            return AgentTextIO(
                text="[极速智能体] 请配置 API Key", metadata={"status": "no_api_key"}
            )

        try:
            import openai

            client = openai.OpenAI(
                api_key=input.api_key, base_url=input.api_base or None
            )
            response = client.chat.completions.create(
                model=input.model_name,
                messages=[
                    {"role": "system", "content": input.system_prompt},
                    {"role": "user", "content": input.user_message},
                ],
                temperature=input.temperature,
                max_tokens=input.max_tokens,
            )
            text = response.choices[0].message.content or ""
            return AgentTextIO(
                text=text, metadata={"model": input.model_name, "mode": "fast"}
            )
        except ImportError:
            return AgentTextIO(
                text="[极速智能体] 请安装 openai", metadata={"error": "missing openai"}
            )
        except Exception as e:
            return AgentTextIO(
                text=f"[极速智能体] 调用失败: {e}", metadata={"error": str(e)}
            )


# ============================================================
# 40. MCP 节点
# ============================================================


@ui(
    server_url={"input_type": "text_field", "placeholder": "MCP 服务地址"},
    tool_name={"input_type": "text_field", "placeholder": "调用的工具名称"},
    data={"input_type": "None"},
)
class MCPInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    server_url: str = Field(default="", title="MCP 服务地址")
    tool_name: str = Field(default="", title="工具名称")
    tool_params: str = Field(default="{}", title="工具参数(JSON)")


@work_node(name="MCP", group="07-智能体", box_color="#795548")
class MCPNode(BaseWorkNode):
    """MCP (Model Context Protocol) 节点"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return MCPInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return AgentTextIO

    def run(self, input: MCPInput) -> Optional[BaseModel]:
        if not input.server_url.strip():
            return AgentTextIO(text="", metadata={"error": "MCP 服务地址为空"})

        import json

        try:
            params = json.loads(input.tool_params) if input.tool_params.strip() else {}
        except json.JSONDecodeError:
            params = {}

        metadata = {
            "type": "mcp",
            "server_url": input.server_url,
            "tool_name": input.tool_name,
            "params": params,
            "status": "interface_reserved",
            "message": "MCP 接口已预留，需配置 MCP 服务端",
        }
        return AgentTextIO(text=f"[MCP] 调用: {input.tool_name}", metadata=metadata)


# ============================================================
# 41. 提示词输入节点
# ============================================================


@ui(
    prompt={"input_type": "code_editor", "language": "markdown"},
)
class PromptInput(BaseModel):
    prompt: str = Field(default="", title="提示词")
    variables: str = Field(default="", title="变量(格式: key=value,每行一个)")


class PromptOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    text: str = Field(default="", title="渲染后提示词")
    variables_dict: dict = Field(default_factory=dict, title="变量字典")


@work_node(name="提示词输入", group="07-智能体", box_color="#795548")
class PromptInputNode(BaseWorkNode):
    """提示词输入与变量渲染"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return PromptInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return PromptOutput

    def run(self, input: PromptInput) -> Optional[BaseModel]:
        # 解析变量
        variables = {}
        if input.variables.strip():
            for line in input.variables.strip().split("\n"):
                line = line.strip()
                if "=" in line:
                    key, val = line.split("=", 1)
                    variables[key.strip()] = val.strip()

        # 渲染提示词
        rendered = input.prompt
        for key, val in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", val)

        return PromptOutput(text=rendered, variables_dict=variables)


# ============================================================
# 42. 技能节点
# ============================================================


@ui(
    skill_name={"input_type": "text_field"},
    skill_code={"input_type": "code_editor", "language": "python"},
    data={"input_type": "None"},
)
class SkillInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    skill_name: str = Field(default="", title="技能名称")
    skill_code: str = Field(
        default="# 技能代码\nresult = input_text\n", title="技能代码"
    )
    input_text: str = Field(default="", title="输入文本")


@work_node(name="技能", group="07-智能体", box_color="#795548")
class SkillNode(BaseWorkNode):
    """单个技能节点"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return SkillInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return AgentTextIO

    def run(self, input: SkillInput) -> Optional[BaseModel]:
        exec_ctx = {"input_text": input.input_text, "data": input.data, "result": ""}
        try:
            exec(
                input.skill_code,
                {
                    "__builtins__": {
                        "print": print,
                        "len": len,
                        "str": str,
                        "int": int,
                        "float": float,
                        "list": list,
                        "dict": dict,
                    }
                },
                exec_ctx,
            )  # noqa: S102
            result = exec_ctx.get("result", "")
        except Exception as e:
            result = f"[技能执行错误] {e}"

        return AgentTextIO(text=str(result), metadata={"skill_name": input.skill_name})


# ============================================================
# 43. 钉钉助手节点
# ============================================================


@ui(
    webhook_url={"input_type": "text_field", "placeholder": "钉钉机器人 Webhook URL"},
    message_type={"input_type": "combobox", "options": ["text", "markdown", "link"]},
    data={"input_type": "None"},
)
class DingTalkInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    webhook_url: str = Field(default="", title="Webhook URL")
    message_type: str = Field(default="text", title="消息类型")
    message_content: str = Field(default="", title="消息内容")
    at_mobiles: str = Field(default="", title="@手机号(逗号分隔)")


@work_node(name="钉钉助手", group="07-智能体", box_color="#795548")
class DingTalkNode(BaseWorkNode):
    """钉钉机器人助手节点"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return DingTalkInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return AgentTextIO

    def run(self, input: DingTalkInput) -> Optional[BaseModel]:
        if not input.webhook_url.strip():
            return AgentTextIO(text="", metadata={"error": "Webhook URL 为空"})

        import json
        import urllib.request

        at_mobiles = [m.strip() for m in input.at_mobiles.split(",") if m.strip()]

        if input.message_type == "markdown":
            payload = {
                "msgtype": "markdown",
                "markdown": {"title": "LocalQuant", "text": input.message_content},
                "at": {"atMobiles": at_mobiles},
            }
        elif input.message_type == "link":
            payload = {
                "msgtype": "link",
                "link": {
                    "title": "LocalQuant",
                    "text": input.message_content,
                    "messageUrl": "",
                },
            }
        else:
            payload = {
                "msgtype": "text",
                "text": {"content": input.message_content},
                "at": {"atMobiles": at_mobiles},
            }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                input.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
            return AgentTextIO(text="[钉钉] 消息发送成功", metadata={"status": "sent"})
        except Exception as e:
            return AgentTextIO(text=f"[钉钉] 发送失败: {e}", metadata={"error": str(e)})


# ============================================================
# 44. 极速智能体应用节点
# ============================================================


@ui(
    app_name={"input_type": "text_field"},
    model_name={
        "input_type": "combobox",
        "options": ["gpt-4o-mini", "gpt-4o", "qwen-turbo"],
    },
    data={"input_type": "None"},
)
class FastAgentAppInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    app_name: str = Field(default="", title="应用名称")
    system_prompt: str = Field(default="", title="系统提示词")
    user_message: str = Field(default="", title="用户消息")
    model_name: str = Field(default="gpt-4o-mini", title="模型")
    api_key: str = Field(default="", title="API Key")
    api_base: str = Field(default="", title="API Base URL")


@work_node(name="极速智能体应用", group="07-智能体", box_color="#795548")
class FastAgentAppNode(BaseWorkNode):
    """极速智能体应用节点"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FastAgentAppInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return AgentTextIO

    def run(self, input: FastAgentAppInput) -> Optional[BaseModel]:
        if not input.api_key.strip():
            return AgentTextIO(
                text="[极速应用] 请配置 API Key", metadata={"status": "no_api_key"}
            )

        try:
            import openai

            client = openai.OpenAI(
                api_key=input.api_key, base_url=input.api_base or None
            )
            messages = []
            if input.system_prompt.strip():
                messages.append({"role": "system", "content": input.system_prompt})
            messages.append({"role": "user", "content": input.user_message})
            response = client.chat.completions.create(
                model=input.model_name,
                messages=messages,
                temperature=0.3,
                max_tokens=1024,
            )
            text = response.choices[0].message.content or ""
            return AgentTextIO(
                text=text, metadata={"app": input.app_name, "model": input.model_name}
            )
        except Exception as e:
            return AgentTextIO(text=f"[极速应用] 失败: {e}", metadata={"error": str(e)})


# ============================================================
# 45. 智能体聚合节点
# ============================================================


@ui(
    strategy={"input_type": "combobox", "options": ["vote", "chain", "parallel"]},
    data={"input_type": "None"},
)
class AgentAggregateInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    strategy: str = Field(default="vote", title="聚合策略")
    agent_outputs: str = Field(default="", title="智能体输出(换行分隔)")


@work_node(name="智能体聚合", group="07-智能体", box_color="#795548")
class AgentAggregateNode(BaseWorkNode):
    """智能体聚合节点 — 合并多个智能体输出"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return AgentAggregateInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return AgentTextIO

    def run(self, input: AgentAggregateInput) -> Optional[BaseModel]:
        outputs = [o.strip() for o in input.agent_outputs.split("\n") if o.strip()]

        if input.strategy == "vote":
            # 投票：取出现最多的
            from collections import Counter

            counter = Counter(outputs)
            result = counter.most_common(1)[0][0] if counter else ""
        elif input.strategy == "chain":
            result = " -> ".join(outputs)
        else:
            result = "\n---\n".join(outputs)

        return AgentTextIO(
            text=result,
            metadata={"strategy": input.strategy, "agent_count": len(outputs)},
        )


# ============================================================
# 46. 智能体集合节点
# ============================================================


@ui(
    agent_configs={"input_type": "code_editor", "language": "json"},
    data={"input_type": "None"},
)
class AgentCollectionInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    agent_configs: str = Field(default="[]", title="智能体配置(JSON数组)")
    task: str = Field(default="", title="任务描述")


class AgentCollectionOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    agents: list = Field(default_factory=list, title="智能体列表")
    task: str = Field(default="", title="任务")


@work_node(name="智能体集合", group="07-智能体", box_color="#795548")
class AgentCollectionNode(BaseWorkNode):
    """智能体集合节点 — 配置和管理多个智能体"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return AgentCollectionInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return AgentCollectionOutput

    def run(self, input: AgentCollectionInput) -> Optional[BaseModel]:
        import json

        try:
            agents = (
                json.loads(input.agent_configs) if input.agent_configs.strip() else []
            )
        except json.JSONDecodeError:
            agents = []

        return AgentCollectionOutput(data=input.data, agents=agents, task=input.task)


# ============================================================
# 47. 智能体消息节点
# ============================================================


@ui(
    message={"input_type": "code_editor", "language": "markdown"},
    role={"input_type": "combobox", "options": ["user", "system", "assistant"]},
    data={"input_type": "None"},
)
class AgentMessageInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    message: str = Field(default="", title="消息内容")
    role: str = Field(default="user", title="角色")
    template_vars: str = Field(default="", title="模板变量(key=value,每行一个)")


class AgentMessageOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    text: str = Field(default="", title="渲染后消息")
    role: str = Field(default="user", title="角色")


@work_node(name="智能体消息", group="07-智能体", box_color="#795548")
class AgentMessageNode(BaseWorkNode):
    """智能体消息构造节点"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return AgentMessageInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return AgentMessageOutput

    def run(self, input: AgentMessageInput) -> Optional[BaseModel]:
        rendered = input.message
        if input.template_vars.strip():
            for line in input.template_vars.strip().split("\n"):
                if "=" in line:
                    key, val = line.split("=", 1)
                    rendered = rendered.replace(f"{{{{{key.strip()}}}}}", val.strip())

        return AgentMessageOutput(data=input.data, text=rendered, role=input.role)


# ============================================================
# 48. 智能体交易节点
# ============================================================


@ui(
    strategy_prompt={"input_type": "code_editor", "language": "markdown"},
    model_name={"input_type": "combobox", "options": ["gpt-4", "gpt-4o", "claude-3"]},
    risk_level={
        "input_type": "combobox",
        "options": ["conservative", "moderate", "aggressive"],
    },
    data={"input_type": "None"},
)
class AgentTradeInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    strategy_prompt: str = Field(
        default="根据市场数据生成交易信号。", title="策略提示词"
    )
    market_data_summary: str = Field(default="", title="市场数据摘要")
    model_name: str = Field(default="gpt-4", title="模型")
    risk_level: str = Field(default="moderate", title="风险等级")
    max_position: float = Field(default=0.3, title="最大仓位比例")
    api_key: str = Field(default="", title="API Key")
    api_base: str = Field(default="", title="API Base URL")


class AgentTradeOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    text: str = Field(default="", title="交易建议")
    signals: dict = Field(default_factory=dict, title="交易信号")
    risk_assessment: dict = Field(default_factory=dict, title="风险评估")


@work_node(name="智能体交易", group="07-智能体", box_color="#795548")
class AgentTradeNode(BaseWorkNode):
    """智能体交易节点 — AI 驱动的交易决策"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return AgentTradeInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return AgentTradeOutput

    def run(self, input: AgentTradeInput) -> Optional[BaseModel]:
        if not input.api_key.strip():
            return AgentTradeOutput(
                text="[智能体交易] 请配置 API Key",
                signals={},
                risk_assessment={"risk_level": input.risk_level},
            )

        system_msg = f"""你是一个量化交易智能体。
风险等级: {input.risk_level}
最大仓位: {input.max_position}
{input.strategy_prompt}
请以JSON格式输出交易信号，包含: action(buy/sell/hold), symbol, quantity, reason。"""

        try:
            import openai

            client = openai.OpenAI(
                api_key=input.api_key, base_url=input.api_base or None
            )
            response = client.chat.completions.create(
                model=input.model_name,
                messages=[
                    {"role": "system", "content": system_msg},
                    {
                        "role": "user",
                        "content": f"市场数据摘要: {input.market_data_summary}",
                    },
                ],
                temperature=0.3,
                max_tokens=input.max_tokens if hasattr(input, "max_tokens") else 2048,
            )
            text = response.choices[0].message.content or ""

            import json

            try:
                signals = (
                    json.loads(text)
                    if text.strip().startswith("{") or text.strip().startswith("[")
                    else {}
                )
            except json.JSONDecodeError:
                signals = {}

            return AgentTradeOutput(
                text=text,
                signals=signals,
                risk_assessment={
                    "risk_level": input.risk_level,
                    "max_position": input.max_position,
                },
            )
        except Exception as e:
            return AgentTradeOutput(
                text=f"[智能体交易] 失败: {e}",
                signals={},
                risk_assessment={"error": str(e)},
            )
