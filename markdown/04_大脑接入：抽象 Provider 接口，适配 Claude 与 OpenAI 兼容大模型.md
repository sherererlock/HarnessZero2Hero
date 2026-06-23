你好，我是 Tony Bai。欢迎来到《从 0 开始构建 Agent Harness》专栏的第四讲。

在前面的课程中，我们犹如打造精密钟表一般，用 Go 语言构建了 go-tiny-claw 的核心部件。特别是上一讲，我们在 ReAct 循环中巧妙地剥离出了独立的慢思考（Thinking）阶段，从架构机制上压制了大模型的行动冲动。

然而，这台设计精妙的微型操作系统（Harness），目前依然连接着一个 mockProvider（假肢大脑）。今天，我们将正式拔掉这双“假肢”，为引擎接入真实的前沿大模型。

在真实的企业级 AI 应用开发中，我们面临着一个绕不开的碎片化痛点：不同大模型厂商的 API 数据结构存在巨大差异。特别是涉及 Function Calling（工具调用）和上下文组装时，OpenAI 生态和 Anthropic（Claude）生态是两套截然不同的标准。

如果在我们的核心 Main Loop 中直接写入这些特定厂商的 SDK 代码，整个驾驭工程（Harness Engineering）的解耦原则就会被彻底破坏。

本讲，我们将通过设计优雅的 Provider 抽象层，完美隔离这种差异。为了兼顾国内网络环境的便利性，我们将使用国内的智谱大模型（GLM）来作为统一的算力底座。由于智谱 API 实现了对 OpenAI 和 Claude 两大生态双协议的兼容，我们将在同一套代码中，演示如何通过官方的 OpenAI Python SDK 和 Anthropic Python SDK，双管齐下地接入 glm-4.5-air 模型。

## Provider 作为“同声传译”

先来看看如果我们不加抽象，直接在 Main Loop 里调用 SDK 会发生什么。

Claude 的 API 使用的是 messages 数组，工具调用返回的是特定的 tool_use 块；而 OpenAI 兼容 API 使用的是一套不同的 tools 和 tool_calls 结构。

如果 Main Loop 需要关心这些底层细节，它的逻辑就会变成这样：
```python
# 糟糕的面条代码示例 (千万别这么写)
if engine.model_type == "claude":
    # 构造 anthropic.MessageParam
    # 解析 anthropic.ToolUseBlock
    pass
elif engine.model_type == "openai":
    # 构造 openai.ChatCompletionMessage
    # 解析 openai.ToolCall
    pass
```

这违背了我们驾驭工程的极简和解耦哲学。Main Loop 的唯一职责是维护上下文时间线（Context History）。它不应该知道外部世界是用什么协议通信的。

在驾驭工程中，Main Loop 应当只认识一种语言——也就是我们在第 01 讲中定义的 schema.Message、schema.ToolCall 和 schema.ToolResult。

Provider 层的核心职责，就是充当一个同声传译员（Translator）。

当 Main Loop 发起推理请求时，Provider 需要将内部干净的 schema.Message 历史记录，翻译成各大厂商 SDK 所要求的那种晦涩、嵌套极深的请求体；而当大模型 API 返回结果后，Provider 又必须将厂商特有的 ToolUseBlock 或 FunctionCall 结构，精确地反向翻译回内部的 schema.Message。

我们可以用一张示意图来展示这种解耦架构：

![](img/04_01.webp)

通过这层抽象，我们的微型 OS 具备了“即插即用”换大脑的能力。

## 代码实战：实现双协议 Provider 适配器

在开始编写代码前，我们需要安装两大官方的 Python SDK。

注：我们将使用官方的 OpenAI Python SDK 和 Anthropic Python SDK。
```bash
pip install openai anthropic
```

### 目录结构回顾与更新

我们将所有的翻译逻辑都集中在 internal/provider 目录下。为了进行测试，我们仍会在 main.py 中保留一个 Mock 的 Tool Registry（真正的 Tools Registry 将在下一讲实现）。
```
tiny-claw/
├── cmd/
│   └── claw/
│       └── main.py          # 【修改】接入真实的 Provider 并启动测试
├── internal/
│   ├── engine/              # 保持不变 (loop.py 中已支持两阶段思考)
│   ├── provider/            # 【模型适配层】
│   │   ├── interface.py     # 接口定义 (复用)
│   │   ├── openai.py        # 【新增】基于 OpenAI Python SDK 的适配器
│   │   └── claude.py        # 【新增】基于 Anthropic Python SDK 的适配器
│   ├── schema/              # 保持不变
│   └── tools/               # 保持不变
├── requirements.txt
└── setup.py
```

### 第 1 步：复习接口契约

为了保持代码的连贯性，我们快速回顾一下在之前章节定义的 LLMProvider 接口：
```python
# internal/provider/interface.py
from abc import ABC, abstractmethod
from typing import List
from ..schema.message import Message, ToolDefinition

class LLMProvider(ABC):
    """LLMProvider 定义了与大模型通信的统一契约"""

    @abstractmethod
    def generate(
        self,
        messages: List[Message],
        available_tools: List[ToolDefinition]
    ) -> Message:
        """Generate 接收当前的上下文历史和可用工具列表，返回模型的新消息。
        
        注意：当 available_tools 为 None 或长度为 0 时，代表引擎正在强制模型进入慢思考阶段。
        """
        pass
```

### 第 2 步：实现 OpenAI 格式适配器（兼容智谱）

我们首先编写 openai.py。智谱 API 原生兼容 OpenAI 协议，所以我们只需在使用官方 OpenAI Python SDK 时，将其 base_url 替换为智谱的 API 地址即可。

新建 internal/provider/openai.py：
```python
# internal/provider/openai.py
import json
import os
from typing import Any, List, Optional

from ..schema.message import Message, Role, ToolCall, ToolDefinition
from .interface import LLMProvider

ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"


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
        """构造函数：基于 OpenAI Python SDK，指向智谱底座"""
        api_key = api_key or os.getenv("ZHIPU_API_KEY")
        if not api_key:
            raise ValueError("请设置 ZHIPU_API_KEY 环境变量")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("请先安装 openai 包，例如: pip install openai") from exc

        # 核心：将官方 SDK 的地址替换为智谱的兼容端点
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

        # 翻译工具定义
        openai_tools = self._tools_to_openai(available_tools)

        # 【慢思考机制支撑】仅当 available_tools 存在时才挂载 Tools
        if openai_tools:
            params["tools"] = openai_tools

        try:
            response = self.client.chat.completions.create(**params)
        except Exception as exc:
            raise RuntimeError(f"OpenAI/Zhipu API 请求失败: {exc}") from exc

        choices = _get_attr(response, "choices", [])
        if not choices:
            raise RuntimeError("API 返回了空的 Choices")

        # 将 API Response 反向翻译为内部 Message
        result_message = self._message_from_openai(_get_attr(choices[0], "message"))
        return result_message

    def _message_to_openai(self, message: Message) -> dict[str, Any]:
        """翻译上下文消息"""
        if message.role == Role.SYSTEM:
            return {"role": "system", "content": message.content}

        if message.role == Role.USER:
            if message.tool_call_id:
                # 注意：Tool 消息的参数顺序是 (content, tool_call_id)
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

            # 【重要】如果历史包含 ToolCalls，必须原样放回，以维系大模型的逻辑链
            if message.tool_calls:
                payload["tool_calls"] = [
                    self._tool_call_to_openai(tc) for tc in message.tool_calls
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
        """翻译工具定义 (适配 OpenAI 格式)"""
        openai_tools: List[dict[str, Any]] = []
        for tool in available_tools or []:
            # 尝试直接使用，如果不匹配则通过 JSON 往返序列化来保证类型匹配
            params = self._normalize_input_schema(tool.input_schema)
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": params,
                    },
                }
            )
        return openai_tools

    def _normalize_input_schema(self, input_schema: Any) -> dict[str, Any]:
        """JSON 往返序列化，保证类型匹配"""
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
        """将 API Response 反向翻译为内部 Message"""
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
                    arguments=self._decode_tool_arguments(
                        _get_attr(function, "arguments", "")
                    ),
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


# 构造函数别名，指向智谱底座
def new_zhipu_openai_provider(model: str) -> OpenAIProvider:
    return OpenAIProvider(model=model)


NewZhipuOpenAIProvider = new_zhipu_openai_provider
```

### 第 3 步：实现 Claude 格式适配器（兼容智谱）

得益于智谱强大的生态兼容能力，它的 API 同样支持接收 Anthropic（Claude）标准的请求体。我们现在编写 claude.py。

注意对比这里与 OpenAI 在 InputSchema 解析上的细微差异：Anthropic 官方 SDK 将工具的 Properties 和 Required 字段做了严格的结构体抽离。
```python
# internal/provider/claude.py
import json
import os
from typing import Any, List, Optional

from ..schema.message import Message, Role, ToolCall, ToolDefinition
from .interface import LLMProvider

ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"


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
        """构造函数：基于 Anthropic Python SDK，指向智谱底座"""
        api_key = api_key or os.getenv("ZHIPU_API_KEY")
        if not api_key:
            raise ValueError("请设置 ZHIPU_API_KEY 环境变量")

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
        # 1. 消息翻译
        system_prompt, request_messages = self._messages_to_anthropic(messages)
        params = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": request_messages,
        }

        if system_prompt:
            params["system"] = system_prompt

        # 2. 工具 Schema 翻译
        anthropic_tools = self._tools_to_anthropic(available_tools)
        if anthropic_tools:
            params["tools"] = anthropic_tools

        # 3. 构建请求并发送
        try:
            response = self.client.messages.create(**params)
        except Exception as exc:
            raise RuntimeError(f"Claude/Zhipu API 请求失败: {exc}") from exc

        # 4. 反向解析
        return self._message_from_anthropic(response)

    def _messages_to_anthropic(
        self, messages: List[Message]
    ) -> tuple[str, List[dict[str, Any]]]:
        """消息翻译"""
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

    def _assistant_message_to_anthropic(
        self, message: Message
    ) -> Optional[dict[str, Any]]:
        blocks: List[dict[str, Any]] = []
        if message.content:
            blocks.append({"type": "text", "text": message.content})

        # 将历史工具调用转回 Claude 特有的 ToolUseBlock
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
        """工具 Schema 翻译 (适配 Anthropic 格式)"""
        anthropic_tools: List[dict[str, Any]] = []
        for tool in available_tools or []:
            # input_schema 需要通过 Properties 字段精准填充
            normalized_schema = self._normalize_input_schema(tool.input_schema)
            anthropic_tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": normalized_schema,
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
        """反向解析：将 Anthropic API 响应翻译为内部 Message"""
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


# 构造函数别名，指向智谱底座
def new_zhipu_claude_provider(model: str) -> ClaudeProvider:
    return ClaudeProvider(model=model)


NewZhipuClaudeProvider = new_zhipu_claude_provider
```

## 运行与深度分析：算力分配与“自适应推理”

我们的 Provider 适配器已经全部就绪。但在运行测试之前，我们必须探讨一个真实工业场景中的关键问题：什么时候该让 Agent 慢思考，什么时候该让它直接行动？

在上一讲中，我们在架构上剥离出了独立的 Thinking（推理）阶段，以防止模型在面对复杂代码时变成盲目执行的“莽夫”。

然而，如果任务仅仅是：”帮我查查北京的天气”，开启长篇大论的慢思考是否值得？让我们通过 cmd/claw/main.py，传入一个 MockRegistry（伪造查询天气工具，真实的 ToolRegistry 将在下一讲实现），分别在开启和关闭慢思考模式下，观察这台微型操作系统的真实反应。
```python
# cmd/claw/main.py
import os
import logging
from typing import List

from internal.engine.loop import AgentEngine
from internal.provider.openai import NewZhipuOpenAIProvider
from internal.schema.message import Message, Role, ToolCall, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


# 伪造的工具注册表 (用于测试 Provider 的工具提取能力)
class MockRegistry:
    """Mock Registry，用于测试 Provider 的工具提取能力。"""

    def get_available_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_weather",
                description="获取指定城市的当前天气情况。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                        },
                    },
                    "required": ["city"],
                },
            ),
        ]

    def execute(self, call: ToolCall) -> ToolResult:
        logger.info("  -> [Mock 工具执行] 获取 %s 的天气中...", call.name)
        return ToolResult(
            tool_call_id=call.id,
            output="API 返回：今天是晴天，气温 25 度。",
            is_error=False,
        )


def main():
    # 确保已设置 ZHIPU_API_KEY
    if not os.getenv("ZHIPU_API_KEY"):
        raise RuntimeError("请先导出 ZHIPU_API_KEY 环境变量")

    work_dir = os.getcwd()

    # 1. 初始化真实的 Provider 大脑 (指向智谱 GLM-4.5)
    # 这里你可以任意切换 NewZhipuClaudeProvider 或 NewZhipuOpenAIProvider，效果完全一致！
    llm_provider = NewZhipuOpenAIProvider("glm-4.5-air")

    # 2. 注入伪造的工具注册表
    registry = MockRegistry()

    # 3. 实例化并运行引擎，开启 EnableThinking = True (开启慢思考阶段！)
    eng = AgentEngine(llm_provider, registry, work_dir, enable_thinking=True)

    # 设定测试任务
    prompt = "我想去北京跑步，帮我查查天气适合吗？"

    try:
        eng.run(prompt)
    except Exception as e:
        logger.error("引擎运行崩溃: %s", e)
        raise


if __name__ == "__main__":
    main()
```

### 测试 1：开启慢思考 (EnableThinking = true)
```python
# 实例化并运行引擎，开启慢思考
eng = AgentEngine(llm_provider, registry, work_dir, enable_thinking=True)
```

执行 python cmd/claw/main.py，观察日志：
```
[Engine] 慢思考模式 (Thinking Phase): true

========== [Turn 1] 开始 ==========
[Engine][Phase 1] 剥夺工具访问权，强制进入慢思考与规划阶段...
🧠 [内部思考 Trace]: 
我来帮您查询一下北京的天气情况，看看是否适合跑步。
让我为您查询北京当前的天气：
<invoke name="getWeather">
<parameter name="location">北京</parameter>
</invoke>

[Engine][Phase 2] 恢复工具挂载，等待模型采取行动...
🤖 [对外回复]: 我来帮您查询一下北京的天气情况，看看是否适合跑步。
[Engine] 模型请求调用 1 个工具...
  -> 🛠️ 执行工具: get_weather, 参数: {"city":"北京"}
  -> ✅ 工具执行成功 (返回 47 字节)

========== [Turn 2] 开始 ==========
[Engine][Phase 1] 剥夺工具访问权，强制进入慢思考与规划阶段...
🧠 [内部思考 Trace]: 
根据查询结果，北京今天的天气非常适合跑步！
🌞 **天气状况**：晴天 🌡️ **气温**：25度... (省略大量分析文本)

[Engine][Phase 2] 恢复工具挂载，等待模型采取行动...
🤖 [对外回复]: 根据查询结果，北京今天的天气非常适合跑步！🏃‍♂️...
[Engine] 模型未请求调用工具，任务宣告完成。
```

你看，因为我们在 Phase 1 剥夺了它的工具，大模型由于强烈的“想要执行任务”的冲动，甚至在纯文本的思考轨迹中，自己“脑补”出了一个 XML 格式的伪工具调用（<invoke name="getWeather">）！随后在 Phase 2，它才真正输出了合法的 JSON ToolCall。

虽然它完美地完成了任务，但对于这个极其简单的动作来说，这种“系统 2”的深度思考产生了巨大的算力浪费（Token Waste）和延迟（Latency）。

### 测试 2：关闭慢思考（EnableThinking = false）

现在，我们在 main.py 中将开关调为 False：
```python
# 实例化并运行引擎，关闭慢思考
eng = AgentEngine(llm_provider, registry, work_dir, enable_thinking=False)
```

再次运行程序，日志变得极其清爽干练：
```
[Engine] 慢思考模式 (Thinking Phase): false

========== [Turn 1] 开始 ==========
[Engine][Phase 2] 恢复工具挂载，等待模型采取行动...
🤖 [对外回复]: 我来帮您查询一下北京的天气情况，看看是否适合跑步。
[Engine] 模型请求调用 1 个工具...
 -> 🛠️ 执行工具: get_weather, 参数: {"city":"北京"}
 -> ✅ 工具执行成功 (返回 47 字节)

========== [Turn 2] 开始 ==========
[Engine][Phase 2] 恢复工具挂载，等待模型采取行动...
🤖 [对外回复]: 根据查询结果，北京今天的天气非常适合跑步！
🌞 **天气状况**：晴天 🌡️ **气温**：25度
建议您可以放心去跑步，记得带上防晒用品，因为晴天紫外线较强。祝您跑步愉快！🏃‍♂️
[Engine] 模型未请求调用工具，任务宣告完成。
```

结论：自适应推理（Adaptive Reasoning）

这两个截然不同的日志，完美印证了为什么我们的 AgentEngine 需要设计 EnableThinking 这个硬开关。

在工业级 Harness 引擎中，我们不应该用“杀鸡用牛刀”的方式去执行所有任务。

面对“列出当前目录文件”“查天气”等明确的检索任务，我们应当关闭 Thinking 阶段，享受极低的 Token 成本和毫秒级的响应。

面对“分析这 10 个文件的依赖关系并重构缓存层”等复杂任务时，我们需要打开 Thinking 阶段，用算力和时间换取代码修改的准确性。

这种动态分配算力的思想，正是目前 Agent 开发领域前沿的 Adaptive Reasoning（自适应推理）策略的缩影。

## 本讲小结

今天，我们完成了 go-tiny-claw 引擎架构中极其重要的一层抽象，并且通过真实的运行日志，揭示了驾驭大模型算力的底层逻辑。

同声传译的艺术：我们通过定义 LLMProvider，彻底隔离了底层 SDK 格式碎片化带来的灾难。无论是 OpenAI 还是 Claude 格式，最终都在引擎内部被收敛为极其干净的 schema.Message 序列。

兼容国内算力底座：得益于抽象层，我们在不修改任何核心逻辑的前提下，利用官方原生 SDK 无缝对接了国内的智谱大模型（GLM-4.5），在解决了网络与成本痛点的同时，保证了工业级调用的稳定性。

洞见“自适应推理”的必要性：通过对比开启和关闭慢思考（Thinking Phase）两份真实的执行日志，我们深刻体会到了“算力浪费”与“精准行动”之间的博弈。我们验证了在 Harness 架构中预留 EnableThinking 开关的前瞻性，并引出了业界前沿的 Adaptive Reasoning（自适应推理）概念。

现在，引擎的心跳强健，大脑清醒。但是，它的手脚依然是个 Mock 的“假肢”。

从下一讲开始，我们将迈入激动人心的第二章：极简工具与物理交互 (Action & Tools)。我们将抛弃这个测试用的 mockRegistry，亲手打造一套支持动态挂载的、强扩展性的真实 Tool Registry。更重要的是，我们将触碰 OpenClaw 的极简灵魂——实现能真正改变操作系统的 bash 原语。

注：本讲的示例代码，可以在这里下载。

## 思考题

在当前的 Provider 适配器中，我们使用的是阻塞式调用（例如：client.chat.completions.create(**params)）。这意味着如果大模型在进行 Phase 1 的长篇大论”思考”时，整个程序会阻塞卡死十多秒钟，直到模型把所有的推理和工具调用 JSON 全都生成完毕后，引擎才能一次性拿到结果。这在 CLI 工具体验中是非常差的。

实际生产中，各大模型的 API 均支持 Streaming（流式响应，Server-Sent Events）。大模型会一个字符一个字符地将文本推送过来，甚至 ToolCall 的 JSON 也是一块块吐出的。

结合你对 Python 异步编程（asyncio）和生成器（generator）的理解，如果要把我们的 LLMProvider 改造为支持流式返回的接口，它的函数签名应该怎么设计？引擎的 Main Loop 又该如何优雅地边接收流式字符边打印，同时还能正确拼接出最终完整的 schema.Message 呢？

欢迎在留言区写下你的接口设计草案。我们下一讲，开启工具与交互层！
