import logging
import os
import time

from common import (
    build_engine_for_work_dir,
    new_read_file_tool,
    resolve_work_dir,
    run_parallel_main,
)
from internal.engine.session import GlobalSessionMgr
from internal.engine.terminal_reporter import new_terminal_reporter
from internal.schema.message import Message, Role

def run_front_group(reporter) -> None:
    work_dir = os.path.join(resolve_work_dir(), "tmp/project_frontend")
    engine = build_engine_for_work_dir(
        work_dir=work_dir,
        tool_factories=[new_read_file_tool],
        enable_thinking=False,
    )
    session = GlobalSessionMgr.get_or_create("chat_front_001", work_dir)

    prompt_turn_1 = "帮我看看 README.md 里记录了什么内容？"
    logging.info("\n>>> [Session A / Turn 1]: %s", prompt_turn_1)
    err = engine.run(prompt_turn_1, session=session, reporter=reporter)
    if err is not None:
        logging.error("[Session A / Turn 1] 运行失败: %s", err)
        return

    # 故意注入大量闲聊，把第一轮的关键信息挤出 working memory。
    for _ in range(6):
        session.append(
            Message(role=Role.USER, content="这只是一句闲聊占位符。"),
            Message(role=Role.ASSISTANT, content="好的，收到闲聊。"),
        )

    prompt_turn_2 = "请直接告诉我，刚才第一轮你查到的内容是什么？不准调用工具！"
    logging.info("\n>>> [Session A / Turn 2]: %s", prompt_turn_2)
    err = engine.run(prompt_turn_2, session=session, reporter=reporter)
    if err is not None:
        logging.error("[Session A / Turn 2] 运行失败: %s", err)


def run_back_group(reporter) -> None:
    time.sleep(2)
    work_dir = os.path.join(resolve_work_dir(), "tmp/project_backend")
    engine = build_engine_for_work_dir(
        work_dir=work_dir,
        tool_factories=[new_read_file_tool],
        enable_thinking=False,
    )
    session = GlobalSessionMgr.get_or_create("chat_back_002", work_dir)

    prompt = "别人查到了一个密钥，你这里能看到吗？不准调用工具！"
    logging.info("\n>>> [Session B]: %s", prompt)
    err = engine.run(prompt, session=session, reporter=reporter)
    if err is not None:
        logging.error("[Session B] 运行失败: %s", err)


def main() -> None:
    run_parallel_main(
        targets=[run_front_group, run_back_group],
        reporter_factory=new_terminal_reporter,
        required_env_vars=("ZHIPU_API_KEY",),
    )


if __name__ == "__main__":
    main()
