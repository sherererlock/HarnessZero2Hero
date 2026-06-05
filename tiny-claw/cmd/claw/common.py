import logging
import os
import sys
from typing import Callable, Iterable

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
from internal.tools.registry import BaseTool, new_registry
from internal.tools.write import new_write_file_tool

ToolFactory = Callable[[str], BaseTool]


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y/%m/%d %H:%M:%S",
    )
    # 保留业务日志，同时压低第三方 HTTP 客户端的请求日志噪音。
    for logger_name in ("httpx", "httpcore", "openai"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def build_engine(
    tool_factories: Iterable[ToolFactory],
    model: str = "xiaomi/mimo-v2.5",
    enable_thinking: bool = False,
) -> AgentEngine:
    work_dir = os.getcwd()
    llm_provider = new_zhipu_openai_provider(model)
    registry = new_registry()

    for tool_factory in tool_factories:
        registry.register(tool_factory(work_dir))

    return AgentEngine(
        provider=llm_provider,
        registry=registry,
        work_dir=work_dir,
        enable_thinking=enable_thinking,
    )


def run_prompt_main(
    prompt: str,
    tool_factories: Iterable[ToolFactory],
    model: str = "xiaomi/mimo-v2.5",
    enable_thinking: bool = True,
) -> None:
    configure_logging()
    engine = build_engine(
        tool_factories=tool_factories,
        model=model,
        enable_thinking=enable_thinking,
    )

    err = engine.run(prompt)
    if err is not None:
        logging.error("引擎运行崩溃: %s", err)
        raise SystemExit(1) from err
