import os
from pathlib import Path
from typing import Iterable, Optional


def _candidate_env_paths(start_dir: str) -> Iterable[Path]:
    current = Path(start_dir).resolve()
    if current.is_file():
        current = current.parent

    for directory in (current, *current.parents):
        yield directory / ".env"


def _read_env_value(env_path: Path, key: str) -> Optional[str]:
    if not env_path.is_file():
        return None

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        name, value = stripped.split("=", 1)
        if name.strip() != key:
            continue

        return value.strip().strip('"').strip("'")

    return None


def resolve_api_key(
    explicit_api_key: Optional[str] = None,
    env_var_name: str = "ZHIPU_API_KEY",
    start_dirs: Optional[list[str]] = None,
) -> Optional[str]:
    if explicit_api_key:
        return explicit_api_key

    env_value = os.getenv(env_var_name)
    if env_value:
        return env_value

    search_dirs = start_dirs or [os.getcwd(), Path(__file__).resolve().parent]
    seen_paths: set[Path] = set()
    for start_dir in search_dirs:
        for env_path in _candidate_env_paths(start_dir):
            if env_path in seen_paths:
                continue
            seen_paths.add(env_path)

            value = _read_env_value(env_path, env_var_name)
            if value:
                return value

    return None
