import logging
import os
import sys
import threading
import uuid
from typing import Callable, Iterable, Optional

# 让直接运行脚本时也能找到项目内模块。
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from internal.engine.loop import AgentEngine
from internal.engine.reportor import Reporter
from internal.engine.session import new_session
from internal.provider.env_loader import _candidate_env_paths, _read_env_value
from internal.provider.openai import new_zhipu_openai_provider
from internal.tools.Bash import new_bash_tool
from internal.tools.edit_file import new_edit_file_tool
from internal.tools.readfile import new_read_file_tool
from internal.tools.registry import BaseTool, new_registry
from internal.tools.write import new_write_file_tool

ToolFactory = Callable[[str], BaseTool]
ParallelTarget = Callable[[Reporter], None]
ReporterFactory = Callable[[], Reporter]


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y/%m/%d %H:%M:%S",
    )
    # 保留业务日志，同时压低第三方 HTTP 客户端的请求日志噪音。
    for logger_name in ("httpx", "httpcore", "openai"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def require_env_vars(names: Iterable[str]) -> None:
    missing = []
    search_dirs = [os.getcwd(), os.path.dirname(__file__)]

    for name in names:
        if os.getenv(name, ""):
            continue

        seen_paths = set()
        resolved_value = None
        for start_dir in search_dirs:
            for env_path in _candidate_env_paths(start_dir):
                if env_path in seen_paths:
                    continue
                seen_paths.add(env_path)

                resolved_value = _read_env_value(env_path, name)
                if resolved_value:
                    break
            if resolved_value:
                break

        if resolved_value:
            os.environ[name] = resolved_value
            continue

        missing.append(name)

    if missing:
        raise RuntimeError("请先导出环境变量: " + ", ".join(missing))


def resolve_work_dir() -> str:
    return os.path.join(os.getcwd(), "workspace")


def new_cli_session():
    work_dir = resolve_work_dir()
    return new_session(session_id=f"cli-{uuid.uuid4().hex}", work_dir=work_dir)


def build_engine_for_work_dir(
    work_dir: str,
    tool_factories: Iterable[ToolFactory],
    model: str = "xiaomi/mimo-v2.5",
    enable_thinking: bool = False,
    plan_mode: bool = False,
) -> AgentEngine:
    llm_provider = new_zhipu_openai_provider(model)
    registry = new_registry()

    for tool_factory in tool_factories:
        registry.register(tool_factory(work_dir))

    return AgentEngine(
        provider=llm_provider,
        registry=registry,
        enable_thinking=enable_thinking,
        PlanMode=plan_mode,
    )


def build_engine(
    tool_factories: Iterable[ToolFactory],
    model: str = "xiaomi/mimo-v2.5",
    enable_thinking: bool = False,
    plan_mode: bool = False,
) -> AgentEngine:
    work_dir = resolve_work_dir()
    return build_engine_for_work_dir(
        work_dir=work_dir,
        tool_factories=tool_factories,
        model=model,
        enable_thinking=enable_thinking,
        plan_mode=plan_mode,
    )


def run_prompt_main(
    prompt: str,
    tool_factories: Iterable[ToolFactory],
    model: str = "xiaomi/mimo-v2.5",
    enable_thinking: bool = True,
    plan_mode: bool = False,
) -> None:
    configure_logging()
    engine = build_engine(
        tool_factories=tool_factories,
        model=model,
        enable_thinking=enable_thinking,
        plan_mode=plan_mode,
    )
    session = new_cli_session()

    err = engine.run(prompt, session=session)
    if err is not None:
        logging.error("引擎运行崩溃: %s", err)
        raise SystemExit(1) from err


def run_prompt_main_with_reporter(
    prompt: str,
    tool_factories: Iterable[ToolFactory],
    reporter: Optional[Reporter],
    model: str = "xiaomi/mimo-v2.5",
    enable_thinking: bool = True,
    plan_mode: bool = False,
) -> None:
    configure_logging()
    engine = build_engine(
        tool_factories=tool_factories,
        model=model,
        enable_thinking=enable_thinking,
        plan_mode=plan_mode,
    )
    session = new_cli_session()

    err = engine.run(prompt, session=session, reporter=reporter)
    if err is not None:
        logging.error("引擎运行崩溃: %s", err)
        raise SystemExit(1) from err


def run_parallel_main(
    targets: Iterable[ParallelTarget],
    reporter_factory: ReporterFactory,
    required_env_vars: Iterable[str] = ("ZHIPU_API_KEY",),
) -> None:
    configure_logging()
    require_env_vars(required_env_vars)
    reporter = reporter_factory()

    threads = [
        threading.Thread(target=target, args=(reporter,))
        for target in targets
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()
