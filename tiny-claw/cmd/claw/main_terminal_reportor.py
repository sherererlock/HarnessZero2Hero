from common import (
    new_bash_tool,
    new_edit_file_tool,
    new_read_file_tool,
    new_write_file_tool,
    run_prompt_main_with_reporter,
)
from internal.engine.terminal_reporter import new_terminal_reporter


def main() -> None:
    prompt = """
我需要在当前目录下新建一个 ping.py，提供一个简单的 http ping 接口。
写完之后，帮我把代码用 git 提交一下。
"""
    run_prompt_main_with_reporter(
        prompt=prompt,
        tool_factories=[
            new_read_file_tool,
            new_write_file_tool,
            new_bash_tool,
            new_edit_file_tool,
        ],
        reporter=new_terminal_reporter(),
        enable_thinking=False,
    )


if __name__ == "__main__":
    main()
