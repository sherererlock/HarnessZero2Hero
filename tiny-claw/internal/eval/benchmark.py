from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from ..engine.loop import AgentEngine
from ..engine.session import Session, new_session
from ..observability.tracker import new_cost_tracker
from ..provider.openai import new_zhipu_openai_provider
from ..tools.Bash import new_bash_tool
from ..tools.edit_file import new_edit_file_tool
from ..tools.readfile import new_read_file_tool
from ..tools.registry import new_registry
from ..tools.write import new_write_file_tool


@dataclass(slots=True)
class TestCase:
    """定义一个需要 Agent 去完成并验证的独立任务。"""

    id: str
    name: str
    setup_script: str = ""
    task_prompt: str = ""
    validate_script: str = ""
    max_turns: int = 0


@dataclass(slots=True)
class TestResult:
    """存放单次跑分结果。"""

    test_case_id: str
    passed: bool
    total_cost_cny: float = 0.0
    duration_ms: int = 0
    error_msg: str = ""

    @property
    def total_cost_usd(self) -> float:
        # 兼容原 Go 草稿里的字段名。
        return self.total_cost_cny


class BenchmarkRunner:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def run_suite(self, testcases: list[TestCase]) -> list[TestResult]:
        """执行一组评测集，并返回跑分结果。"""
        logging.info("==================================================")
        logging.info("启动自动化 Harness Benchmark 评估... | 模型: %s", self.model_name)
        logging.info("==================================================")

        results: list[TestResult] = []
        passed_count = 0
        total_cost = 0.0

        for test_case in testcases:
            logging.info("\n>>> 正在执行用例 [%s]: %s", test_case.id, test_case.name)
            result = self._run_single_test(test_case)
            results.append(result)

            if result.passed:
                passed_count += 1
                logging.info(
                    ">>> 用例 [%s] 测试通过! | 耗时: %dms | 花费: $%.6f",
                    test_case.id,
                    result.duration_ms,
                    result.total_cost_cny,
                )
            else:
                logging.error(
                    ">>> 用例 [%s] 测试失败! | 错误: %s",
                    test_case.id,
                    result.error_msg,
                )

            total_cost += result.total_cost_cny

        success_rate = 0.0
        if testcases:
            success_rate = passed_count / len(testcases) * 100

        logging.info("\n================ 跑分终极报告 ================")
        logging.info(
            "总用例数: %d | 成功数: %d | 成功率: %.2f%%",
            len(testcases),
            passed_count,
            success_rate,
        )
        logging.info("总消耗成本: $%.6f", total_cost)
        logging.info("==================================================")
        return results

    def _run_single_test(self, test_case: TestCase) -> TestResult:
        start_time = time.perf_counter()
        work_dir = self._prepare_work_dir(test_case.id)

        if test_case.setup_script:
            setup_result = self._run_bash_script(test_case.setup_script, cwd=work_dir)
            if setup_result.returncode != 0:
                return TestResult(
                    test_case_id=test_case.id,
                    passed=False,
                    error_msg=f"靶机 Setup 失败: {self._combined_output(setup_result)}",
                    duration_ms=self._elapsed_ms(start_time),
                )

        session = new_session(test_case.id, str(work_dir))
        engine = self._build_engine(str(work_dir), session)
        err = engine.run(test_case.task_prompt, session=session, reporter=None)
        if err is not None:
            return TestResult(
                test_case_id=test_case.id,
                passed=False,
                total_cost_cny=session.total_cost_cny,
                duration_ms=self._elapsed_ms(start_time),
                error_msg=f"Agent 崩溃: {err}",
            )

        validate_result = self._run_bash_script(test_case.validate_script, cwd=work_dir)
        duration_ms = self._elapsed_ms(start_time)
        if validate_result.returncode != 0:
            return TestResult(
                test_case_id=test_case.id,
                passed=False,
                total_cost_cny=session.total_cost_cny,
                duration_ms=duration_ms,
                error_msg=f"验证脚本执行失败: {self._combined_output(validate_result)}",
            )

        return TestResult(
            test_case_id=test_case.id,
            passed=True,
            total_cost_cny=session.total_cost_cny,
            duration_ms=duration_ms,
        )

    def _build_engine(self, work_dir: str, session: Session) -> AgentEngine:
        real_provider = new_zhipu_openai_provider(self.model_name)
        tracked_provider = new_cost_tracker(real_provider, self.model_name, session)

        registry = new_registry()
        registry.register(new_read_file_tool(work_dir))
        registry.register(new_write_file_tool(work_dir))
        registry.register(new_bash_tool(work_dir))
        registry.register(new_edit_file_tool(work_dir))

        return AgentEngine(
            provider=tracked_provider,
            registry=registry,
            enable_thinking=False,
            PlanMode=False,
        )

    def _prepare_work_dir(self, test_case_id: str) -> Path:
        workspace_root = Path(os.getcwd()) / "workspace"
        work_dir = workspace_root / f"{test_case_id}_{time.time_ns()}"
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

    def _run_bash_script(self, script: str, cwd: Path) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(
                ["bash", "-lc", script],
                cwd=str(cwd),
                capture_output=True,
                text=False,
                check=False,
            )
        except OSError as exc:
            return subprocess.CompletedProcess(
                args=["bash", "-lc", script],
                returncode=1,
                stdout=b"",
                stderr=str(exc).encode("utf-8", errors="replace"),
            )

    def _combined_output(self, result: subprocess.CompletedProcess[bytes]) -> str:
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        output = f"{stdout}{stderr}".strip()
        return output or "无终端输出"

    def _elapsed_ms(self, start_time: float) -> int:
        return int((time.perf_counter() - start_time) * 1000)

    RunSuite = run_suite


def new_benchmark_runner(model: str) -> BenchmarkRunner:
    return BenchmarkRunner(model_name=model)


NewBenchmarkRunner = new_benchmark_runner
