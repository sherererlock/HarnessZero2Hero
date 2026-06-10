from __future__ import annotations

import json
import logging
from dataclasses import replace

from internal.schema.message import Message, Role

logger = logging.getLogger(__name__)


class Compactor:
    """负责监控和压缩上下文内存，防止大模型发生 OOM。"""

    def __init__(self, max_chars: int, retain_last_msgs: int) -> None:
        self.max_chars = max_chars
        self.retain_last_msgs = retain_last_msgs

    def compact(self, msgs: list[Message]) -> list[Message]:
        """压缩消息列表中的远期历史与超长工具输出。"""
        current_length = self.estimate_length(msgs)
        if current_length < self.max_chars:
            return msgs

        logger.warning(
            "[Compactor] 内存告警：当前上下文长度 (%d 字符) 超过阈值 (%d)，触发压缩清理...",
            current_length,
            self.max_chars,
        )

        compacted: list[Message] = []
        protect_start_index = max(0, len(msgs) - self.retain_last_msgs)

        for index, msg in enumerate(msgs):
            if msg.role == Role.SYSTEM:
                compacted.append(msg)
                continue

            new_msg = replace(msg)
            is_in_working_memory = index >= protect_start_index

            if msg.role == Role.USER and msg.tool_call_id:
                if not is_in_working_memory:
                    if len(msg.content) > 200:
                        new_msg.content = (
                            "...[为了节省内存，早期的工具输出已被系统强制清理。"
                            f"原始长度: {len(msg.content)} 字节]..."
                        )
                else:
                    max_keep = 1000
                    if len(msg.content) > max_keep:
                        head = msg.content[:500]
                        tail = msg.content[-500:]
                        new_msg.content = (
                            f"{head}\n\n"
                            f"...[内容过长，中间 {len(msg.content) - max_keep} 字节已被系统截断]...\n\n"
                            f"{tail}"
                        )
            elif msg.role == Role.ASSISTANT and msg.content:
                if not is_in_working_memory and len(msg.content) > 200:
                    new_msg.content = "...[早期的推理思考过程已折叠]..."

            compacted.append(new_msg)

        new_length = self.estimate_length(compacted)
        logger.info(
            "[Compactor] 压缩完成。上下文长度从 %d 降至 %d 字符。",
            current_length,
            new_length,
        )
        return compacted

    def estimate_length(self, msgs: list[Message]) -> int:
        """粗略计算当前上下文总字符数。"""
        total_length = 0
        for msg in msgs:
            total_length += len(msg.content)
            for tool_call in msg.tool_calls or []:
                total_length += len(tool_call.name)
                total_length += len(self._stringify_arguments(tool_call.arguments))
        return total_length

    @staticmethod
    def _stringify_arguments(arguments: object) -> str:
        if arguments is None:
            return ""
        if isinstance(arguments, str):
            return arguments
        try:
            return json.dumps(arguments, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(arguments)


def new_compactor(max_chars: int, retain_last_msgs: int) -> Compactor:
    return Compactor(max_chars=max_chars, retain_last_msgs=retain_last_msgs)
