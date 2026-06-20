import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../.."))
CLAW_CMD_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../claw"))

for path in (PROJECT_ROOT, CLAW_CMD_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from common import configure_logging, require_env_vars
from internal.eval.benchmark import TestCase, new_benchmark_runner


def main() -> None:
    configure_logging()
    require_env_vars(("ZHIPU_API_KEY",))

    testcases = [
        TestCase(
            id="test_001_edit",
            name="测试模糊替换工具的准确性",
            setup_script="""echo '{"name": "tiny-claw", "version": "v1.0.0"}' > config.json""",
            task_prompt=(
                "当前目录下有一个 config.json。请你使用 edit_file 工具，"
                "将其中的 version 从 v1.0.0 改为 v2.0.0。不要做其他多余操作。"
            ),
            validate_script="""grep '"version": "v2.0.0"' config.json""",
        ),
        TestCase(
            id="test_002_code_gen",
            name="测试代码阅读与创建新文件的综合能力",
            setup_script=(
                "cat <<'EOF' > calculator.py\n"
                "def multiply(a, b):\n"
                "    return a * b\n"
                "EOF"
            ),
            task_prompt=(
                "当前目录下有一个 calculator.py。请你仔细阅读它，然后在同级目录下，"
                "帮我写一个规范的单元测试文件 test_calculator.py，用来测试 multiply 函数。测试时用python3运行。"
                "请务必包含正常的测试用例。"
            ),
            validate_script="python3 -m unittest -v",
        ),
    ]

    runner = new_benchmark_runner("xiaomi/mimo-v2.5")
    runner.run_suite(testcases)


if __name__ == "__main__":
    main()
