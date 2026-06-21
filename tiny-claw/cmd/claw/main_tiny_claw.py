import argparse
import logging
import os

from common import (
    build_engine_with_provider_for_work_dir,
    configure_logging,
    new_bash_tool,
    new_edit_file_tool,
    new_read_file_tool,
    new_write_file_tool,
    new_zhipu_openai_provider,
    require_env_vars,
)
from internal.engine.session import GlobalSessionMgr
from internal.engine.terminal_reporter import new_terminal_reporter
from internal.observability.tracker import new_cost_tracker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 tiny-claw 命令行入口。")
    parser.add_argument("--prompt", required=False, help="要交给 Agent 执行的任务描述", default="我感觉这个项目里的代码好像有严重的并发安全问题。请你在这个目录下自行探索，找到问题文件，分析原因，并进行修复和正确性验证")
    parser.add_argument(
        "--dir",
        default="./workspace",
        help="Agent 运行的工作区目录路径，默认为当前目录",
    )
    parser.add_argument(
        "--session",
        default="cli_default_session",
        help="指定会话 ID，支持断点续传",
    )
    parser.add_argument(
        "--model",
        default="xiaomi/mimo-v2.5",
        help="指定要使用的模型名称",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()
    require_env_vars(("ZHIPU_API_KEY",))

    work_dir = os.path.abspath(args.dir)
    session = GlobalSessionMgr.get_or_create(args.session, work_dir)

    real_provider = new_zhipu_openai_provider(args.model)
    tracked_provider = new_cost_tracker(real_provider, args.model, session)
    engine = build_engine_with_provider_for_work_dir(
        provider=tracked_provider,
        work_dir=work_dir,
        tool_factories=[
            new_read_file_tool,
            new_write_file_tool,
            new_bash_tool,
            new_edit_file_tool,
        ],
        enable_thinking=False,
        plan_mode=False,
    )
    reporter = new_terminal_reporter()

    logging.info("启动 tiny-claw CLI，引擎工作区: %s", work_dir)
    logging.info("使用会话 ID: %s", args.session)
    logging.info("使用模型: %s", args.model)

    err = engine.run(args.prompt, session=session, reporter=reporter)
    if err is not None:
        logging.error("引擎运行崩溃: %s", err)
        raise SystemExit(1) from err


if __name__ == "__main__":
    main()
