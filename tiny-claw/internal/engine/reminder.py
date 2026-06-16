from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from ..schema.message import Message, Role, ToolCall, ToolResult

logger = logging.getLogger(__name__)


class ReminderInjector:
    """在模型重复失败时注入强力提醒，打断死循环。"""

    def __init__(self) -> None:
        self.consecutive_failures: dict[str, int] = {}

    def check_and_inject(self, last_tool_call: ToolCall, last_result: ToolResult) -> Optional[Message]:
        """根据本轮工具执行结果决定是否追加提醒消息。"""
        fingerprint = generate_fingerprint(last_tool_call.name, last_tool_call.arguments)

        if not last_result.is_error:
            self.consecutive_failures = {}
            return None

        fail_count = self.consecutive_failures.get(fingerprint, 0) + 1
        self.consecutive_failures[fingerprint] = fail_count
        logger.info(
            "[Reminder] 监控到工具 %s 执行失败，该参数特征连续失败次数: %d",
            last_tool_call.name,
            fail_count,
        )

        if fail_count < 3:
            return None

        logger.warning("[Reminder] 触发死循环干预！注入强力修正指令。")
        nudge_msg = (
            "[SYSTEM REMINDER 警告]\n"
            f"你似乎陷入了死循环。你刚刚连续 {fail_count} 次使用相同的参数调用了 "
            f"'{last_tool_call.name}' 工具，并且都失败了。\n"
            "请立即停止这种无效的重试！你的注意力被当前的报错过度吸引了。\n"
            "你需要：\n"
            "1. 停止猜测参数。跳出当前的局部思维。\n"
            "2. 彻底改变你的策略。\n"
            "3. 如果你确实无法通过系统工具解决当前问题，请直接结束任务并向用户说明你需要什么人工帮助，"
            "而不是继续盲目消耗 API 资源尝试。"
        )
        return Message(role=Role.USER, content=nudge_msg)


def generate_fingerprint(tool_name: str, args: Any) -> str:
    """为工具名和参数生成稳定指纹，用于识别重复失败。"""
    hasher = hashlib.md5()
    hasher.update(tool_name.encode("utf-8"))
    hasher.update(_normalize_args(args))
    return hasher.hexdigest()


def _normalize_args(args: Any) -> bytes:
    if args is None:
        return b""
    if isinstance(args, bytes):
        return args
    if isinstance(args, str):
        return args.encode("utf-8")
    try:
        return json.dumps(args, ensure_ascii=False, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError):
        return str(args).encode("utf-8")


def new_reminder_injector() -> ReminderInjector:
    return ReminderInjector()
