import logging
import os

from common import (
    build_engine,
    configure_logging,
    new_bash_tool,
    new_edit_file_tool,
    new_read_file_tool,
    new_write_file_tool,
)
from internal.provider.env_loader import _candidate_env_paths, _read_env_value


def _resolve_env_value(name: str, start_dirs: list[str] | None = None) -> str | None:
    env_value = os.getenv(name)
    if env_value:
        return env_value

    search_dirs = start_dirs if start_dirs is not None else [os.getcwd(), os.path.dirname(__file__)]
    seen_paths = set()
    for start_dir in search_dirs:
        for env_path in _candidate_env_paths(start_dir):
            if env_path in seen_paths:
                continue
            seen_paths.add(env_path)

            value = _read_env_value(env_path, name)
            if value:
                return value
    return None


def validate_required_env_vars(start_dirs: list[str] | None = None) -> None:
    required = ["ZHIPU_API_KEY", "FEISHU_APP_ID", "FEISHU_APP_SECRET"]
    missing = []
    for name in required:
        value = _resolve_env_value(name, start_dirs=start_dirs)
        if not value:
            missing.append(name)
            continue
        os.environ.setdefault(name, value)

    if missing:
        raise RuntimeError("请先设置环境变量: " + ", ".join(missing))


def main() -> None:
    from internal.feishu.bot import new_feishu_bot

    configure_logging()
    validate_required_env_vars()
    engine = build_engine(
        tool_factories=[
            new_read_file_tool,
            new_write_file_tool,
            new_bash_tool,
            new_edit_file_tool,
        ],
        enable_thinking=True,
    )
    bot = new_feishu_bot(engine)
    logging.info("go-tiny-claw 飞书长连接模式启动中")
    bot.start_websocket()


if __name__ == "__main__":
    main()
