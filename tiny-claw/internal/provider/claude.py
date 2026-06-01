import json
import os
from typing import Any, List, Optional

from ..schema.message import Message, Role, ToolCall, ToolDefinition
from .env_loader import resolve_api_key
from .interface import LLMProvider

ZHIPU_BASE_URL = "https://token-plan-cn.xiaomimimo.com/anthropic"


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class ClaudeProvider(LLMProvider):
    """使用 Anthropic Python SDK 访问智谱兼容接口的 Provider。"""

    def __init__(
        self,
        model: str,
        client: Any = None,
        api_key: Optional[str] = None,
        base_url: str = ZHIPU_BASE_URL,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.client = client or self._build_client(api_key=api_key, base_url=base_url)

    @staticmethod
    def _build_client(api_key: Optional[str], base_url: str) -> Any:
        api_key = resolve_api_key(api_key)
        if not api_key:
            raise ValueError("请设置 ZHIPU_API_KEY，或在项目 .env 中配置它")

        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ImportError("请先安装 anthropic 包，例如: pip install anthropic") from exc

        return Anthropic(api_key=api_key, base_url=base_url)

    def generate(
        self,
        messages: List[Message],
        available_tools: Optional[List[ToolDefinition]],
    ) -> Message:
        system_prompt, request_messages = self._messages_to_anthropic(messages)
        params = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": request_messages,
        }
        if system_prompt:
            params["system"] = system_prompt

        anthropic_tools = self._tools_to_anthropic(available_tools)
        if anthropic_tools:
            params["tools"] = anthropic_tools

        try:
            response = self.client.messages.create(**params)
        except Exception as exc:
            raise RuntimeError(f"Claude/Zhipu API 请求失败: {exc}") from exc

        return self._message_from_anthropic(response)

    def _messages_to_anthropic(self, messages: List[Message]) -> tuple[str, List[dict[str, Any]]]:
        system_prompt = ""
        anthropic_messages: List[dict[str, Any]] = []

        for message in messages:
            if message.role == Role.SYSTEM:
                system_prompt = message.content
                continue

            if message.role == Role.USER:
                anthropic_messages.append(self._user_message_to_anthropic(message))
                continue

            if message.role == Role.ASSISTANT:
                assistant_message = self._assistant_message_to_anthropic(message)
                if assistant_message is not None:
                    anthropic_messages.append(assistant_message)
                continue

            raise ValueError(f"不支持的消息角色: {message.role}")

        return system_prompt, anthropic_messages

    def _user_message_to_anthropic(self, message: Message) -> dict[str, Any]:
        if message.tool_call_id:
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": message.tool_call_id,
                        "content": message.content,
                        "is_error": False,
                    }
                ],
            }

        return {
            "role": "user",
            "content": [{"type": "text", "text": message.content}],
        }

    def _assistant_message_to_anthropic(self, message: Message) -> Optional[dict[str, Any]]:
        blocks: List[dict[str, Any]] = []
        if message.content:
            blocks.append({"type": "text", "text": message.content})
        for tool_call in message.tool_calls or []:
            blocks.append(
                {
                    "type": "tool_use",
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "input": self._decode_tool_arguments(tool_call.arguments),
                }
            )

        if not blocks:
            return None

        return {"role": "assistant", "content": blocks}

    def _tools_to_anthropic(
        self, available_tools: Optional[List[ToolDefinition]]
    ) -> List[dict[str, Any]]:
        anthropic_tools: List[dict[str, Any]] = []
        for tool in available_tools or []:
            anthropic_tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": self._normalize_input_schema(tool.input_schema),
                }
            )
        return anthropic_tools

    def _normalize_input_schema(self, input_schema: Any) -> dict[str, Any]:
        if input_schema is None:
            return {"type": "object", "properties": {}}

        if isinstance(input_schema, dict):
            return input_schema

        try:
            normalized = json.loads(_json_dumps(input_schema))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"工具入参 Schema 不是合法 JSON 对象: {input_schema!r}") from exc

        if not isinstance(normalized, dict):
            raise ValueError(f"工具入参 Schema 必须是字典对象: {input_schema!r}")
        return normalized

    def _message_from_anthropic(self, response: Any) -> Message:
        content_blocks = _get_attr(response, "content", []) or []
        result = Message(role=Role.ASSISTANT, content="")
        tool_calls: List[ToolCall] = []

        for block in content_blocks:
            block_type = _get_attr(block, "type")
            if block_type == "text":
                result.content += _get_attr(block, "text", "") or ""
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=_get_attr(block, "id", ""),
                        name=_get_attr(block, "name", ""),
                        arguments=_get_attr(block, "input", {}) or {},
                    )
                )

        result.tool_calls = tool_calls or None
        return result

    def _decode_tool_arguments(self, arguments: Any) -> Any:
        if arguments in (None, ""):
            return {}
        if isinstance(arguments, bytes):
            arguments = arguments.decode("utf-8")
        if not isinstance(arguments, str):
            return arguments
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return arguments


def new_zhipu_claude_provider(model: str) -> ClaudeProvider:
    return ClaudeProvider(model=model)


NewZhipuClaudeProvider = new_zhipu_claude_provider
