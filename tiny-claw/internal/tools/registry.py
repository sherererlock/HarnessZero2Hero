from abc import ABC, abstractmethod
from typing import List
from ..schema.message import ToolDefinition, ToolCall, ToolResult

class Registry(ABC):
    """Registry 定义了工具的注册与分发执行接口"""

    @abstractmethod
    def get_available_tools(self) -> List[ToolDefinition]:
        """GetAvailableTools 返回当前系统挂载的所有可用工具的 Schema"""
        pass

    @abstractmethod
    def execute(self, call: ToolCall) -> ToolResult:
        """Execute 实际执行模型请求的工具，并返回结果"""
        pass
