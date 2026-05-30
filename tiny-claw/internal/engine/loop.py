import logging
from typing import List
from ..provider.interface import LLMProvider
from ..tools.registry import Registry
from ..schema.message import Message, Role

class AgentEngine:
    """AgentEngine 是微型 OS 的核心驱动"""
    
    def __init__(self, provider: LLMProvider, registry: Registry, work_dir: str):
        self.provider = provider
        self.registry = registry
        # WorkDir (工作区): 借鉴 OpenClaw 的理念，Agent 必须有一个明确的物理边界
        self.work_dir = work_dir

    def run(self, user_prompt: str) -> None:
        """Run 启动 Agent 的生命周期"""
        logging.info(f"[Engine] 引擎启动，锁定工作区: {self.work_dir}")
        
        # 1. 初始化会话的 Context (上下文内存)
        # 在真实的场景中，这里会由动态 Prompt 组装器加载 AGENTS.md。目前我们先硬编码。
        context_history: List[Message] = [
            Message(
                role=Role.SYSTEM,
                content="You are go-tiny-claw, an expert coding assistant. You have full access to tools in the workspace."
            ),
            Message(
                role=Role.USER,
                content=user_prompt
            )
        ]
        
        turn_count = 0
        # 2. The Main Loop: 心跳开始 (标准的 ReAct 循环)
        while True:
            turn_count += 1
            logging.info(f"========== [Turn {turn_count}] 开始 ==========")
            
            # 获取当前挂载的所有工具定义
            available_tools = self.registry.get_available_tools()
            
            # 向大模型发起推理请求 (包含 Reasoning)
            logging.info("[Engine] 正在思考 (Reasoning)...")
            try:
                # 注意：Python 中不需要显式传递 context，除非有特殊需求
                response_msg = self.provider.generate(context_history, available_tools)
            except Exception as e:
                raise RuntimeError(f"模型生成失败: {e}")

            # 将模型的响应完整追加到上下文历史中
            context_history.append(response_msg)
            
            # 如果模型回复了纯文本，打印出来 (这通常是它的思考过程，或是最终结果)
            if response_msg.content:
                print(f"🤖 模型: {response_msg.content}")
                
            # 3. 退出条件判断
            # 如果模型没有请求任何工具调用，说明它认为任务已经完成，跳出循环。
            if not response_msg.tool_calls:
                logging.info("[Engine] 任务完成，退出循环。")
                break
                
            # 4. 执行行动 (Action) 与 获取观察结果 (Observation)
            logging.info(f"[Engine] 模型请求调用 {len(response_msg.tool_calls)} 个工具...")
            for tool_call in response_msg.tool_calls:
                logging.info(f"  -> 🛠️ 执行工具: {tool_call.name}, 参数: {tool_call.arguments}")
                
                # 通过 Registry 路由并执行底层工具
                result = self.registry.execute(tool_call)
                
                if result.is_error:
                    logging.info(f"  -> ❌ 工具执行报错: {result.output}")
                else:
                    logging.info(f"  -> ✅ 工具执行成功 (返回 {len(result.output)} 字节)")
                    
                # 将工具执行的观察结果 (Observation) 封装为 User Message 追加到上下文中
                # 注意：ToolCallID 必须携带！这是维系大模型推理链条的关键
                observation_msg = Message(
                    role=Role.USER,
                    content=result.output,
                    tool_call_id=tool_call.id
                )
                context_history.append(observation_msg)
            
            # 循环回到开头，模型将带着新加入的 Observation 继续它的下一轮思考...
