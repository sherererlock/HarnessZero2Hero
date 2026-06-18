from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..engine.session import Session
from ..provider.interface import LLMProvider
from ..schema.message import Message, ToolDefinition


@dataclass(frozen=True)
class Pricing:
    input_price: float
    output_price: float


# PricingModel 定义了不同大模型的计费标准 (单位: 美元/1M Tokens)
# 为了演示，这里硬编码了当前市面上几个主流模型的官方大致定价。
PRICING_MODEL: Dict[str, Pricing] = {
    "xiaomi/mimo-v2.5": Pricing(input_price=0.15, output_price=0.15),
}


class CostTracker(LLMProvider):
    """包装真实 LLMProvider 的装饰器，用于统计耗时和账单。"""

    def __init__(
        self,
        next_provider: LLMProvider,
        model_name: str,
        session: Optional[Session] = None,
    ) -> None:
        self.next_provider = next_provider
        self.model_name = model_name
        self.session = session

    def generate(
        self,
        messages: List[Message],
        available_tools: Optional[List[ToolDefinition]],
    ) -> Message:
        start_time = time.perf_counter()

        try:
            response_message = self.next_provider.generate(messages, available_tools)
        except Exception:
            latency = time.perf_counter() - start_time
            logging.exception("[Tracker] API 调用失败，耗时: %.3fs", latency)
            raise

        latency = time.perf_counter() - start_time
        usage = response_message.usage
        if usage is None:
            logging.warning("[Tracker] API 调用完成，但未返回 Usage 数据 | 耗时: %.3fs", latency)
            return response_message

        prompt_tokens = usage.prompt_tokens
        completion_tokens = usage.completion_tokens
        cost = self._calculate_cost(prompt_tokens, completion_tokens)

        logging.info(
            "[Tracker] API 调用完成 | 耗时: %.3fs | 输入: %d tk | 输出: %d tk | 花费: %.6f",
            latency,
            prompt_tokens,
            completion_tokens,
            cost,
        )

        if self.session is not None:
            self.session.record_usage(prompt_tokens, completion_tokens, cost)
            logging.info(
                "[Tracker] 当前会话 (%s) 累计花费: %.6f",
                self.session.id,
                self.session.total_cost_cny,
            )

        return response_message

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = PRICING_MODEL.get(self.model_name)
        if pricing is None:
            return 0.0

        return (
            prompt_tokens * pricing.input_price
            + completion_tokens * pricing.output_price
        ) / 1_000_000.0


def new_cost_tracker(
    next_provider: LLMProvider,
    model_name: str,
    session: Optional[Session] = None,
) -> CostTracker:
    return CostTracker(
        next_provider=next_provider,
        model_name=model_name,
        session=session,
    )


NewCostTracker = new_cost_tracker
PricingModel = PRICING_MODEL
