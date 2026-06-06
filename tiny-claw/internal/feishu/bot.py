import json
import logging
import os
import sys
import threading
from typing import Any, Mapping, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from internal.engine.reportor import Reporter

try:
    import lark_oapi as lark
    import lark_oapi.api.im.v1 as larkim
    import lark_oapi.ws as larkws
except ImportError:
    lark = None
    larkim = None
    larkws = None


def _read_field(value: Any, *names: str) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return None


class _WebSocketEventHandler:
    """适配飞书 WS SDK 所需的 do_without_validation 接口。"""

    def __init__(self, bot: "FeishuBot"):
        self.bot = bot

    def do_without_validation(self, payload: bytes) -> None:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        event = json.loads(payload)
        self.bot.handle_message_event(event)
        return None


class FeishuBot:
    """FeishuBot 封装了飞书机器人的配置与核心业务流。"""

    def __init__(self, engine: Any, client: Optional[Any] = None):
        app_id = os.getenv("FEISHU_APP_ID", "")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")
        if not app_id or not app_secret:
            raise RuntimeError("请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")

        self.app_id = app_id
        self.app_secret = app_secret
        self.engine = engine
        self.client = client or self._build_client()

    def _build_client(self) -> Any:
        if lark is None:
            raise ImportError("请先安装 lark_oapi 包，例如: pip install lark-oapi")
        return (
            lark.Client.builder()
            .app_id(self.app_id)
            .app_secret(self.app_secret)
            .build()
        )

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

    def start_websocket(self) -> None:
        if larkws is None:
            raise ImportError("请先安装 lark_oapi 包，例如: pip install lark-oapi")

        logging.info("正在启动 WebSocket 长连接模式...")
        event_handler = _WebSocketEventHandler(self)
        ws_client = larkws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            auto_reconnect=True,
        )
        logging.info("WebSocket 客户端已创建，正在连接飞书服务器...")
        return ws_client.start()

    def get_event_dispatcher(self):
        encrypt_key = os.getenv("FEISHU_ENCRYPT_KEY", "")
        verify_token = os.getenv("FEISHU_VERIFY_TOKEN", "")
        return self.create_event_dispatcher(verify_token, encrypt_key)

    def create_event_dispatcher(self, verify_token: str, encrypt_key: str):
        del verify_token, encrypt_key

        def dispatcher(event: Any) -> None:
            event_body = _read_field(event, "event") or event
            message = _read_field(event_body, "message")
            if message is None:
                logging.debug("[Feishu] 忽略非消息事件: %r", event)
                return
            self.handle_message_event(event)

        return dispatcher

    def handle_message_event(self, event: Any) -> None:
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
        reporter = FeishuReporter(client=self.client, chat_id=chat_id)
        err = self.engine.run(prompt, reporter)
        if err is not None:
            reporter.send_msg(f"❌ Agent 运行崩溃: {err}")

    StartWebSocket = start_websocket
    GetEventDispatcher = get_event_dispatcher
    createEventDispatcher = create_event_dispatcher
    handleMessageEvent = handle_message_event
    handleAgentRun = handle_agent_run


class FeishuReporter(Reporter):
    """将引擎输出格式化后发给飞书。"""

    def __init__(self, client: Any, chat_id: str):
        self.client = client
        self.chat_id = chat_id

    def _build_request(self, text: str) -> Any:
        content = json.dumps({"text": text}, ensure_ascii=False)
        if larkim is None:
            return {
                "receive_id_type": "chat_id",
                "receive_id": self.chat_id,
                "msg_type": "text",
                "content": content,
            }
        return (
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

    def send_msg(self, text: str) -> None:
        request = self._build_request(text)
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

    sendMsg = send_msg
    OnThinking = on_thinking
    OnToolCall = on_tool_call
    OnToolResult = on_tool_result
    OnMessage = on_message


def new_feishu_bot(engine: Any, client: Optional[Any] = None) -> FeishuBot:
    return FeishuBot(engine=engine, client=client)


NewFeishuBot = new_feishu_bot
