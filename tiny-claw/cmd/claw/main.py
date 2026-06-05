from common import new_read_file_tool, run_prompt_main


def main() -> None:
    prompt = "请调用工具读取一下当前工作区目录下 hello.txt 文件的内容，并用一句话向我总结它说了什么。"
    run_prompt_main(
        prompt=prompt,
        tool_factories=[new_read_file_tool],
    )


if __name__ == "__main__":
    main()
