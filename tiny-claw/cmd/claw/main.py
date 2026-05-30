import os
import sys
import logging
from typing import List

# 解决 Windows 终端编码问题，确保能输出 Emoji
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 调整 Python 路径以便导入 tiny_claw 模块
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from internal.provider.interface import LLMProvider
from internal.tools.registry import Registry
from internal.schema.message import Message, ToolDefinition, ToolCall, ToolResult, Role
from internal.engine.loop import AgentEngine

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y/%m/%d %H:%M:%S'
)

# ==========================================
# 1. 伪造的大模型 Provider
# ==========================================
class MockProvider(LLMProvider):
    def __init__(self):
        self.turn = 0

    def generate(self, messages: List[Message], available_tools: List[ToolDefinition]) -> Message:
        """模拟大模型的响应：第一轮请求执行 bash，第二轮输出最终结果"""
        self.turn += 1
        if self.turn == 1:
            return Message(
                role=Role.ASSISTANT,
                content="让我来看看当前目录下有什么文件。",
                tool_calls=[
                    ToolCall(id="call_123", name="bash", arguments={"command": "ls -la"})
                ]
            )
        return Message(
            role=Role.ASSISTANT,
            content="我看到了文件列表，里面包含 main.py，任务完成！"
        )

# ==========================================
# 2. 伪造的 Tool Registry
# ==========================================
class MockRegistry(Registry):
    def get_available_tools(self) -> List[ToolDefinition]:
        return []

    def execute(self, call: ToolCall) -> ToolResult:
        """直接返回一段伪造的终端输出"""
        return ToolResult(
            tool_call_id=call.id,
            output="-rw-r--r--  1 user group  234 Oct 24 10:00 main.py\n",
            is_error=False
        )

# ==========================================
# 3. 组装运行
# ==========================================
def main():
    # 获取当前执行目录作为 WorkDir 物理边界
    work_dir = os.getcwd()
    
    p = MockProvider()
    r = MockRegistry()
    
    # 实例化核心引擎
    eng = AgentEngine(p, r, work_dir)
    
    # 发起任务指令
    try:
        eng.run("帮我检查当前目录的文件")
    except Exception as e:
        # 避免在错误消息中使用不支持的字符或处理编码
        try:
            logging.error(f"引擎崩溃: {e}")
        except:
            print(f"Engine crashed with error.")
        sys.exit(1)

if __name__ == "__main__":
    main()
