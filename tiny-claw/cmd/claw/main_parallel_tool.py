from common import (
    new_bash_tool,
    new_edit_file_tool,
    new_read_file_tool,
    new_write_file_tool,
    run_prompt_main,
)


def main() -> None:
    prompt = """
我当前目录下有 a.txt、b.txt、c.txt 三个文件。
为了节省时间，请你同时一次性读取这三个文件，并将它们的内容综合起来，告诉我它们分别记录了什么领域的信息。
"""
    run_prompt_main(
        prompt=prompt,
        tool_factories=[
            new_read_file_tool,
            new_write_file_tool,
            new_bash_tool,
            new_edit_file_tool,
        ],

        enable_thinking=False,
    )


if __name__ == "__main__":
    main()
