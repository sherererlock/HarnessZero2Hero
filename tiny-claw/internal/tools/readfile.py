import os
from typing import Any

from ..schema.message import ToolDefinition
from .registry import BaseTool

MAX_LEN = 8000


class ReadFileTool(BaseTool):
    """读取工作区内本地文件内容的工具。"""

    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "read_file"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="读取指定路径的文件内容。请提供相对工作区的路径。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径，如 cmd/claw/main.py",
                    }
                },
                "required": ["path"],
            },
        )

    def execute(self, args: Any) -> str:
        path = self._extract_path(args)
        full_path = os.path.join(self.work_dir, path)

        try:
            with open(full_path, "r", encoding="utf-8") as file:
                content = file.read()
        except OSError as exc:
            raise RuntimeError(f"打开文件失败: {exc}") from exc

        if len(content) > MAX_LEN:
            return (
                f"{content[:MAX_LEN]}\n\n"
                f"...[由于内容过长，已被系统截断至前 {MAX_LEN} 字节]..."
            )
        return content

    def _extract_path(self, args: Any) -> str:
        if not isinstance(args, dict):
            raise ValueError("参数解析失败: 参数必须是包含 path 的对象")

        path = args.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("参数解析失败: path 必须是非空字符串")
        return path


def new_read_file_tool(work_dir: str) -> ReadFileTool:
    return ReadFileTool(work_dir)


NewReadFileTool = new_read_file_tool
