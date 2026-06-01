import json
import os
from typing import Any, List, Optional

from ..schema.message import Message, Role, ToolCall, ToolDefinition
from .env_loader import resolve_api_key
from .interface import LLMProvider

ZHIPU_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class OpenAIProvider(LLMProvider):
    """使用 OpenAI Python SDK 访问智谱兼容接口的 Provider。"""

    def __init__(
        self,
        model: str,
        client: Any = None,
        api_key: Optional[str] = None,
        base_url: str = ZHIPU_BASE_URL,
    ):
        self.model = model
        self.base_url = base_url
        self.client = client or self._build_client(api_key=api_key, base_url=base_url)

    @staticmethod
    def _build_client(api_key: Optional[str], base_url: str) -> Any:
        api_key = resolve_api_key(api_key)
        if not api_key:
            raise ValueError("请设置 ZHIPU_API_KEY，或在项目 .env 中配置它")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("请先安装 openai 包，例如: pip install openai") from exc

        return OpenAI(api_key=api_key, base_url=base_url)

    def generate(
        self,
        messages: List[Message],
        available_tools: Optional[List[ToolDefinition]],
    ) -> Message:
        request_messages = [self._message_to_openai(message) for message in messages]
        params = {
            "model": self.model,
            "messages": request_messages,
        }

        openai_tools = self._tools_to_openai(available_tools)
        if openai_tools:
            params["tools"] = openai_tools

        try:
            response = self.client.chat.completions.create(**params)
        except Exception as exc:
            raise RuntimeError(f"OpenAI/Zhipu API 请求失败: {exc}") from exc

        choices = _get_attr(response, "choices", [])
        if not choices:
            raise RuntimeError("API 返回了空的 Choices")

        return self._message_from_openai(_get_attr(choices[0], "message"))

    def _message_to_openai(self, message: Message) -> dict[str, Any]:
        if message.role == Role.SYSTEM:
            return {"role": "system", "content": message.content}

        if message.role == Role.USER:
            if message.tool_call_id:
                return {
                    "role": "tool",
                    "content": message.content,
                    "tool_call_id": message.tool_call_id,
                }
            return {"role": "user", "content": message.content}

        if message.role == Role.ASSISTANT:
            payload: dict[str, Any] = {"role": "assistant"}
            if message.content:
                payload["content"] = message.content
            if message.tool_calls:
                payload["tool_calls"] = [
                    self._tool_call_to_openai(tool_call) for tool_call in message.tool_calls
                ]
            if "content" not in payload and "tool_calls" not in payload:
                payload["content"] = ""
            return payload

        raise ValueError(f"不支持的消息角色: {message.role}")

    def _tool_call_to_openai(self, tool_call: ToolCall) -> dict[str, Any]:
        return {
            "id": tool_call.id,
            "type": "function",
            "function": {
                "name": tool_call.name,
                "arguments": self._encode_tool_arguments(tool_call.arguments),
            },
        }

    def _tools_to_openai(
        self, available_tools: Optional[List[ToolDefinition]]
    ) -> List[dict[str, Any]]:
        openai_tools: List[dict[str, Any]] = []
        for tool in available_tools or []:
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": self._normalize_input_schema(tool.input_schema),
                    },
                }
            )
        return openai_tools

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

    def _message_from_openai(self, message: Any) -> Message:
        if message is None:
            raise RuntimeError("API 返回的消息为空")

        content = _get_attr(message, "content", "") or ""
        tool_calls: List[ToolCall] = []
        for tool_call in _get_attr(message, "tool_calls", []) or []:
            if _get_attr(tool_call, "type") != "function":
                continue

            function = _get_attr(tool_call, "function")
            tool_calls.append(
                ToolCall(
                    id=_get_attr(tool_call, "id", ""),
                    name=_get_attr(function, "name", ""),
                    arguments=self._decode_tool_arguments(_get_attr(function, "arguments", "")),
                )
            )

        return Message(
            role=Role.ASSISTANT,
            content=content,
            tool_calls=tool_calls or None,
        )

    def _encode_tool_arguments(self, arguments: Any) -> str:
        if arguments is None:
            return "{}"
        if isinstance(arguments, bytes):
            return arguments.decode("utf-8")
        if isinstance(arguments, str):
            return arguments
        return _json_dumps(arguments)

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


def new_zhipu_openai_provider(model: str) -> OpenAIProvider:
    return OpenAIProvider(model=model)


NewZhipuOpenAIProvider = new_zhipu_openai_provider
