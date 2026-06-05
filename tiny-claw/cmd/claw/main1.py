from common import new_bash_tool, new_read_file_tool, new_write_file_tool, run_prompt_main


def main() -> None:
    prompt = """
请帮我执行以下操作：
1. 用 bash 查看一下我当前电脑的 python 版本。
2. 帮我写一个简单的 helloworld.py 文件，输出 "Hello, python-tiny-claw!"。
3. 用 bash 编译并运行这个 python 文件，确认它能正常工作。
"""
    run_prompt_main(
        prompt=prompt,
        tool_factories=[new_read_file_tool, new_write_file_tool, new_bash_tool],
    )


if __name__ == "__main__":
    main()
