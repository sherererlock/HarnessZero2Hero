import logging
import os

from common import (
    build_engine_for_work_dir,
    configure_logging,
    new_bash_tool,
    new_read_file_tool,
    new_write_file_tool,
    require_env_vars,
)
from internal.engine.session import GlobalSessionMgr
from internal.engine.terminal_reporter import new_terminal_reporter


def build_prompt() -> str:
    return """
请帮我执行以下三个步骤：
1. 使用 bash 执行 echo "开始排查日志"
2. 使用 read_file 工具读取当前目录下的巨大文件 mock_log.txt
3. 使用 bash 执行 date 命令获取当前时间，并告诉我任务全部完成。
""".strip()


def main() -> None:
    configure_logging()
    require_env_vars(("ZHIPU_API_KEY",))

    # 保持与原 Go 版本一致：工作目录就是脚本启动时所在目录。
    work_dir = os.getcwd() + "/workspace"
    engine = build_engine_for_work_dir(
        work_dir=work_dir,
        tool_factories=[new_read_file_tool, new_write_file_tool, new_bash_tool],
        enable_thinking=False,
    )
    reporter = new_terminal_reporter()
    session = GlobalSessionMgr.get_or_create("test_oom_protection_001", work_dir)

    err = engine.run(build_prompt(), session=session, reporter=reporter)
    if err is not None:
        logging.error("引擎运行崩溃: %s", err)
        raise SystemExit(1) from err


if __name__ == "__main__":
    main()
