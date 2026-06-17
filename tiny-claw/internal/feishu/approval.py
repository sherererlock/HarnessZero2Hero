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


class ApprovalManager:
    """统一管理当前正在等待人类审批的任务。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.pending_tasks: Dict[str, queue.Queue[ApprovalResult]] = {}

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
            self.pending_tasks[task_id] = ch

        notice_msg = (
            "⚠️ **高危操作审批请求**\n"
            "Agent 试图执行以下动作:\n"
            f"- 工具: {tool_name}\n"
            f"- 参数: {self._format_args(args)}\n"
            f"任务 ID: **{task_id}**\n"
            f'👉 请在此消息下方回复 "approve {task_id}" 或 "reject {task_id}" 来决定是否放行。'
        )

        try:
            self._send_notice(notice_msg, task_id, reporter)
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
            ch = self.pending_tasks.get(task_id)

        if ch is None:
            logging.info("[Approval] 找不到对应的 TaskID: %s，可能已超时或处理完毕", task_id)
            return

        logging.info(
            "[Approval] 收到来自飞书的审批结果 (TaskID: %s, Allowed: %s)",
            task_id,
            allowed,
        )
        ch.put(ApprovalResult(allowed=allowed, reason=reason))

    def _send_notice(self, notice_msg: str, task_id: str, reporter: Optional[Any]) -> None:
        if reporter is not None:
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

    WaitForApproval = wait_for_approval
    ResolveApproval = resolve_approval


GLOBAL_APPROVAL_MGR = ApprovalManager()
GlobalApprovalMgr = GLOBAL_APPROVAL_MGR


def is_dangerous_command(tool_name: str, args: Any) -> bool:
    """简单的正则黑名单检查，判断该工具调用是否需要审批。"""
    if tool_name not in {"bash", "write_file", "edit_file"}:
        return False

    if tool_name == "bash":
        arg_text = ApprovalManager._format_args(args)
        dangerous_patterns = [
            r"rm\s+-r",
            r"sudo\s+",
            r"drop\s+",
            r">.*\.go",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, arg_text):
                return True

    return False


IsDangerousCommand = is_dangerous_command
