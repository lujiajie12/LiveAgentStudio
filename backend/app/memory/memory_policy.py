from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ORDER_PATTERN = re.compile(
    r"((?:订单号|单号|物流单号|运单号)[：:\s#-]*)([A-Za-z0-9-]{6,})"
)
ADDRESS_PATTERN = re.compile(
    r"((?:地址|收货地址|详细地址)[：:\s]*)([^，。；\n]{4,80})"
)
ID_CARD_PATTERN = re.compile(r"(?<!\d)(\d{17}[\dXx]|\d{15})(?!\d)")
NOISE_PATTERN = re.compile(r"^[0-9\W_]+$")
MATH_PATTERN = re.compile(r"^[0-9\.\+\-\*\/\(\)\s=？?]+$")
REPEATED_CHAR_PATTERN = re.compile(r"^(.)\1{2,}$")

GREETING_KEYWORDS = ("你好", "您好", "在吗", "hi", "hello", "哈哈")
PREFERENCE_KEYWORDS = ("偏好", "风格", "口吻", "以后都", "记住", "习惯", "更喜欢")
PRODUCT_FACT_KEYWORDS = (
    "商品",
    "产品",
    "规格",
    "参数",
    "卖点",
    "容量",
    "功率",
    "适合",
    "区别",
    "对比",
    "材质",
    "成分",
    "型号",
)
FAQ_KEYWORDS = (
    "运费",
    "发货",
    "物流",
    "售后",
    "保修",
    "退货",
    "退款",
    "换货",
    "赠品",
    "下单",
    "支付",
    "客服",
    "规则",
)
TEMPORAL_KEYWORDS = ("今天几号", "现在几点", "当前时间", "日期", "时间", "星期几")
EPHEMERAL_WEB_KEYWORDS = ("最新", "实时", "新闻", "天气", "汇率", "股价", "搜索", "查一下")
MEMORY_RECALL_META_KEYWORDS = ("刚刚", "刚才", "上一轮", "前面", "之前", "回顾", "回忆", "聊了什么", "几个问题")
NO_ANSWER_PREFIXES = (
    "抱歉，我暂时没有在知识库中找到足够信息",
    "抱歉，这个问题目前缺少足够依据",
)


@dataclass(slots=True)
class MemoryWriteDecision:
    should_store: bool
    reason: str
    messages: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryPolicy:
    """Long-term memory write policy for QA agent."""

    def __init__(self, max_chars: int = 240):
        self.max_chars = max_chars

    def build_write_decision(
        self,
        *,
        user_input: str,
        assistant_output: str,
        current_product_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryWriteDecision:
        normalized_query = self._normalize(user_input)
        normalized_answer = self._normalize(assistant_output)
        metadata = dict(metadata or {})

        if self._should_skip(normalized_query, normalized_answer, metadata):
            return MemoryWriteDecision(should_store=False, reason="policy_skip")

        memory_types = self._infer_memory_types(normalized_query, normalized_answer, current_product_id)
        sanitized_query = self._sanitize_and_summarize(normalized_query)
        sanitized_answer = self._sanitize_and_summarize(normalized_answer)

        if not sanitized_query and not sanitized_answer:
            return MemoryWriteDecision(should_store=False, reason="empty_after_sanitize")

        messages: list[dict[str, str]] = []
        if sanitized_query:
            messages.append({"role": "user", "content": sanitized_query})
        if sanitized_answer:
            messages.append({"role": "assistant", "content": sanitized_answer})

        summary_parts: list[str] = []
        if sanitized_query:
            summary_parts.append(f"recent_question: {sanitized_query}")
        if sanitized_answer:
            summary_parts.append(f"assistant_answer: {sanitized_answer}")

        decision_metadata = {
            **metadata,
            "memory_types": memory_types,
            "sanitized": True,
            "current_product_id": current_product_id or "",
            "memory_summary": " | ".join(summary_parts),
        }
        return MemoryWriteDecision(
            should_store=True,
            reason="store_relevant_qa_memory",
            messages=messages,
            metadata=decision_metadata,
        )

    def _should_skip(self, query: str, answer: str, metadata: dict[str, Any]) -> bool:
        lowered_query = query.lower()
        if not query:
            return True
        if NOISE_PATTERN.fullmatch(query) or REPEATED_CHAR_PATTERN.fullmatch(query):
            return True
        if MATH_PATTERN.fullmatch(query) and not any(token in query for token in ("商品", "产品")):
            return True
        if any(keyword in lowered_query for keyword in GREETING_KEYWORDS):
            return True
        # 记忆回溯类元问题不应再写回长期记忆，否则会污染后续 recall 结果。
        if metadata.get("tool_intent") == "memory_recall" or self._looks_memory_recall_meta_query(query):
            return True
        if any(keyword in query for keyword in TEMPORAL_KEYWORDS):
            return True
        if any(keyword in query for keyword in EPHEMERAL_WEB_KEYWORDS) and metadata.get("tools_used"):
            return True
        if any(answer.startswith(prefix) for prefix in NO_ANSWER_PREFIXES) and not self._looks_business_relevant(query):
            return True
        return False

    def _infer_memory_types(self, query: str, answer: str, current_product_id: str | None) -> list[str]:
        kinds: list[str] = ["recent_question"]
        if any(keyword in query for keyword in PREFERENCE_KEYWORDS):
            kinds.append("operator_preference")
        if any(keyword in query for keyword in PRODUCT_FACT_KEYWORDS) or current_product_id:
            kinds.append("product_fact")
        if any(keyword in query for keyword in FAQ_KEYWORDS):
            kinds.append("faq")
        if "喜欢" in answer or "偏好" in answer:
            kinds.append("preference_signal")
        normalized: list[str] = []
        for item in kinds:
            if item not in normalized:
                normalized.append(item)
        return normalized

    def _looks_business_relevant(self, query: str) -> bool:
        return any(keyword in query for keyword in (*PRODUCT_FACT_KEYWORDS, *FAQ_KEYWORDS, *PREFERENCE_KEYWORDS))

    def _looks_memory_recall_meta_query(self, query: str) -> bool:
        return any(keyword in query for keyword in MEMORY_RECALL_META_KEYWORDS) and any(
            token in query for token in ("问题", "回答", "回复", "对话", "内容")
        )

    def _sanitize_and_summarize(self, text: str) -> str:
        sanitized = self._sanitize(text)
        if len(sanitized) <= self.max_chars:
            return sanitized
        return sanitized[: self.max_chars - 3].rstrip() + "..."

    def _sanitize(self, text: str) -> str:
        sanitized = self._normalize(text)
        sanitized = PHONE_PATTERN.sub("[PHONE]", sanitized)
        sanitized = EMAIL_PATTERN.sub("[EMAIL]", sanitized)
        sanitized = ORDER_PATTERN.sub(r"\1[ORDER_ID]", sanitized)
        sanitized = ADDRESS_PATTERN.sub(r"\1[ADDRESS]", sanitized)
        sanitized = ID_CARD_PATTERN.sub("[ID_CARD]", sanitized)
        return sanitized

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()
