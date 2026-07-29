"""信息推送节点 — 将工作流结果推送到外部渠道（钉钉等）"""

import json
import urllib.request
from typing import Optional, Type

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui


class PushResultOutput(BaseModel):
    """推送结果输出"""

    text: str = Field(default="", title="结果")
    metadata: dict = Field(default_factory=dict, title="元数据")


# ============================================================
# 钉钉推送节点
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


@work_node(
    name="钉钉推送",
    group="11-信息推送",
    box_color="#795548",
    description="通过钉钉机器人 Webhook 推送消息，可附带上游数据摘要",
    example="回测 / 股票排名 → 钉钉推送",
    notes=[
        "需先在钉钉群创建自定义机器人并填入 Webhook URL",
        "data 为可选连线输入，提供时会拼接数据摘要到消息中",
    ],
)
class DingTalkNode(BaseWorkNode):
    """钉钉机器人推送节点"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return DingTalkInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return PushResultOutput

    def run(self, input: DingTalkInput) -> Optional[BaseModel]:
        if not input.webhook_url.strip():
            return PushResultOutput(text="", metadata={"error": "Webhook URL 为空"})

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
            return PushResultOutput(
                text="[钉钉] 消息发送成功", metadata={"status": "sent"}
            )
        except Exception as e:
            return PushResultOutput(
                text=f"[钉钉] 发送失败: {e}", metadata={"error": str(e)}
            )
