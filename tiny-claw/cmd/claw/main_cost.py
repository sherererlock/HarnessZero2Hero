import logging

from common import (
    build_engine_with_provider_for_work_dir,
    configure_logging,
    new_bash_tool,
    require_env_vars,
    resolve_work_dir,
)
from internal.engine.session import GlobalSessionMgr
from internal.engine.terminal_reporter import new_terminal_reporter
from internal.observability.tracker import new_cost_tracker
from internal.provider.openai import new_zhipu_openai_provider


def main() -> None:
    configure_logging()
    require_env_vars(("ZHIPU_API_KEY",))

    work_dir = resolve_work_dir()
    model_name = "xiaomi/mimo-v2.5"
    session_id = "test_observability_001"
    session = GlobalSessionMgr.get_or_create(session_id, work_dir)

    real_provider = new_zhipu_openai_provider(model_name)
    tracked_provider = new_cost_tracker(real_provider, model_name, session)
    engine = build_engine_with_provider_for_work_dir(
        provider=tracked_provider,
        work_dir=work_dir,
        tool_factories=[new_bash_tool],
        enable_thinking=False,
        plan_mode=False,
    )
    reporter = new_terminal_reporter()
    prompt = "请用 bash 帮我用 date 命令查一下现在的时间。"

    logging.info("\n>>> 启动带仪表盘的可观测性测试...")
    err = engine.run(prompt, session=session, reporter=reporter)
    if err is not None:
        logging.error("引擎运行崩溃: %s", err)
        raise SystemExit(1)

    logging.info("\n================ 财务报表 ================")
    logging.info("会话 ID: %s", session.id)
    logging.info("总消耗 Input Tokens: %d", session.total_prompt_tokens)
    logging.info("总消耗 Output Tokens: %d", session.total_completion_tokens)
    logging.info("总计费用 (CNY): ¥%.6f", session.total_cost_cny)
    logging.info("==========================================")


if __name__ == "__main__":
    main()
