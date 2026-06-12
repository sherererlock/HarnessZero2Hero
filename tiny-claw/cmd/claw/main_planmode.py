import argparse
import logging

from common import (
    build_engine_for_work_dir,
    configure_logging,
    new_bash_tool,
    new_edit_file_tool,
    new_read_file_tool,
    new_write_file_tool,
    require_env_vars,
    resolve_work_dir,
)
from internal.engine.session import GlobalSessionMgr
from internal.engine.terminal_reporter import new_terminal_reporter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="以计划模式运行 tiny-claw。")
    parser.add_argument("--prompt", required=True, help="要交给 Agent 执行的任务描述")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()
    require_env_vars(("ZHIPU_API_KEY",))

    work_dir = resolve_work_dir()
    engine = build_engine_for_work_dir(
        work_dir=work_dir,
        tool_factories=[
            new_read_file_tool,
            new_write_file_tool,
            new_bash_tool,
            new_edit_file_tool,
        ],
        enable_thinking=False,
        plan_mode=True,
    )
    reporter = new_terminal_reporter()

    # 保持固定 session id，便于多次运行时复用短期工作记忆。
    session = GlobalSessionMgr.get_or_create("task_web_server_01", work_dir)
    logging.info(">>> 收到指令: %s", args.prompt)

    err = engine.run(args.prompt, session=session, reporter=reporter)
    if err is not None:
        logging.error("引擎运行崩溃: %s", err)
        raise SystemExit(1) from err


if __name__ == "__main__":
    main()
