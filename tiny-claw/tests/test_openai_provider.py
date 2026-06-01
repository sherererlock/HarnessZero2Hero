import unittest

from internal.schema.message import Message, Role, ToolCall, ToolDefinition
from internal.provider.openai import OpenAIProvider


class _FakeFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.type = "function"
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content: str, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


class _FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self.response


class _FakeChat:
    def __init__(self, response):
        self.completions = _FakeCompletions(response)


class _FakeClient:
    def __init__(self, response):
        self.chat = _FakeChat(response)


class OpenAIProviderTests(unittest.TestCase):
    def test_generate_translates_messages_tools_and_response(self):
        response = _FakeResponse(
            _FakeMessage(
                content="我先读文件。",
                tool_calls=[_FakeToolCall("call_new", "read_file", '{"path":"README.md"}')],
            )
        )
        client = _FakeClient(response)
        provider = OpenAIProvider(model="glm-4.5", client=client)

        messages = [
            Message(role=Role.SYSTEM, content="你是助手"),
            Message(role=Role.USER, content="请看看仓库"),
            Message(
                role=Role.ASSISTANT,
                content="我先列目录。",
                tool_calls=[ToolCall(id="call_hist", name="bash", arguments={"command": "ls"})],
            ),
            Message(role=Role.USER, content="README.md", tool_call_id="call_hist"),
        ]
        tools = [
            ToolDefinition(
                name="read_file",
                description="读取文件",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            )
        ]

        result = provider.generate(messages, tools)
        request = client.chat.completions.last_kwargs

        self.assertEqual("glm-4.5", request["model"])
        self.assertEqual("system", request["messages"][0]["role"])
        self.assertEqual("user", request["messages"][1]["role"])
        self.assertEqual("assistant", request["messages"][2]["role"])
        self.assertEqual("tool", request["messages"][3]["role"])
        self.assertEqual("call_hist", request["messages"][3]["tool_call_id"])
        self.assertEqual("bash", request["messages"][2]["tool_calls"][0]["function"]["name"])
        self.assertEqual('{"command":"ls"}', request["messages"][2]["tool_calls"][0]["function"]["arguments"])
        self.assertEqual("read_file", request["tools"][0]["function"]["name"])

        self.assertEqual(Role.ASSISTANT, result.role)
        self.assertEqual("我先读文件。", result.content)
        self.assertEqual("call_new", result.tool_calls[0].id)
        self.assertEqual("read_file", result.tool_calls[0].name)
        self.assertEqual({"path": "README.md"}, result.tool_calls[0].arguments)


if __name__ == "__main__":
    unittest.main()
