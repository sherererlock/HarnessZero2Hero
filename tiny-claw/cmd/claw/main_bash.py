import logging
import os
import sys

# 让直接运行脚本时也能找到项目内模块。
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from internal.engine.loop import AgentEngine
from internal.provider.openai import new_zhipu_openai_provider
from internal.tools.Bash import new_bash_tool
from internal.tools.edit_file import new_edit_file_tool
from internal.tools.readfile import new_read_file_tool
from internal.tools.registry import new_registry
from internal.tools.write import new_write_file_tool


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y/%m/%d %H:%M:%S",
)


def main() -> None:
    work_dir = os.getcwd()

    llm_provider = new_zhipu_openai_provider("xiaomi/mimo-v2.5")
    registry = new_registry()

    registry.register(new_read_file_tool(work_dir))
    registry.register(new_write_file_tool(work_dir))
    registry.register(new_bash_tool(work_dir))
    registry.register(new_edit_file_tool(work_dir))

    engine = AgentEngine(
        provider=llm_provider,
        registry=registry,
        work_dir=work_dir,
        enable_thinking=False,
    )

    prompt = """
我当前目录下有一个 server.py 文件。
请帮我把里面 "TODO: 增加鉴权逻辑" 下面的那个 if 语句，整个替换为：
if user == None:
    print("Forbidden!")
    return
"""
    try:
        engine.run(prompt)
    except Exception as exc:
        logging.error("引擎运行崩溃: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
