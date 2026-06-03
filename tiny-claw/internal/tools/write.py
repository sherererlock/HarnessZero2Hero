import os
from typing import Any

from ..schema.message import ToolDefinition
from .registry import BaseTool


class WriteFileTool(BaseTool):
    """在工作区内创建或覆盖写入文件的工具。"""

    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "write_file"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="创建或覆盖写入一个文件。如果目录不存在会自动创建。请提供相对于工作区的相对路径。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径，如 src/main.py",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整文件内容",
                    },
                },
                "required": ["path", "content"],
            },
        )

    def execute(self, args: Any) -> str:
        path, content = self._extract_args(args)
        full_path = os.path.join(self.work_dir, path)

        parent_dir = os.path.dirname(full_path)
        if parent_dir:
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except OSError as exc:
                raise RuntimeError(f"创建父目录失败: {exc}") from exc

        try:
            with open(full_path, "w", encoding="utf-8") as file:
                file.write(content)
        except OSError as exc:
            raise RuntimeError(f"写入文件失败: {exc}") from exc

        return f"成功将内容写入到文件: {path}"

    def _extract_args(self, args: Any) -> tuple[str, str]:
        if not isinstance(args, dict):
            raise ValueError("参数解析失败: 参数必须是包含 path 和 content 的对象")

        path = args.get("path")
        content = args.get("content")

        if not isinstance(path, str) or not path:
            raise ValueError("参数解析失败: path 必须是非空字符串")
        if not isinstance(content, str):
            raise ValueError("参数解析失败: content 必须是字符串")

        return path, content


def new_write_file_tool(work_dir: str) -> WriteFileTool:
    return WriteFileTool(work_dir)


NewWriteFileTool = new_write_file_tool
