import json
import logging
import os
import threading
from typing import Any, Mapping, Optional

import lark_oapi as lark
import lark_oapi.api.im.v1 as larkim

from ..engine.loop import AgentEngine
from ..engine.reportor import Reporter


def _read_field(value: Any, *names: str) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return None


class FeishuBot:
    """封装飞书机器人的配置与核心业务流。"""

    def __init__(self, engine: AgentEngine, client: Optional[Any] = None):
        app_id = os.getenv("FEISHU_APP_ID", "")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")
        if not app_id or not app_secret:
            raise RuntimeError("请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")

        self.app_id = app_id
        self.app_secret = app_secret
        self.engine = engine
        self.client = client or (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .build()
        )

    def get_event_dispatcher(self):
        """返回一个可直接挂到上层回调入口的处理函数。"""
        return self.handle_message_event

    @staticmethod
    def _extract_text_content(raw_content: Any) -> str:
        if raw_content is None:
            return ""
        if isinstance(raw_content, bytes):
            raw_content = raw_content.decode("utf-8")
        if isinstance(raw_content, Mapping):
            return str(raw_content.get("text", ""))
        if not isinstance(raw_content, str):
            return str(raw_content)

        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            return raw_content

        if isinstance(parsed, Mapping):
            return str(parsed.get("text", raw_content))
        return raw_content

    def handle_message_event(self, event: Any) -> None:
        """处理一条飞书消息事件，并异步启动 Agent。"""
        event_body = _read_field(event, "event") or event
        message = _read_field(event_body, "message")
        if message is None:
            logging.warning("[Feishu] 收到无法识别的事件: %r", event)
            return

        chat_id = _read_field(message, "chat_id", "chatId")
        raw_content = _read_field(message, "content")
        content = self._extract_text_content(raw_content)

        if not chat_id:
            logging.warning("[Feishu] 消息事件缺少 chat_id: %r", event)
            return

        logging.info("[Feishu] 收到会话 %s 消息: %s", chat_id, content)
        threading.Thread(
            target=self.handle_agent_run,
            args=(chat_id, content),
            daemon=True,
        ).start()

    def handle_agent_run(self, chat_id: str, prompt: str) -> None:
        """连接飞书与底层引擎。"""
        reporter = FeishuReporter(client=self.client, chat_id=chat_id)
        err = self.engine.run(prompt, reporter)
        if err is not None:
            reporter.send_msg(f"❌ Agent 运行崩溃: {err}")


class FeishuReporter(Reporter):
    """将引擎输出格式化后发给飞书。"""

    def __init__(self, client: Any, chat_id: str):
        self.client = client
        self.chat_id = chat_id

    def send_msg(self, text: str) -> None:
        content = json.dumps({"text": text}, ensure_ascii=False)
        request = (
            larkim.CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                larkim.CreateMessageRequestBody.builder()
                .receive_id(self.chat_id)
                .msg_type("text")
                .content(content)
                .build()
            )
            .build()
        )
        self.client.im.v1.message.create(request)

    def on_thinking(self) -> None:
        self.send_msg("🤔 模型正在慢思考 (Thinking)...")

    def on_tool_call(self, tool_name: str, args: str) -> None:
        self.send_msg(f"🛠️ 正在执行工具：{tool_name}\n参数：{args}")

    def on_tool_result(self, tool_name: str, result: str, is_error: bool) -> None:
        if is_error:
            self.send_msg(f"⚠️ 执行报错 ({tool_name})：\n{result}")
            return
        self.send_msg(f"✅ 执行成功 ({tool_name})")

    def on_message(self, content: str) -> None:
        self.send_msg(content)


def new_feishu_bot(engine: AgentEngine, client: Optional[Any] = None) -> FeishuBot:
    return FeishuBot(engine=engine, client=client)
