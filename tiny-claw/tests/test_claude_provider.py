import unittest

from internal.provider.claude import ClaudeProvider
from internal.schema.message import Message, Role, ToolCall, ToolDefinition


class _FakeContentBlock:
    def __init__(self, block_type: str, text: str = "", block_id: str = "", name: str = "", input_data=None):
        self.type = block_type
        self.text = text
        self.id = block_id
        self.name = name
        self.input = input_data if input_data is not None else {}


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeMessages:
    def __init__(self, response):
        self.response = response
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self.response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


class ClaudeProviderTests(unittest.TestCase):
    def test_generate_translates_messages_tools_and_response(self):
        response = _FakeResponse(
            [
                _FakeContentBlock("text", text="我先读取 README。"),
                _FakeContentBlock(
                    "tool_use",
                    block_id="tool_new",
                    name="read_file",
                    input_data={"path": "README.md"},
                ),
            ]
        )
        client = _FakeClient(response)
        provider = ClaudeProvider(model="glm-4.5", client=client)

        messages = [
            Message(role=Role.SYSTEM, content="你是助手"),
            Message(role=Role.USER, content="请看看仓库"),
            Message(
                role=Role.ASSISTANT,
                content="我先列目录。",
                tool_calls=[ToolCall(id="tool_hist", name="bash", arguments={"command": "ls"})],
            ),
            Message(role=Role.USER, content="README.md", tool_call_id="tool_hist"),
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
        request = client.messages.last_kwargs

        self.assertEqual("glm-4.5", request["model"])
        self.assertEqual(4096, request["max_tokens"])
        self.assertEqual("你是助手", request["system"])
        self.assertEqual("user", request["messages"][0]["role"])
        self.assertEqual("assistant", request["messages"][1]["role"])
        self.assertEqual("user", request["messages"][2]["role"])
        self.assertEqual("text", request["messages"][1]["content"][0]["type"])
        self.assertEqual("tool_use", request["messages"][1]["content"][1]["type"])
        self.assertEqual("tool_result", request["messages"][2]["content"][0]["type"])
        self.assertEqual("tool_hist", request["messages"][2]["content"][0]["tool_use_id"])
        self.assertEqual("read_file", request["tools"][0]["name"])

        self.assertEqual(Role.ASSISTANT, result.role)
        self.assertEqual("我先读取 README。", result.content)
        self.assertEqual("tool_new", result.tool_calls[0].id)
        self.assertEqual("read_file", result.tool_calls[0].name)
        self.assertEqual({"path": "README.md"}, result.tool_calls[0].arguments)


if __name__ == "__main__":
    unittest.main()
