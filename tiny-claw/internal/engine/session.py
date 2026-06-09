from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Dict, List

from ..schema.message import Message, Role


@dataclass
class Session:
    """Session 代表一次持续的人机交互过程，负责维护完整历史。"""

    id: str
    work_dir: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    history: List[Message] = field(default_factory=list)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def append(self, *msgs: Message) -> None:
        """线程安全地向 Session 中追加消息。"""
        with self._lock:
            self.history.extend(msgs)
            self.updated_at = datetime.now()
            # 持久化预留点：
            # 真实实现里可在这里把 history 追加写入 work_dir/.claw/sessions/*.jsonl

    def get_working_memory(self, limit: int) -> List[Message]:
        """
        返回最近的 N 条消息作为“短期工作记忆”。

        如果切片首条是被截断后留下的孤儿 tool result，则继续丢弃，
        直到首条重新回到连续的 user/assistant 消息。
        """
        with self._lock:
            total = len(self.history)
            if total <= limit or limit <= 0:
                return list(self.history)

            result = list(self.history[total - limit :])

            while result:
                first = result[0]
                if first.role == Role.USER and first.tool_call_id:
                    result = result[1:]
                    continue
                break

            return result


def new_session(session_id: str, work_dir: str) -> Session:
    return Session(id=session_id, work_dir=work_dir)


class SessionManager:
    """全局 Session Manager: 用于多用户/多终端隔离。"""

    def __init__(self) -> None:
        self.sessions: Dict[str, Session] = {}
        self._lock = RLock()

    def get_or_create(self, session_id: str, work_dir: str) -> Session:
        with self._lock:
            if session_id in self.sessions:
                return self.sessions[session_id]

            session = new_session(session_id, work_dir)
            self.sessions[session_id] = session
            return session


global_session_mgr = SessionManager()
GlobalSessionMgr = global_session_mgr
