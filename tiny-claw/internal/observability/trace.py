from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterator, Optional


_current_tracer_var: ContextVar[Optional["Tracer"]] = ContextVar(
    "current_tracer", default=None
)
_current_span_var: ContextVar[Optional["Span"]] = ContextVar(
    "current_span", default=None
)


def get_current_tracer() -> Optional["Tracer"]:
    return _current_tracer_var.get()


def get_current_span() -> Optional["Span"]:
    return _current_span_var.get()


@dataclass
class Span:
    name: str
    tracer: "Tracer"
    parent: Optional["Span"] = None
    attributes: dict[str, Any] = field(default_factory=dict)
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    duration_ms: Optional[int] = None
    children: list["Span"] = field(default_factory=list)
    status: str = "ok"
    error: Optional[str] = None
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def add_child(self, child: "Span") -> None:
        with self._lock:
            self.children.append(child)

    def add_attribute(self, key: str, value: Any) -> None:
        with self._lock:
            self.attributes[key] = value

    def record_error(self, error: Any) -> None:
        self.status = "error"
        self.error = str(error)

    def finish(self) -> None:
        if self.end_time is not None:
            return
        self.end_time = datetime.now(timezone.utc)
        self.duration_ms = int(
            (self.end_time - self.start_time).total_seconds() * 1000
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
        }
        if self.attributes:
            payload["attributes"] = _to_jsonable(self.attributes)
        if self.children:
            payload["children"] = [child.to_dict() for child in self.children]
        if self.status != "ok":
            payload["status"] = self.status
        if self.error:
            payload["error"] = self.error
        return payload


class Tracer:
    def __init__(self, work_dir: str, session_id: str) -> None:
        self.work_dir = Path(work_dir)
        self.session_id = session_id
        self.trace_dir = self.work_dir / ".claw" / "traces"

    @contextmanager
    def span(
        self,
        name: str,
        parent: Optional[Span] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Iterator[Span]:
        if parent is None:
            parent = get_current_span()

        span = Span(
            name=name,
            tracer=self,
            parent=parent,
            attributes=dict(attributes or {}),
        )
        if parent is not None:
            parent.add_child(span)

        tracer_token = _current_tracer_var.set(self)
        span_token = _current_span_var.set(span)
        try:
            yield span
        except Exception as exc:
            span.record_error(exc)
            raise
        finally:
            span.finish()
            _current_span_var.reset(span_token)
            _current_tracer_var.reset(tracer_token)

    def export_trace(self, root_span: Span) -> str:
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        filename = f"trace_{self.session_id}_{int(datetime.now(timezone.utc).timestamp())}.json"
        file_path = self.trace_dir / filename
        file_path.write_text(
            json.dumps(root_span.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(file_path)


def new_tracer(work_dir: str, session_id: str) -> Tracer:
    return Tracer(work_dir=work_dir, session_id=session_id)


def preview_text(value: Any, limit: int = 200) -> str:
    text = _stringify(value)
    if len(text) <= limit:
        return text
    return text[:limit] + f"...(已截断，原始长度: {len(text)})"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return str(value)


NewTracer = new_tracer
