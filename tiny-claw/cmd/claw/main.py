import os
import sys
import logging
import json
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
# 1. 升级版 Mock Provider
# ==========================================
class MockProvider(LLMProvider):
    def __init__(self):
        self.turn = 0

    def generate(self, messages: List[Message], available_tools: List[ToolDefinition]) -> Message:
        # 如果工具列表为空，说明这是引擎发起的 Phase 1: Thinking 阶段
        if not available_tools:
            return Message(
                role=Role.ASSISTANT,
                content="【推理中】目标是检查文件。我不能直接盲猜，我需要先调用 bash 工具执行 ls 命令，看看当前目录下有什么，然后再做定夺。"
            )
        
        # 如果工具列表不为空，说明这是 Phase 2: Action 阶段
        self.turn += 1
        if self.turn == 1:
            # 第一轮 Action：顺着刚才的 Thinking，精准调用工具
            return Message(
                role=Role.ASSISTANT,
                content="我要执行我刚才计划的步骤了。",
                tool_calls=[
                    ToolCall(id="call_123", name="bash", arguments={"command": "ls -la"})
                ]
            )
        
        # 第二轮 Action：直接总结退出
        return Message(
            role=Role.ASSISTANT,
            content="根据工具返回的结果，我看到了 main.py，任务圆满完成！"
        )

# ==========================================
# 2. 升级版 Mock Registry
# ==========================================
class MockRegistry(Registry):
    def get_available_tools(self) -> List[ToolDefinition]:
        # 为了让 Phase 2 能检测到工具，这里返回一个伪造的工具定义数组
        return [ToolDefinition(name="bash", description="Execute bash commands", input_schema={})]

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
    
    # 实例化核心引擎，开启 enable_thinking = True
    eng = AgentEngine(p, r, work_dir, enable_thinking=True)
    
    # 发起任务指令
    try:
        eng.run("帮我检查当前目录的文件")
    except Exception as e:
        try:
            logging.error(f"引擎崩溃: {e}")
        except:
            print(f"Engine crashed with error.")
        sys.exit(1)

if __name__ == "__main__":
    main()
