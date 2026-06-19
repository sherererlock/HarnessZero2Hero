import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Optional
from ..context.composer import PromptComposer
from ..context.compactor import Compactor
from ..context.recovery import RecoveryManager
from ..observability.trace import new_tracer
from ..provider.interface import LLMProvider
from ..tools.registry import Registry
from .reportor import Reporter
from ..schema.message import Message, Role
from .session import Session
from .reminder import ReminderInjector

class AgentEngine:
    """AgentEngine 是微型 OS 的核心驱动"""
    
    def __init__(self, provider: LLMProvider, registry: Registry, enable_thinking: bool = False, PlanMode: bool = None):
        self.provider = provider
        self.registry = registry
        self.PlanMode = PlanMode
        self.compactor = Compactor(max_chars=3000, retain_last_msgs=6)
        self.enable_thinking = enable_thinking
        self.recovery_manager = RecoveryManager()
        self.reminder_injector = ReminderInjector()
        
    def run(self, user_prompt: str, session: Session = None, reporter: Reporter = None) -> Optional[Exception]:
        """Run 启动 Agent 的生命周期"""
        if session is None:
            return ValueError("session 不能为空")

        logging.info(f"[Engine] 引擎启动， 会话：{session.id} 锁定工作区: {session.work_dir}")
        if self.enable_thinking:
            logging.info("[Engine] 慢思考模式已开启")

        prompt_composer = PromptComposer(session.work_dir, self.PlanMode)
        system_prompt = prompt_composer.build()
        session.append(Message(role=Role.USER, content=user_prompt))

        tracer = new_tracer(session.work_dir, session.id)
        root_span = None
        trace_path = None

        try:
            with tracer.span(
                "Agent.Run",
                attributes={
                    "session_id": session.id,
                    "work_dir": session.work_dir,
                },
            ) as root_span:
                turn_count = 0
                # 2. The Main Loop: 心跳开始 (标准的 ReAct 循环)
                while True:
                    turn_count += 1
                    logging.info(f"========== [Turn {turn_count}] 开始 ==========")

                    with tracer.span(
                        f"Turn-{turn_count}",
                        parent=root_span,
                        attributes={"turn_index": turn_count},
                    ) as turn_span:
                        # 获取当前挂载的所有工具定义
                        available_tools = self.registry.get_available_tools()

                        working_memory = session.get_working_memory(6)
                        context_history = [
                            system_prompt
                        ]
                        context_history.extend(working_memory)

                        compactedContext = self.compactor.compact(context_history)
                        turn_span.add_attribute(
                            "context_message_count", len(compactedContext)
                        )

                        if self.enable_thinking:
                            if reporter:
                                reporter.on_thinking()

                            logging.info("[Engine][Phase: 1] 剥夺工具访问权限，强制进入慢思考")
                            try:
                                with tracer.span(
                                    "LLM.Thinking",
                                    parent=turn_span,
                                ) as think_span:
                                    think_resp = self.provider.generate(compactedContext, None)
                                    if think_resp.usage is not None:
                                        think_span.add_attribute(
                                            "prompt_tokens",
                                            think_resp.usage.prompt_tokens,
                                        )
                                        think_span.add_attribute(
                                            "completion_tokens",
                                            think_resp.usage.completion_tokens,
                                        )
                                    if think_resp.content:
                                        logging.info(f"🤖 模型: {think_resp.content}")
                                        compactedContext.append(think_resp)
                                        session.append(think_resp)
                            except Exception as e:
                                return RuntimeError(f"Thinking 阶段生成失败: {e}")

                        # 向大模型发起推理请求 (包含 Reasoning)
                        logging.info("[Engine][Phase: 2] 恢复工具挂载，等待模型采取行动......")

                        try:
                            with tracer.span(
                                "LLM.Action",
                                parent=turn_span,
                                attributes={
                                    "available_tool_count": len(available_tools),
                                },
                            ) as action_span:
                                response_msg = self.provider.generate(
                                    compactedContext, available_tools
                                )
                                if response_msg.usage is not None:
                                    action_span.add_attribute(
                                        "prompt_tokens",
                                        response_msg.usage.prompt_tokens,
                                    )
                                    action_span.add_attribute(
                                        "completion_tokens",
                                        response_msg.usage.completion_tokens,
                                    )
                                action_span.add_attribute(
                                    "tool_call_count", len(response_msg.tool_calls or [])
                                )
                        except Exception as e:
                            return RuntimeError(f"Action 阶段生成失败: {e}")

                        # 将模型的响应完整追加到上下文历史中
                        compactedContext.append(response_msg)
                        session.append(response_msg)

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
                        executed_tool_results: List[Optional[tuple]] = [None] * len(response_msg.tool_calls)

                        def execute_tool(idx: int, call, parent_span) -> None:
                            logging.info("  -> [Worker-%d] 🛠️ 触发并行执行: %s", idx, call.name)
                            if reporter:
                                reporter.on_tool_call(call.name, call.arguments)

                            result = self.registry.execute(call, parent_span=parent_span)
                            executed_tool_results[idx] = (call, result)

                            finalOutput = result.output
                            if result.is_error:
                                finalOutput = self.recovery_manager.analyze_and_inject(call.name, result.output)
                                logging.info("  -> [Worker-%d] 修复后的输出: %s", idx, finalOutput)
                            else:
                                logging.info("  -> [Worker-%d] 工具输出: %s", idx, finalOutput)

                            if reporter:
                                displayOutput = finalOutput
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
                                executor.submit(execute_tool, idx, tool_call, turn_span)
                                for idx, tool_call in enumerate(response_msg.tool_calls)
                            ]
                            for future in futures:
                                future.result()

                        logging.info("[Engine] 所有并发工具执行完毕，开始聚合观察结果 (Observation)...")
                        completed_observations: List[Message] = []
                        for obs in observation_msgs:
                            if obs is not None:
                                compactedContext.append(obs)
                                completed_observations.append(obs)

                        if completed_observations:
                            session.append(*completed_observations)

                        for executed in executed_tool_results:
                            if executed is None:
                                continue

                            tool_call, tool_result = executed
                            reminder_msg = self.reminder_injector.check_and_inject(tool_call, tool_result)
                            if reminder_msg is not None:
                                session.append(reminder_msg)
                                break

                        # 循环回到开头，模型将带着新加入的 Observation 继续它的下一轮思考...

            return None
        finally:
            if root_span is not None:
                trace_path = tracer.export_trace(root_span)
                logging.info("[Tracing] 本次任务执行回放已保存到: %s", trace_path)

    def run_sub(
        self,
        task_prompt: str,
        read_only_registry: Registry,
        reporter: Any = None,
    ) -> str:
        """启动一次性、只读受限的子智能体探索循环。"""
        context_history = [
            Message(
                role=Role.SYSTEM,
                content=(
                    "你是一个专门负责深度探索的探路者 (Explorer Subagent)。\n"
                    "你的任务是根据主架构师的指令，在当前工作区内仔细阅读代码、查阅日志，搜集足够的信息。\n"
                    "【核心纪律】\n"
                    "1. 你必须、且只能依靠内置工具（如 bash 的 find/grep，或 read_file）去寻找答案。绝对不允许凭空捏造或猜测！\n"
                    "2. 如果你没有找到确切的答案，你必须继续使用工具深入搜索。\n"
                    "3. 当且仅当你找到了确切的线索后，停止调用工具，直接输出一段纯文本作为你的终极汇报。主架构师会根据你的汇报来做下一步决策。"
                ),
            ),
            Message(role=Role.USER, content=task_prompt),
        ]

        max_sub_turns = 10
        turn_count = 0

        while True:
            turn_count += 1
            if turn_count > max_sub_turns:
                raise RuntimeError(
                    f"子智能体探索过于深入，超过 {max_sub_turns} 轮被强制召回，请主 Agent 给它更明确的指令"
                )

            available_tools = read_only_registry.get_available_tools()
            compacted_context = self.compactor.compact(context_history)

            try:
                action_resp = self.provider.generate(compacted_context, available_tools)
            except Exception as exc:
                raise RuntimeError(f"子智能体推理失败: {exc}") from exc

            context_history.append(action_resp)

            if not action_resp.tool_calls:
                return action_resp.content

            logging.info(
                "[Engine][Subagent] 模型请求并发调用 %d 个只读工具...",
                len(action_resp.tool_calls),
            )
            observation_msgs: List[Optional[Message]] = [None] * len(action_resp.tool_calls)

            def execute_tool(idx: int, call) -> None:
                if reporter is not None:
                    reporter.on_tool_call(f"[Subagent] {call.name}", call.arguments)

                result = read_only_registry.execute(call)
                final_output = result.output
                if result.is_error:
                    final_output = self.recovery_manager.analyze_and_inject(
                        call.name, result.output
                    )

                if reporter is not None:
                    display_output = final_output
                    if len(display_output) > 200:
                        display_output = display_output[:200] + "... (已截断)"

                    reporter.on_tool_result(
                        f"[Subagent] {call.name}",
                        display_output,
                        result.is_error,
                    )

                observation_msgs[idx] = Message(
                    role=Role.USER,
                    content=final_output,
                    tool_call_id=call.id,
                )

            with ThreadPoolExecutor(max_workers=len(action_resp.tool_calls)) as executor:
                futures = [
                    executor.submit(execute_tool, idx, tool_call)
                    for idx, tool_call in enumerate(action_resp.tool_calls)
                ]
                for future in futures:
                    future.result()

            for obs in observation_msgs:
                if obs is not None:
                    context_history.append(obs)
