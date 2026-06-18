import logging
from typing import Any, Protocol

from ..schema.message import ToolDefinition
from .registry import BaseTool, Registry


class AgentRunner(Protocol):
    """打破 tools 与 engine 间循环依赖的子智能体运行抽象。"""

    def run_sub(
        self,
        task_prompt: str,
        read_only_registry: Registry,
        reporter: Any,
    ) -> str:
        """启动一个匿名子智能体，并返回最终的纯文本总结。"""


class SubagentTool(BaseTool):
    """派出只读子智能体做深度探索，再回收摘要报告。"""

    def __init__(
        self,
        runner: AgentRunner,
        read_only_registry: Registry,
        reporter: Any,
    ):
        self.runner = runner
        self.read_only_registry = read_only_registry
        self.reporter = reporter

    def name(self) -> str:
        return "spawn_subagent"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description=(
                "派出一个专门用于深度探索的子智能体。"
                "当你需要阅读大量代码、跨文件查找逻辑时请调用此工具。"
                "它在探索完毕后，会给你返回一份极度精炼的摘要报告。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "task_prompt": {
                        "type": "string",
                        "description": "给子智能体下达的明确指令。",
                    }
                },
                "required": ["task_prompt"],
            },
        )

    def execute(self, args: Any) -> str:
        task_prompt = self._extract_task_prompt(args)
        logging.info(
            "[Subagent] 主 Agent 发起委派！正在拉起探路者: [%s]...",
            task_prompt,
        )

        try:
            summary = self._run_subagent(task_prompt)
        except Exception as exc:
            return f"子智能体执行失败: {exc}"

        logging.info("[Subagent] 子智能体任务结束。报告返回给主干...")
        return f"【子智能体探索报告】:\n{summary}"

    def _extract_task_prompt(self, args: Any) -> str:
        if not isinstance(args, dict):
            raise ValueError("参数解析失败: 参数必须是包含 task_prompt 的对象")

        task_prompt = args.get("task_prompt")
        if not isinstance(task_prompt, str) or not task_prompt:
            raise ValueError("参数解析失败: task_prompt 必须是非空字符串")

        return task_prompt

    def _run_subagent(self, task_prompt: str) -> str:
        run_sub = getattr(self.runner, "run_sub", None)
        if callable(run_sub):
            return run_sub(task_prompt, self.read_only_registry, self.reporter)

        run_sub_pascal = getattr(self.runner, "RunSub", None)
        if callable(run_sub_pascal):
            return run_sub_pascal(task_prompt, self.read_only_registry, self.reporter)

        raise RuntimeError("runner 未实现 run_sub / RunSub")


def new_subagent_tool(
    runner: AgentRunner,
    read_only_registry: Registry,
    reporter: Any,
) -> SubagentTool:
    return SubagentTool(runner, read_only_registry, reporter)


NewSubagentTool = new_subagent_tool
