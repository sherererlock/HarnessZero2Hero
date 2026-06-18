import logging

from common import (
    build_engine_for_work_dir,
    configure_logging,
    new_bash_tool,
    new_cli_session,
    new_edit_file_tool,
    new_read_file_tool,
    new_write_file_tool,
    require_env_vars,
    resolve_work_dir,
)
from internal.engine.terminal_reporter import new_terminal_reporter
from internal.tools.readfile import new_read_file_tool as new_read_only_file_tool
from internal.tools.registry import new_registry
from internal.tools.subagent import new_subagent_tool
from internal.tools.Bash import new_bash_tool as new_read_only_bash_tool


def main() -> None:
    configure_logging()
    require_env_vars(("ZHIPU_API_KEY",))

    work_dir = resolve_work_dir()
    reporter = new_terminal_reporter()

    read_only_registry = new_registry()
    read_only_registry.register(new_read_only_file_tool(work_dir))
    read_only_registry.register(new_read_only_bash_tool(work_dir))

    engine = build_engine_for_work_dir(
        work_dir=work_dir,
        tool_factories=[
            new_read_file_tool,
            new_write_file_tool,
            new_bash_tool,
            new_edit_file_tool,
        ],
        enable_thinking=False,
    )
    engine.registry.register(new_subagent_tool(engine, read_only_registry, reporter))

    session = new_cli_session()
    prompt = """
我需要你在这个遗留项目里，找到那个“核心密码”。
为了防止污染主上下文，请你务必派出子智能体（spawn_subagent）去执行探索任务。
你可以让子智能体使用 bash 去查找当前目录及其所有子目录下名为 config.txt 的文件。
子智能体拿到密码向你汇报后，请你亲自使用 write_file 工具，将密码写在根目录的 answer.txt 里。
"""

    logging.info(">>> 启动多智能体协同测试...")
    err = engine.run(prompt, session=session, reporter=reporter)
    if err is not None:
        logging.error("引擎运行崩溃: %s", err)
        raise SystemExit(1) from err


if __name__ == "__main__":
    main()
