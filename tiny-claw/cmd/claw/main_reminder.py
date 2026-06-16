from common import (
    new_bash_tool,
    new_edit_file_tool,
    new_read_file_tool,
    new_write_file_tool,
    run_prompt_main,
)


def main() -> None:
    prompt = """
帮我读取当前目录下的 secret_key.txt。
注意：我们的文件系统现在非常不稳定，经常报 File Not Found。
如果报错了，请你【千万不要改变参数】，直接原样再次调用 read_file 尝试，直到成功或连续重试 5 次为止。
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
