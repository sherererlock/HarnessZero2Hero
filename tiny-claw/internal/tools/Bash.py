import os
import subprocess
from typing import Any

from ..schema.message import ToolDefinition
from .registry import BaseTool

TIMEOUT_SECONDS = 30
MAX_LEN = 8000


class BashTool(BaseTool):
    """在工作区执行 shell 命令的工具。"""

    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "bash"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="在当前工作区执行任意的 bash 命令。支持链式命令(如 &&)。返回标准输出(stdout)和标准错误(stderr)。",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 bash 命令，例如: ls -la 或 go test ./...",
                    }
                },
                "required": ["command"],
            },
        )

    def execute(self, args: Any) -> str:
        command = self._extract_command(args)

        try:
            completed = subprocess.run(
                self._shell_command(command),
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            timeout_output = self._combine_output(exc.stdout, exc.stderr)
            return (
                timeout_output
                + "\n[警告: 命令执行超时(30s)，已被系统强制终止。如果是启动常驻服务，请尝试将其转入后台。]"
            ).lstrip("\n")

        output = self._combine_output(completed.stdout, completed.stderr)

        if completed.returncode != 0:
            return f"执行报错: exit code {completed.returncode}\n输出:\n{output}"

        if output == "":
            return "命令执行成功，无终端输出。"

        if len(output) > MAX_LEN:
            return f"{output[:MAX_LEN]}\n\n...[终端输出过长，已截断至前 {MAX_LEN} 字节]..."

        return output

    def _extract_command(self, args: Any) -> str:
        if not isinstance(args, dict):
            raise ValueError("参数解析失败: 参数必须是包含 command 的对象")

        command = args.get("command")
        if not isinstance(command, str) or not command:
            raise ValueError("参数解析失败: command 必须是非空字符串")
        return command

    def _shell_command(self, command: str) -> list[str]:
        if os.name == "nt":
            return ["powershell", "-Command", command]
        return ["bash", "-lc", command]

    def _combine_output(self, stdout: Any, stderr: Any) -> str:
        parts = []
        for part in (stdout, stderr):
            if isinstance(part, bytes):
                part = part.decode("utf-8", errors="replace")
            if part:
                parts.append(part)
        return "".join(parts)


def new_bash_tool(work_dir: str) -> BashTool:
    return BashTool(work_dir)


NewBashTool = new_bash_tool
