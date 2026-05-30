from enum import Enum
from typing import List, Optional, Any
from dataclasses import dataclass

# Role 定义消息的角色，这是与大模型沟通的基石
class Role(str, Enum):
    SYSTEM = "system"    # 系统提示词：确立 Agent 的性格与红线
    USER = "user"        # 用户输入 / 工具执行的返回结果 (Observation)
    ASSISTANT = "assistant" # 模型的输出：包含推理(Reasoning)或工具调用(ToolCall)

@dataclass
class ToolCall:
    """ToolCall 代表模型请求调用某个具体的工具"""
    id: str        # 工具调用的唯一 ID
    name: str      # 想要调用的工具名称 (例如 "bash")
    # Arguments 存放 JSON 参数。对应 Go 的 json.RawMessage
    arguments: Any 

@dataclass
class Message:
    """Message 代表上下文中传递的单条消息"""
    role: Role
    content: str = "" # 存放纯文本内容
    # 如果模型决定调用工具，此字段将被填充 (支持并行调用多个工具)
    tool_calls: Optional[List[ToolCall]] = None
    # 如果这是对某个工具调用的响应，此字段必须填写，以告知模型上下文的关联性
    tool_call_id: Optional[str] = None

@dataclass
class ToolResult:
    """ToolResult 代表工具在本地执行完毕后返回的物理结果"""
    tool_call_id: str
    output: str           # 工具执行的控制台输出或报错堆栈
    is_error: bool = False # 标记是否失败，供后续的驾驭工程进行错误自愈

@dataclass
class ToolDefinition:
    """ToolDefinition 描述了一个大模型可以调用的工具元信息 (供模型理解工具有什么用)"""
    name: str
    description: str
    input_schema: Any     # 对应 Go 的 interface{}，通常是 JSON Schema 字典
