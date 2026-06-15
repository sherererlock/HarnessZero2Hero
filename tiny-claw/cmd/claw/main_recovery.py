from common import (
    new_bash_tool,
    new_edit_file_tool,
    new_read_file_tool,
    new_write_file_tool,
    run_prompt_main,
)


def main() -> None:
    prompt = """
我当前目录下有一个 auth.py 文件。
请修改 auth.py 中的 login 函数。
请直接使用 edit_file 工具替换下面的代码块，将判断条件改为同时允许"admin"、"root"和"guest"三种用户登录：
// 鉴权入口函数
def login(user: str) -> bool:
    if user == "admin":
        return True
    return False


你只负责修改，不允许提交
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
