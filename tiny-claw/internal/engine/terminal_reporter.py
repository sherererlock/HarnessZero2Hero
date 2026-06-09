from __future__ import annotations

from typing import Any

from .reportor import Reporter


class TerminalReporter(Reporter):
    """在终端中直观打印 Agent 状态。"""

    def on_thinking(self) -> None:
        print("\n[TerminalReporter][🤔 思考中] 模型正在推理...")

    def on_tool_call(self, tool_name: str, args: Any) -> None:
        print(f"[TerminalReporter][🛠️ 调用工具] {tool_name}")
        
        display_args = str(args).replace("\n", "\\n").replace("\r", "\\r")
        if len(display_args) > 150:
            display_args = display_args[:150] + "... (已截断)"

        print(f"[TerminalReporter]   参数: {display_args}")

    def on_tool_result(self, tool_name: str, result: str, is_error: bool) -> None:
        if is_error:
            print(f"[TerminalReporter][❌ 执行失败] {tool_name}")
            if result != "":
                print(f"[TerminalReporter]   错误: {result}")
            return

        print(f"[TerminalReporter][✅ 执行成功] {tool_name} {result}")

    def on_message(self, content: str) -> None:
        if content == "":
            print("\n[TerminalReporter][🤖 Agent 回复] 空回复")
            return

        print(f"\n[TerminalReporter][🤖 Agent 回复:\n{content}\n")


def new_terminal_reporter() -> TerminalReporter:
    return TerminalReporter()
