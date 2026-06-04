import os
from typing import Any

from ..schema.message import ToolDefinition
from .registry import BaseTool


class EditFileTool(BaseTool):
    """对现有文件进行局部字符串替换的工具。"""

    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "edit_file"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description=(
                "对现有文件进行局部的字符串替换。这比重写整个文件更安全、更快速。"
                "请提供足够的 old_text 上下文以确保匹配的唯一性。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要修改的文件路径",
                    },
                    "old_text": {
                        "type": "string",
                        "description": (
                            "文件中原有的文本。必须包含足够的上下文（建议上下各多包含几行），"
                            "以确保在文件中的唯一性。"
                        ),
                    },
                    "new_text": {
                        "type": "string",
                        "description": "要替换成的新文本",
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
        )

    def execute(self, args: Any) -> str:
        path, old_text, new_text = self._extract_args(args)
        full_path = os.path.join(self.work_dir, path)

        try:
            with open(full_path, "r", encoding="utf-8") as file:
                original_content = file.read()
        except OSError as exc:
            raise RuntimeError(f"读取文件失败，请确认路径是否正确: {exc}") from exc

        new_content = fuzzy_replace(original_content, old_text, new_text)

        try:
            with open(full_path, "w", encoding="utf-8", newline="") as file:
                file.write(new_content)
        except OSError as exc:
            raise RuntimeError(f"写回文件失败: {exc}") from exc

        return f"✅ 成功修改文件: {path}"

    def _extract_args(self, args: Any) -> tuple[str, str, str]:
        if not isinstance(args, dict):
            raise ValueError("参数解析失败: 参数必须是包含 path、old_text、new_text 的对象")

        path = args.get("path")
        old_text = args.get("old_text")
        new_text = args.get("new_text")

        if not isinstance(path, str) or not path:
            raise ValueError("参数解析失败: path 必须是非空字符串")
        if not isinstance(old_text, str):
            raise ValueError("参数解析失败: old_text 必须是字符串")
        if not isinstance(new_text, str):
            raise ValueError("参数解析失败: new_text 必须是字符串")

        return path, old_text, new_text


def fuzzy_replace(original_content: str, old_text: str, new_text: str) -> str:
    """按四级降级策略执行字符串替换。"""
    count = original_content.count(old_text)
    if count == 1:
        return original_content.replace(old_text, new_text, 1)
    if count > 1:
        raise ValueError(f"old_text 匹配到了 {count} 处，请提供更多的上下文代码以确保唯一性")

    normalized_content = _normalize_newlines(original_content)
    normalized_old = _normalize_newlines(old_text)
    count = normalized_content.count(normalized_old)
    if count == 1:
        return normalized_content.replace(normalized_old, new_text, 1)

    trimmed_old = normalized_old.strip()
    if trimmed_old:
        count = normalized_content.count(trimmed_old)
        if count == 1:
            return normalized_content.replace(trimmed_old, new_text, 1)

    return line_by_line_replace(normalized_content, normalized_old, new_text)


def line_by_line_replace(content: str, old_text: str, new_text: str) -> str:
    """逐行去除首尾空白后做滑动窗口匹配。"""
    content_lines = content.split("\n")
    old_lines = old_text.strip().split("\n")

    if len(content_lines) < len(old_lines):
        raise ValueError("找不到该代码片段")

    normalized_old_lines = [line.strip() for line in old_lines]
    if not normalized_old_lines or all(line == "" for line in normalized_old_lines):
        raise ValueError("找不到该代码片段")

    match_count = 0
    match_start_index = -1
    match_end_index = -1

    for start_index in range(len(content_lines) - len(normalized_old_lines) + 1):
        is_match = True
        for offset, old_line in enumerate(normalized_old_lines):
            if content_lines[start_index + offset].strip() != old_line:
                is_match = False
                break

        if is_match:
            match_count += 1
            match_start_index = start_index
            match_end_index = start_index + len(normalized_old_lines)

    if match_count == 0:
        raise ValueError("在文件中未找到 old_text，请大模型先调用 read_file 仔细确认文件内容和缩进")
    if match_count > 1:
        raise ValueError(f"模糊匹配到了 {match_count} 处相似代码，请提供更多上下行代码以精确定位")

    new_content_lines = (
        content_lines[:match_start_index]
        + [new_text]
        + content_lines[match_end_index:]
    )
    return "\n".join(new_content_lines)


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n")


def new_edit_file_tool(work_dir: str) -> EditFileTool:
    return EditFileTool(work_dir)


NewEditFileTool = new_edit_file_tool
