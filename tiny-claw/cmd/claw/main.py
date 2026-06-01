import logging
import os
import sys
from typing import List

# 让从脚本直接运行时也能找到 internal 包。
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from internal.engine.loop import AgentEngine
from internal.provider.openai import new_zhipu_openai_provider
from internal.provider.claude import new_zhipu_claude_provider
from internal.schema.message import ToolCall, ToolDefinition, ToolResult
from internal.tools.registry import Registry


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y/%m/%d %H:%M:%S",
)


class MockRegistry(Registry):
    """用于测试 Provider 工具调用能力的最小注册表。"""

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
                        }
                    },
                    "required": ["city"],
                },
            )
        ]

    def execute(self, call: ToolCall) -> ToolResult:
        logging.info("  -> [Mock 工具执行] 获取 %s 的天气中...", call.name)
        return ToolResult(
            tool_call_id=call.id,
            output="API 返回：今天是晴天，气温 25 度。",
            is_error=False,
        )


def main() -> None:
    work_dir = os.getcwd()

    # 这里可以切到 new_zhipu_claude_provider(...)；当前先默认走 OpenAI 兼容接口。
    # llm_provider = new_zhipu_openai_provider("xiaomi/mimo-v2.5-pro")
    llm_provider = new_zhipu_claude_provider("xiaomi/mimo-v2.5")
    registry = MockRegistry()
    engine = AgentEngine(llm_provider, registry, work_dir, enable_thinking=False)

    prompt = "我想去北京跑步，帮我查查天气适合吗？"
    try:
        engine.run(prompt)
    except Exception as exc:
        logging.error("引擎运行崩溃: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
