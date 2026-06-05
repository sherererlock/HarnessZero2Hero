import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from ..provider.interface import LLMProvider
from ..tools.registry import Registry
from .reportor import Reporter
from ..schema.message import Message, Role

class AgentEngine:
    """AgentEngine 是微型 OS 的核心驱动"""
    
    def __init__(self, provider: LLMProvider, registry: Registry, work_dir: str, enable_thinking: bool = False):
        self.provider = provider
        self.registry = registry
        # WorkDir (工作区): 借鉴 OpenClaw 的理念，Agent 必须有一个明确的物理边界
        self.work_dir = work_dir
        self.enable_thinking = enable_thinking
        
    def run(self, user_prompt: str, reporter: Reporter = None) -> Optional[Exception]:
        """Run 启动 Agent 的生命周期"""
        logging.info(f"[Engine] 引擎启动，锁定工作区: {self.work_dir}")
        if self.enable_thinking:
            logging.info("[Engine] 慢思考模式已开启")
        
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

            if self.enable_thinking:
                if reporter:
                    reporter.on_thinking()

                logging.info("[Engine][Phase: 1] 剥夺工具访问权限，强制进入慢思考")
                try:
                    think_resp = self.provider.generate(context_history, None)
                    if think_resp.content:
                        logging.info(f"🤖 模型: {think_resp.content}")
                        context_history.append(think_resp)
                except Exception as e:
                    return RuntimeError(f"Thinking 阶段生成失败: {e}")

            # 向大模型发起推理请求 (包含 Reasoning)
            logging.info("[Engine][Phase: 2] 恢复工具挂载，等待模型采取行动......")

            try:
                # 注意：Python 中不需要显式传递 context，除非有特殊需求
                response_msg = self.provider.generate(context_history, available_tools)
            except Exception as e:
                return RuntimeError(f"Action 阶段生成失败: {e}")

            # 将模型的响应完整追加到上下文历史中
            context_history.append(response_msg)

            if response_msg.content != "" and reporter is not None:
                reporter.on_message(response_msg.content)
            
            # 如果模型回复了纯文本，打印出来 (这通常是它的思考过程，或是最终结果)
            if response_msg.content:
                logging.info(f"🤖 模型: {response_msg.content}")
                
            # 3. 退出条件判断
            # 如果模型没有请求任何工具调用，说明它认为任务已经完成，跳出循环。
            if not response_msg.tool_calls:
                logging.info("[Engine] 任务完成，退出循环。")
                break
                
            # 4. 执行行动 (Action) 与 获取观察结果 (Observation)
            logging.info("[Engine] 模型请求并发调用 %d 个工具...", len(response_msg.tool_calls))
            
            observation_msgs: List[Optional[Message]] = [None] * len(response_msg.tool_calls)

            def execute_tool(idx: int, call) -> None:
                logging.info("  -> [Worker-%d] 🛠️ 触发并行执行: %s", idx, call.name)
                if reporter:
                    reporter.on_tool_call(call.name, call.arguments)

                result = self.registry.execute(call)
                if reporter:
                    displayOutput = result.output
                    if len(displayOutput) > 200:
                        displayOutput = displayOutput[:200] + "...(已截断，实际长度: %d)" % len(displayOutput)

                    reporter.on_tool_result(call.name, displayOutput, result.is_error)

                if result.is_error:
                    logging.error("  -> [Worker-%d] ❌ 工具执行报错: %s", idx, result.output)
                else:
                    logging.info("  -> [Worker-%d] ✅ 工具执行成功 (返回 %d 字节)", idx, len(result.output))

                observation_msgs[idx] = Message(
                    role=Role.USER,
                    content=result.output,
                    tool_call_id=call.id,
                )

            with ThreadPoolExecutor(max_workers=len(response_msg.tool_calls)) as executor:
                futures = [
                    executor.submit(execute_tool, idx, tool_call)
                    for idx, tool_call in enumerate(response_msg.tool_calls)
                ]
                for future in futures:
                    future.result()

            logging.info("[Engine] 所有并发工具执行完毕，开始聚合观察结果 (Observation)...")
            for obs in observation_msgs:
                if obs is not None:
                    context_history.append(obs)

            # 循环回到开头，模型将带着新加入的 Observation 继续它的下一轮思考...

        return None
