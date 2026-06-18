import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Tuple
from ..schema.message import ToolDefinition, ToolCall, ToolResult


# MiddlewareFunc 定义全局中间件签名：
# 接收当前 ToolCall，返回是否放行以及拦截原因。
MiddlewareFunc = Callable[[ToolCall], Tuple[bool, str]]


class BaseTool(ABC):
    """BaseTool 定义所有具体工具都要实现的通用接口。"""

    @abstractmethod
    def name(self) -> str:
        """返回工具的全局唯一名称，供模型调用。"""
        pass

    @abstractmethod
    def definition(self) -> ToolDefinition:
        """返回提交给模型的工具元信息和参数 Schema。"""
        pass

    @abstractmethod
    def execute(self, args: Any) -> str:
        """接收模型给出的参数并执行具体业务逻辑。"""
        pass

class Registry(ABC):
    """Registry 定义工具的注册与分发接口。"""

    @abstractmethod
    def register(self, tool: BaseTool) -> None:
        """挂载一个新的工具到系统中。"""
        pass

    @abstractmethod
    def use(self, middleware: MiddlewareFunc) -> None:
        """挂载一个全局中间件，在工具执行前依次运行。"""
        pass

    @abstractmethod
    def get_available_tools(self) -> List[ToolDefinition]:
        """返回当前系统挂载的所有工具 Schema。"""
        pass

    @abstractmethod
    def execute(self, call: ToolCall) -> ToolResult:
        """实际路由并执行模型请求的工具调用。"""
        pass


class ToolRegistry(Registry):
    """Registry 的默认实现，使用工具名做 O(1) 路由查找。"""

    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.middlewares: List[MiddlewareFunc] = []

    def register(self, tool: BaseTool) -> None:
        name = tool.name()
        if name in self.tools:
            logging.warning("工具 '%s' 已经被注册，将被覆盖。", name)
        self.tools[name] = tool
        logging.info("[Registry] 成功挂载工具: %s", name)

    def use(self, middleware: MiddlewareFunc) -> None:
        self.middlewares.append(middleware)

    def get_available_tools(self) -> List[ToolDefinition]:
        return [tool.definition() for tool in self.tools.values()]

    def execute(self, call: ToolCall) -> ToolResult:
        tool = self.tools.get(call.name)
        if tool is None:
            return ToolResult(
                tool_call_id=call.id,
                output=f"Error: 系统中不存在名为 '{call.name}' 的工具。",
                is_error=True,
            )

        for middleware in self.middlewares:
            allowed, reason = middleware(call)
            if not allowed:
                logging.warning(
                    "[Registry] 工具 %s 被 Middleware 拦截: %s",
                    call.name,
                    reason,
                )
                return ToolResult(
                    tool_call_id=call.id,
                    output=f"执行被系统拦截。原因: {reason}",
                    is_error=True,
                )

        try:
            output = tool.execute(call.arguments)
        except Exception as exc:
            logging.error(f"[Registry] ❌  工具调用失败: {call.name} - {exc}")
            return ToolResult(
                tool_call_id=call.id,
                output=f"Error executing {call.name}: {exc}",
                is_error=True,
            )

        return ToolResult(
            tool_call_id=call.id,
            output=output,
            is_error=False,
        )


def new_registry() -> Registry:
    return ToolRegistry()


NewRegistry = new_registry
