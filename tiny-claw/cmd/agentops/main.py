import logging
import os
import sys
from typing import Any, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
REPO_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, ".."))

from internal.engine.loop import AgentEngine
from internal.engine.session import GlobalSessionMgr, Session
from internal.feishu.approval import GlobalApprovalMgr, is_dangerous_command
from internal.feishu.bot import FeishuBot
from internal.observability.tracker import new_cost_tracker
from internal.provider.env_loader import _candidate_env_paths, _read_env_value
from internal.provider.openai import new_zhipu_openai_provider
from internal.tools.Bash import new_bash_tool
from internal.tools.edit_file import new_edit_file_tool
from internal.tools.readfile import new_read_file_tool
from internal.tools.registry import new_registry
from internal.tools.write import new_write_file_tool


MODEL_NAME = "xiaomi/mimo-v2.5"


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y/%m/%d %H:%M:%S",
    )
    for logger_name in ("httpx", "httpcore", "openai"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _resolve_env_value(name: str, start_dirs: list[str] | None = None) -> str | None:
    env_value = os.getenv(name)
    if env_value:
        return env_value

    search_dirs = start_dirs if start_dirs is not None else [os.getcwd(), os.path.dirname(__file__)]
    seen_paths = set()
    for start_dir in search_dirs:
        for env_path in _candidate_env_paths(start_dir):
            if env_path in seen_paths:
                continue
            seen_paths.add(env_path)

            value = _read_env_value(env_path, name)
            if value:
                return value
    return None


def validate_required_env_vars(start_dirs: list[str] | None = None) -> None:
    required = ["ZHIPU_API_KEY", "FEISHU_APP_ID", "FEISHU_APP_SECRET"]
    missing = []
    for name in required:
        value = _resolve_env_value(name, start_dirs=start_dirs)
        if not value:
            missing.append(name)
            continue
        os.environ.setdefault(name, value)

    if missing:
        raise RuntimeError("请先设置环境变量: " + ", ".join(missing))


def resolve_work_dir() -> str:
    return os.path.join(REPO_ROOT, "workspace_ops")


def build_agentops_registry(work_dir: str, reporter: Any):
    registry = new_registry()
    for tool_factory in (
        new_read_file_tool,
        new_write_file_tool,
        new_bash_tool,
        new_edit_file_tool,
    ):
        registry.register(tool_factory(work_dir))

    def approval_middleware(call) -> tuple[bool, str]:
        if not is_dangerous_command(call.name, call.arguments):
            return True, ""

        logging.info("[Middleware] 拦截到高危操作: %s，触发飞书审批挂起...", call.name)
        allowed, reason = GlobalApprovalMgr.wait_for_approval(
            task_id=call.id,
            tool_name=call.name,
            args=call.arguments,
            reporter=reporter,
        )
        if not allowed:
            return False, reason
        return True, ""

    registry.use(approval_middleware)
    return registry


class AgentOpsFeishuBot(FeishuBot):
    """贴近文章语义的 Python 版 AgentOps 入口：按请求动态装配引擎。"""

    def __init__(
        self,
        work_dir: str,
        model_name: str = MODEL_NAME,
        client: Optional[Any] = None,
    ):
        super().__init__(engine=None, session=None, client=client)
        self.work_dir = work_dir
        self.model_name = model_name
        self.base_provider = new_zhipu_openai_provider(model_name)

    def _build_session_engine(self, session: Session, reporter: Any) -> AgentEngine:
        registry = build_agentops_registry(self.work_dir, reporter)
        tracked_provider = new_cost_tracker(
            next_provider=self.base_provider,
            model_name=self.model_name,
            session=session,
        )
        return AgentEngine(
            provider=tracked_provider,
            registry=registry,
            enable_thinking=False,
            PlanMode=False,
        )

    def handle_agent_run(self, chat_id: str, prompt: str) -> None:
        reporter = self._get_or_create_reporter(chat_id)
        session = GlobalSessionMgr.get_or_create(chat_id, self.work_dir)
        engine = self._build_session_engine(session, reporter)

        err = engine.run(prompt, session=session, reporter=reporter)
        if err is not None:
            reporter.send_msg(f"❌ Agent 运行崩溃: {err}")


def main() -> None:
    configure_logging()
    validate_required_env_vars()

    work_dir = resolve_work_dir()
    os.makedirs(work_dir, exist_ok=True)

    bot = AgentOpsFeishuBot(work_dir=work_dir, model_name=MODEL_NAME)
    logging.info("tiny-claw AgentOps 飞书长连接模式启动中")
    logging.info("工作区已就绪: %s", work_dir)
    bot.start_websocket()


if __name__ == "__main__":
    main()
