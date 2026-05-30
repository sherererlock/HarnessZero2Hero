from abc import ABC, abstractmethod
from typing import List
from ..schema.message import Message, ToolDefinition

class LLMProvider(ABC):
    """LLMProvider 定义了与大模型通信的统一契约"""

    @abstractmethod
    def generate(
        self, 
        messages: List[Message], 
        available_tools: List[ToolDefinition]
    ) -> Message:
        """Generate 接收当前的上下文历史、可用工具列表，并发起一次大模型推理"""
        pass
