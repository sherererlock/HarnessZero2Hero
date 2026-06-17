import logging

from common import (
    AgentEngine,
    configure_logging,
    new_bash_tool,
    new_edit_file_tool,
    new_read_file_tool,
    new_registry,
    new_write_file_tool,
    new_zhipu_openai_provider,
    resolve_work_dir,
)
from main_feishu import validate_required_env_vars
from internal.engine.session import GlobalSessionMgr
from internal.feishu.approval import GlobalApprovalMgr, is_dangerous_command
from internal.feishu.bot import new_feishu_bot


def build_engine_with_registry(work_dir: str) -> tuple[AgentEngine, object]:
    registry = new_registry()
    for tool_factory in (
        new_read_file_tool,
        new_write_file_tool,
        new_bash_tool,
        new_edit_file_tool,
    ):
        registry.register(tool_factory(work_dir))

    engine = AgentEngine(
        provider=new_zhipu_openai_provider("xiaomi/mimo-v2.5"),
        registry=registry,
        enable_thinking=False,
        PlanMode=False,
    )
    return engine, registry


def main() -> None:
    configure_logging()
    validate_required_env_vars()

    work_dir = resolve_work_dir()
    engine, registry = build_engine_with_registry(work_dir)

    session_id = "test_command_intercept_001"
    session = GlobalSessionMgr.get_or_create(session_id, work_dir)
    bot = new_feishu_bot(engine, session=session)

    def approval_middleware(call) -> tuple[bool, str]:
        if not is_dangerous_command(call.name, call.arguments):
            return True, ""

        allowed, reason = GlobalApprovalMgr.wait_for_approval(
            task_id=call.id,
            tool_name=call.name,
            args=call.arguments,
            reporter=bot.reporter(),
        )
        if not allowed:
            return False, reason
        return True, ""

    registry.use(approval_middleware)
    logging.info("go-tiny-claw 飞书长连接模式启动中，已启用高危操作审批中间件")
    bot.start_websocket()


if __name__ == "__main__":
    main()
