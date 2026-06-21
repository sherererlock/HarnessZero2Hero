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
from internal.engine.session import GlobalSessionMgr, Session
from internal.feishu.approval import GlobalApprovalMgr

try:
    import lark_oapi as lark
    from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
    import lark_oapi.api.im.v1 as larkim
    import lark_oapi.ws as larkws
except ImportError:
    lark = None
    P2CardActionTriggerResponse = None
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
    """适配飞书 WS SDK 所需的事件处理接口。"""

    def __init__(self, bot: "FeishuBot"):
        self.bot = bot

    def _dispatch_payload(self, payload: bytes) -> Any:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        event = json.loads(payload)
        return self.bot.dispatch_event(event)

    def _do_without_validation(self, payload: bytes) -> Any:
        return self._dispatch_payload(payload)

    def do_without_validation(self, payload: bytes) -> Any:
        return self._dispatch_payload(payload)


class FeishuBot:
    """FeishuBot 封装了飞书机器人的配置与核心业务流。"""

    def __init__(
        self,
        engine: Any,
        session: Optional[Session] = None,
        client: Optional[Any] = None,
    ):
        app_id = os.getenv("FEISHU_APP_ID", "")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")
        if not app_id or not app_secret:
            raise RuntimeError("请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")

        self.app_id = app_id
        self.app_secret = app_secret
        self.engine = engine
        self.sess = session
        self.client = client or self._build_client()
        # 按 chat_id 隔离 reporter，避免并发请求互相覆盖目标会话。
        self._reporters: dict[str, FeishuReporter] = {}
        self._reporters_lock = threading.RLock()

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

    def dispatch_event(self, event: Any) -> Any:
        header = _read_field(event, "header")
        event_type = _read_field(header, "event_type") or _read_field(event, "event_type")
        if event_type == "card.action.trigger":
            return self.handle_card_action_event(event)

        event_body = _read_field(event, "event") or event
        message = _read_field(event_body, "message")
        if message is None:
            logging.debug("[Feishu] 忽略非消息事件: %r", event)
            return
        self.handle_message_event(event)

    def create_event_dispatcher(self, verify_token: str, encrypt_key: str):
        del verify_token, encrypt_key

        def dispatcher(event: Any) -> None:
            self.dispatch_event(event)

        return dispatcher

    def _get_or_create_reporter(self, chat_id: str) -> "FeishuReporter":
        with self._reporters_lock:
            reporter = self._reporters.get(chat_id)
            if reporter is None:
                reporter = FeishuReporter(client=self.client, chat_id=chat_id)
                self._reporters[chat_id] = reporter
            return reporter

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

        stripped_content = content.strip()
        if stripped_content.startswith("approve "):
            task_id = stripped_content.removeprefix("approve ").strip()
            if task_id:
                GlobalApprovalMgr.resolve_approval(
                    task_id,
                    True,
                    "人类管理员已批准操作",
                )
                logging.info("[Feishu] 会话 %s: 已批准任务 %s", chat_id, task_id)
            return

        if stripped_content.startswith("reject "):
            task_id = stripped_content.removeprefix("reject ").strip()
            if task_id:
                GlobalApprovalMgr.resolve_approval(
                    task_id,
                    False,
                    "人类管理员认为该操作存在极高风险，已无情拒绝",
                )
                logging.info("[Feishu] 会话 %s: 已拒绝任务 %s", chat_id, task_id)
            return

        threading.Thread(
            target=self.handle_agent_run,
            args=(chat_id, content),
            daemon=True,
        ).start()

    def handle_card_action_event(self, event: Any) -> Any:
        event_body = _read_field(event, "event") or event
        action = _read_field(event_body, "action")
        value = _read_field(action, "value") or {}
        action_name = _read_field(value, "action")
        task_id = _read_field(value, "task_id")
        operator = _read_field(event_body, "operator") or {}
        operator_id = (
            _read_field(operator, "user_id")
            or _read_field(operator, "open_id")
            or _read_field(operator, "union_id")
            or "unknown-user"
        )

        if not task_id or action_name not in {"approve", "reject"}:
            logging.warning("[Feishu] 收到无法识别的卡片回调: %r", event)
            return self._build_card_callback_response(
                toast_type="warning",
                toast_content="未识别到有效的审批任务，卡片保持不变。",
            )

        allowed = action_name == "approve"
        pending = GlobalApprovalMgr.get_pending_task(task_id)
        reason = (
            f"飞书审批按钮已批准，操作人: {operator_id}"
            if allowed
            else f"飞书审批按钮已拒绝，操作人: {operator_id}"
        )
        GlobalApprovalMgr.resolve_approval(task_id, allowed, reason)
        logging.info(
            "[Feishu] 收到卡片审批结果 (TaskID: %s, Allowed: %s, Operator: %s)",
            task_id,
            allowed,
            operator_id,
        )
        if pending is None:
            return self._build_card_callback_response(
                toast_type="warning",
                toast_content="审批结果已收到，但任务可能已处理完成，卡片保持不变。",
            )

        resolved_card = GlobalApprovalMgr.build_resolved_card(
            task_id=task_id,
            tool_name=pending.tool_name,
            args=pending.args,
            allowed=allowed,
            operator_id=operator_id,
        )
        return self._build_card_callback_response(
            toast_type="success" if allowed else "warning",
            toast_content="已批准该操作" if allowed else "已拒绝该操作",
            card=resolved_card,
        )

    def _build_card_callback_response(
        self,
        toast_type: str,
        toast_content: str,
        card: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "toast": {
                "type": toast_type,
                "content": toast_content,
            }
        }
        if card is not None:
            payload["card"] = {
                "type": "raw",
                "data": card,
            }
        if P2CardActionTriggerResponse is not None:
            return P2CardActionTriggerResponse(payload)
        return payload

    def reporter(self, chat_id: Optional[str] = None) -> Optional["FeishuReporter"]:
        with self._reporters_lock:
            if chat_id is not None:
                return self._reporters.get(chat_id)

            if len(self._reporters) == 1:
                return next(iter(self._reporters.values()))

        if chat_id is None and self._reporters:
            logging.warning("[Feishu] 当前存在多个活跃会话，请显式传入 chat_id 获取 reporter")
        return None

    def handle_agent_run(self, chat_id: str, prompt: str) -> None:
        reporter = self._get_or_create_reporter(chat_id)

        if self.sess is not None:
            session = self.sess
        else:
            work_dir = os.path.join(os.getcwd(), "workspace")
            session = GlobalSessionMgr.get_or_create(chat_id, work_dir)

        err = self.engine.run(prompt, session=session, reporter=reporter)
        if err is not None:
            reporter.send_msg(f"❌ Agent 运行崩溃: {err}")

    StartWebSocket = start_websocket
    GetEventDispatcher = get_event_dispatcher
    dispatchEvent = dispatch_event
    createEventDispatcher = create_event_dispatcher
    handleMessageEvent = handle_message_event
    Reporter = reporter
    handleAgentRun = handle_agent_run


class FeishuReporter(Reporter):
    """将引擎输出格式化后发给飞书。"""

    def __init__(self, client: Any, chat_id: str):
        self.client = client
        self.chat_id = chat_id

    def _build_request(self, msg_type: str, content: str) -> Any:
        if larkim is None:
            return {
                "receive_id_type": "chat_id",
                "receive_id": self.chat_id,
                "msg_type": msg_type,
                "content": content,
            }
        return (
            larkim.CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                larkim.CreateMessageRequestBody.builder()
                .receive_id(self.chat_id)
                .msg_type(msg_type)
                .content(content)
                .build()
            )
            .build()
        )

    def send_msg(self, text: str) -> None:
        content = json.dumps({"text": text}, ensure_ascii=False)
        request = self._build_request("text", content)
        self.client.im.v1.message.create(request)

    def send_interactive_card(self, card: Mapping[str, Any]) -> None:
        content = json.dumps(card, ensure_ascii=False)
        request = self._build_request("interactive", content)
        self.client.im.v1.message.create(request)

    def on_thinking(self) -> None:
        # self.send_msg("🤔 模型正在慢思考 (Thinking)...")
        logging.info("on_thinking 🤔 模型正在慢思考 (Thinking)")



    def on_tool_call(self, tool_name: str, args: str) -> None:
        # self.send_msg(f"🛠️ 正在执行工具：{tool_name}\n参数：{args}")
        logging.info(f"on_tool_call 🛠️ 正在执行工具：{tool_name}\n参数：{args}")

    def on_tool_result(self, tool_name: str, result: str, is_error: bool) -> None:
        if is_error:
            self.send_msg(f"⚠️ 执行报错 ({tool_name})：\n{result}")
            logging.error(f"on_tool_result ⚠️ 执行报错 ({tool_name})：\n{result}")
            return
        # self.send_msg(f"✅ 执行成功 ({tool_name})")
        logging.info(f"on_tool_result ✅ 执行成功 ({tool_name})")

    def on_message(self, content: str) -> None:
        self.send_msg(content)

    sendMsg = send_msg
    OnThinking = on_thinking
    OnToolCall = on_tool_call
    OnToolResult = on_tool_result
    OnMessage = on_message


def new_feishu_bot(
    engine: Any,
    session: Optional[Session] = None,
    client: Optional[Any] = None,
) -> FeishuBot:
    return FeishuBot(engine=engine, session=session, client=client)


NewFeishuBot = new_feishu_bot
