from abc import ABC, abstractmethod
from typing import Any


class Reporter(ABC):
    """定义 Agent 引擎向外界输出信息的规范。"""

    @abstractmethod
    def on_thinking(self) -> None:
        """当模型开始进行慢思考 (reasoning) 时调用。"""

    @abstractmethod
    def on_tool_call(self, tool_name: str, args: str) -> None:
        """当模型决定调用工具时调用。"""

    @abstractmethod
    def on_tool_result(
        self, tool_name: str, result: str, is_error: bool
    ) -> None:
        """当工具执行完毕并返回结果时调用。"""

    @abstractmethod
    def on_message(self, content: str) -> None:
        """当模型输出最终回答时调用。"""
