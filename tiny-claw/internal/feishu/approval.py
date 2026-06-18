from __future__ import annotations

import json
import logging
import queue
import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ApprovalResult:
    """审批结果包。"""

    allowed: bool
    reason: str


@dataclass
class PendingApprovalTask:
    """记录待审批任务的上下文，便于回调后更新原卡片。"""

    channel: "queue.Queue[ApprovalResult]"
    tool_name: str
    args: Any


class ApprovalManager:
    """统一管理当前正在等待人类审批的任务。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.pending_tasks: Dict[str, PendingApprovalTask] = {}

    def wait_for_approval(
        self,
        task_id: str,
        tool_name: str,
        args: Any,
        reporter: Optional[Any],
    ) -> tuple[bool, str]:
        """
        发送飞书通知，并阻塞当前线程，直到 webhook 或其他回调给出审批结果。
        """
        ch: queue.Queue[ApprovalResult] = queue.Queue(maxsize=1)
        with self._lock:
            self.pending_tasks[task_id] = PendingApprovalTask(
                channel=ch,
                tool_name=tool_name,
                args=args,
            )

        notice_msg = (
            "⚠️ 高危操作审批请求\n"
            "Agent 试图执行以下动作:\n"
            f"- 工具: {tool_name}\n"
            f"- 参数: {self._format_args(args)}\n"
            f"任务 ID: {task_id}\n"
            f'👉 如当前环境不支持交互卡片，请回复 "approve {task_id}" 或 "reject {task_id}"。'
        )
        notice_card = self._build_notice_card(task_id, tool_name, args)

        try:
            self._send_notice(notice_msg, notice_card, task_id, reporter)
            logging.info("[Approval] 已发送审批请求 (TaskID: %s)，线程挂起等待...", task_id)

            # 驾驭核心：阻塞等待外部回调把审批结果塞回来。
            result = ch.get()
            return result.allowed, result.reason
        finally:
            with self._lock:
                self.pending_tasks.pop(task_id, None)

    def resolve_approval(self, task_id: str, allowed: bool, reason: str) -> None:
        """由飞书 Webhook 回调触发，向等待队列发送审批结果。"""
        with self._lock:
            pending = self.pending_tasks.get(task_id)

        if pending is None:
            logging.info("[Approval] 找不到对应的 TaskID: %s，可能已超时或处理完毕", task_id)
            return

        logging.info(
            "[Approval] 收到来自飞书的审批结果 (TaskID: %s, Allowed: %s)",
            task_id,
            allowed,
        )
        pending.channel.put(ApprovalResult(allowed=allowed, reason=reason))

    def get_pending_task(self, task_id: str) -> Optional[PendingApprovalTask]:
        with self._lock:
            return self.pending_tasks.get(task_id)

    def _send_notice(
        self,
        notice_msg: str,
        notice_card: Dict[str, Any],
        task_id: str,
        reporter: Optional[Any],
    ) -> None:
        if reporter is not None:
            send_card = getattr(reporter, "send_interactive_card", None)
            if callable(send_card):
                send_card(notice_card)
                return

            send_msg = getattr(reporter, "send_msg", None) or getattr(reporter, "sendMsg", None)
            if callable(send_msg):
                send_msg(notice_msg)
                return

        # 回退到终端打印，兼容本地 CLI 模式。
        print(f"\n\033[31m[需要审批 TaskID: {task_id}]\033[0m {notice_msg}")

    @staticmethod
    def _format_args(args: Any) -> str:
        if isinstance(args, str):
            return args
        try:
            return json.dumps(args, ensure_ascii=False)
        except TypeError:
            return str(args)

    @classmethod
    def _build_notice_card(cls, task_id: str, tool_name: str, args: Any) -> Dict[str, Any]:
        formatted_args = cls._truncate_text(cls._format_args(args), limit=500)
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "高危操作审批请求",
                },
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        "**Agent** 试图执行高危操作，请确认是否放行。\n"
                        f"**工具**：`{tool_name}`\n"
                        f"**任务 ID**：`{task_id}`"
                    ),
                },
                {
                    "tag": "hr",
                },
                {
                    "tag": "markdown",
                    "content": f"**参数**：\n```json\n{formatted_args}\n```",
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "批准",
                            },
                            "type": "primary",
                            "value": {
                                "action": "approve",
                                "task_id": task_id,
                            },
                            "confirm": {
                                "title": {
                                    "tag": "plain_text",
                                    "content": "确认批准",
                                },
                                "text": {
                                    "tag": "plain_text",
                                    "content": f"确认允许任务 {task_id} 继续执行？",
                                },
                            },
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "拒绝",
                            },
                            "type": "danger",
                            "value": {
                                "action": "reject",
                                "task_id": task_id,
                            },
                            "confirm": {
                                "title": {
                                    "tag": "plain_text",
                                    "content": "确认拒绝",
                                },
                                "text": {
                                    "tag": "plain_text",
                                    "content": f"确认拒绝任务 {task_id} 的执行请求？",
                                },
                            },
                        },
                    ],
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "如果当前会话未启用卡片回调，仍可发送 approve/reject 指令作为兜底。",
                        }
                    ],
                },
            ],
        }

    @classmethod
    def build_resolved_card(
        cls,
        task_id: str,
        tool_name: str,
        args: Any,
        allowed: bool,
        operator_id: str,
    ) -> Dict[str, Any]:
        formatted_args = cls._truncate_text(cls._format_args(args), limit=500)
        status_text = "已批准" if allowed else "已拒绝"
        status_icon = "✅" if allowed else "⛔"
        template = "green" if allowed else "red"
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": template,
                "title": {
                    "tag": "plain_text",
                    "content": f"高危操作审批{status_text}",
                },
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"{status_icon} **审批结果**：{status_text}\n"
                        f"**工具**：`{tool_name}`\n"
                        f"**任务 ID**：`{task_id}`\n"
                        f"**操作人**：`{operator_id}`"
                    ),
                },
                {
                    "tag": "hr",
                },
                {
                    "tag": "markdown",
                    "content": f"**参数**：\n```json\n{formatted_args}\n```",
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "该审批已处理完成，按钮已失效。",
                        }
                    ],
                },
            ],
        }

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "... (已截断)"

    WaitForApproval = wait_for_approval
    ResolveApproval = resolve_approval


GLOBAL_APPROVAL_MGR = ApprovalManager()
GlobalApprovalMgr = GLOBAL_APPROVAL_MGR


def is_dangerous_command(tool_name: str, args: Any) -> bool:
    """简单的正则黑名单检查，判断该工具调用是否需要审批。"""
    if tool_name not in {"bash", "write_file", "edit_file"}:
        return False

    if tool_name == "bash":
        arg_text = ApprovalManager._format_args(args).lower()
        dangerous_patterns = [
            r"rm\s+-r",
            r"rm\s+-rf",
            r"remove-item\b",
            r"\bdel\b",
            r"\berase\b",
            r"\brd\b",
            r"\brmdir\b",
            r"move-item\b",
            r"rename-item\b",
            r"copy-item\b",
            r"sudo\s+",
            r"drop\s+",
            r">.*\.go",
            r"\.claw\b",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, arg_text):
                return True

    return False


IsDangerousCommand = is_dangerous_command
