import logging

from common import (
    build_engine_for_work_dir,
    configure_logging,
    new_bash_tool,
    new_write_file_tool,
    require_env_vars,
    resolve_work_dir,
)
from internal.engine.session import GlobalSessionMgr
from internal.engine.terminal_reporter import new_terminal_reporter


def main() -> None:
    configure_logging()
    require_env_vars(("ZHIPU_API_KEY",))

    work_dir = resolve_work_dir()
    session_id = "test_trace_001"
    session = GlobalSessionMgr.get_or_create(session_id, work_dir)
    engine = build_engine_for_work_dir(
        work_dir=work_dir,
        tool_factories=[new_bash_tool, new_write_file_tool],
        model="xiaomi/mimo-v2.5",
        enable_thinking=False,
        plan_mode=False,
    )
    reporter = new_terminal_reporter()
    prompt = """
为了加快执行速度，请你在一轮回复中，【同时并行】完成以下两件事：
1. 使用 bash 工具执行一个短命令，确认系统环境可用。
2. 使用 write_file 工具，在当前目录下创建一个 `trace_test.md`，内容写上“测试并发的写入”。
请确保你是分别调用两个不同的工具，不要试图把它们合并成一个命令。
"""

    logging.info("\n>>> 启动带 Tracing 链路追踪的测试...")
    err = engine.run(prompt, session=session, reporter=reporter)
    if err is not None:
        logging.error("引擎运行崩溃: %s", err)
        raise SystemExit(1)

    logging.info(
        "Tracing 已导出到工作区目录: %s",
        f"{work_dir}\\.claw\\traces",
    )


if __name__ == "__main__":
    main()
