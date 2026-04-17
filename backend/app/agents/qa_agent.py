import json
import logging
import re
from datetime import datetime
from inspect import isawaitable
from time import perf_counter
from typing import TYPE_CHECKING, Any, Protocol
from zoneinfo import ZoneInfo

import httpx

from app.agents.base import BaseAgent
from app.core.config import settings
from app.core.observability import record_timed_tool_call
from app.graph.state import LiveAgentState, StatePatch
from app.rag.query_constraints import extract_catalog_attributes, extract_query_budget, normalize_budget_constraint

if TYPE_CHECKING:
    from app.memory.qa_agent_memory_hook import QAMemoryHook

try:
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:  # pragma: no cover
    HumanMessage = None
    SystemMessage = None

try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover
    ChatOpenAI = None


logger = logging.getLogger(__name__)

QA_NO_ANSWER_TEXT = "抱歉，我暂时没有在知识库中找到足够信息，建议联系人工客服进一步确认。"
QA_LOW_CONFIDENCE_TEXT = "抱歉，这个问题目前缺少足够依据，建议联系人工客服进一步确认。"
CJK_CHARS = r"\u3400-\u4dbf\u4e00-\u9fff"
CJK_CLOSE_PUNCT = r"，。！？；：、）》」』】"
CJK_OPEN_PUNCT = r"（《「『【"


DATETIME_TOOL_NAME = "current_datetime"
WEB_SEARCH_TOOL_NAME = "google_search"
TOOL_INTENT_NONE = "none"
TOOL_INTENT_DATETIME = "datetime"
TOOL_INTENT_MEMORY_RECALL = "memory_recall"
TOOL_INTENT_WEB_SEARCH = "web_search"
VALID_TOOL_INTENTS = {
    TOOL_INTENT_NONE,
    TOOL_INTENT_DATETIME,
    TOOL_INTENT_MEMORY_RECALL,
    TOOL_INTENT_WEB_SEARCH,
}
DATETIME_TOOL_PATTERNS = (
    "\u4eca\u5929\u51e0\u53f7",
    "\u4eca\u5929\u51e0\u6708\u51e0\u53f7",
    "\u4eca\u5929\u5468\u51e0",
    "\u4eca\u5929\u662f\u5468\u51e0",
    "\u4eca\u5929\u661f\u671f\u51e0",
    "\u4eca\u5929\u661f\u671f\u51e0\u554a",
    "\u660e\u5929\u51e0\u53f7",
    "\u660e\u5929\u5468\u51e0",
    "\u660e\u5929\u662f\u5468\u51e0",
    "\u660e\u5929\u661f\u671f\u51e0",
    "\u660e\u5929\u662f\u661f\u671f\u51e0",
    "\u660e\u5929\u662f\u4ec0\u4e48\u65e5",
    "\u540e\u5929\u51e0\u53f7",
    "\u540e\u5929\u5468\u51e0",
    "\u540e\u5929\u662f\u5468\u51e0",
    "\u540e\u5929\u661f\u671f\u51e0",
    "\u5927\u540e\u5929",
    "\u4e0b\u5468",
    "\u4e0b\u4e0b\u5468",
    "\u793c\u62dc\u51e0",
    "\u4eca\u5929\u793c\u62dc\u51e0",
    "\u73b0\u5728\u51e0\u70b9",
    "\u73b0\u5728\u51e0\u70b9\u4e86",
    "\u73b0\u5728\u51e0\u70b9\u51e0\u5206",
    "\u73b0\u5728\u51e0\u53f7",
    "\u4eca\u5929\u662f\u51e0\u53f7",
    "\u4eca\u5929\u662f\u51e0\u6708\u51e0\u53f7",
    "\u73b0\u5728\u662f\u4ec0\u4e48\u65f6\u95f4",
    "\u73b0\u5728\u662f\u51e0\u70b9",
    "\u5f53\u524d\u65e5\u671f",
    "\u5f53\u524d\u65f6\u95f4",
    "today date",
    "current date",
    "current time",
    "what date is it",
    "what time is it",
    "tomorrow",
    "day after tomorrow",
)
WEB_SEARCH_PATTERNS = (
    "\u6700\u65b0",
    "\u5b9e\u65f6",
    "\u65b0\u95fb",
    "\u5b98\u7f51",
    "\u67e5\u4e00\u4e0b",
    "\u641c\u4e00\u4e0b",
    "\u5e2e\u6211\u67e5",
    "\u4e0a\u7f51\u67e5",
    "\u8054\u7f51\u67e5",
    "\u5929\u6c14",
    "\u6c47\u7387",
    "\u80a1\u4ef7",
    "\u91d1\u4ef7",
    "\u6cb9\u4ef7",
    "\u884c\u60c5",
    "\u4eca\u65e5",
    "\u4eca\u5929\u65b0\u95fb",
    "latest",
    "current",
    "real-time",
    "realtime",
    "news",
    "search",
    "google",
    "website",
    "official site",
)
WEEKDAY_NAMES = (
    "\u661f\u671f\u4e00",
    "\u661f\u671f\u4e8c",
    "\u661f\u671f\u4e09",
    "\u661f\u671f\u56db",
    "\u661f\u671f\u4e94",
    "\u661f\u671f\u516d",
    "\u661f\u671f\u65e5",
)
MEMORY_RECALL_HINTS = (
    "刚刚",
    "刚才",
    "上一轮",
    "上一个",
    "上个",
    "前面",
    "之前",
    "记得",
    "回顾",
    "回忆",
)
MEMORY_RECALL_TARGETS = (
    "我问",
    "问你的",
    "问题",
    "提问",
    "你说",
    "你回答",
    "回答了",
    "回复",
    "答复",
    "聊了什么",
    "聊到什么",
    "对话",
    "内容",
)
MEMORY_RECALL_QUESTION_TARGETS = ("我问", "问你的", "问题", "提问")
MEMORY_RECALL_ANSWER_TARGETS = ("你说", "你回答", "回答", "回答了", "回复", "答复")
MEMORY_RECALL_DIALOGUE_TARGETS = ("对话", "聊了什么", "聊到什么", "内容")
MEMORY_RECALL_LIST_HINTS = (
    "几个",
    "哪些",
    "哪几个",
    "都有哪些",
    "列出来",
    "展示一下",
    "列表",
    "最近几次",
    "最近几个",
    "前面几个",
    "前面问过的几个",
    "分别是什么",
)
MEMORY_RECALL_ALL_HINTS = ("全部", "所有", "都")
MEMORY_RECALL_EXPLICIT_PATTERNS = (
    "刚刚我问你的是什么问题",
    "刚才我问你的是什么问题",
    "上一轮我问的是什么问题",
    "上一个问题是什么",
    "你刚刚是怎么回答的",
    "你刚才是怎么回答的",
    "上一轮你怎么回答的",
    "你还记得我刚刚问了什么吗",
    "你还记得我之前问过什么吗",
    "我们刚刚聊了什么",
    "我们刚才聊了什么",
)
MEMORY_RECALL_COUNT_PATTERN = re.compile(r"([0-9一二两三四五六七八九十]+)\s*(?:个|条|轮|次)")
CHINESE_NUMBER_MAP = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


KNOWLEDGE_FOCUS_GENERAL = "general"
KNOWLEDGE_FOCUS_PRODUCT_NAME = "product_name"
KNOWLEDGE_FOCUS_MODEL = "model"
KNOWLEDGE_FOCUS_BRAND = "brand"
KNOWLEDGE_FOCUS_MATERIAL = "material"
KNOWLEDGE_FOCUS_PRICE = "price"
KNOWLEDGE_FOCUS_CATEGORY = "category"
KNOWLEDGE_FOCUS_AUDIENCE = "audience"
KNOWLEDGE_FOCUS_FEATURES = "features"
KNOWLEDGE_FOCUS_SPECS = "specs"
VALID_KNOWLEDGE_FOCUS_FIELDS = {
    KNOWLEDGE_FOCUS_GENERAL,
    KNOWLEDGE_FOCUS_PRODUCT_NAME,
    KNOWLEDGE_FOCUS_MODEL,
    KNOWLEDGE_FOCUS_BRAND,
    KNOWLEDGE_FOCUS_MATERIAL,
    KNOWLEDGE_FOCUS_PRICE,
    KNOWLEDGE_FOCUS_CATEGORY,
    KNOWLEDGE_FOCUS_AUDIENCE,
    KNOWLEDGE_FOCUS_FEATURES,
    KNOWLEDGE_FOCUS_SPECS,
}
KNOWLEDGE_FOCUS_FALLBACK_HINTS = {
    KNOWLEDGE_FOCUS_PRODUCT_NAME: ("商品名称", "名称", "叫什", "哪款"),
    KNOWLEDGE_FOCUS_MODEL: ("商品型号", "型号", "型号是", "什么型号"),
    KNOWLEDGE_FOCUS_BRAND: ("品牌", "牌子", "什么牌"),
    KNOWLEDGE_FOCUS_MATERIAL: ("材质", "面料", "什么做的", "什么材质", "主要材质", "填充"),
    KNOWLEDGE_FOCUS_PRICE: ("价格", "多少钱", "价位", "直播价", "价带"),
    KNOWLEDGE_FOCUS_CATEGORY: ("类目", "品类", "属于什么类"),
    KNOWLEDGE_FOCUS_AUDIENCE: ("适合", "适用人群", "适配人群", "适合谁", "哪类人"),
    KNOWLEDGE_FOCUS_FEATURES: ("卖点", "亮点", "特点", "优势"),
    KNOWLEDGE_FOCUS_SPECS: ("规格", "参数", "尺寸", "容量", "功率"),
}
KNOWLEDGE_FOCUS_LINE_PATTERNS = {
    KNOWLEDGE_FOCUS_PRODUCT_NAME: (
        re.compile(r"(?:商品名称|名称)[:：]\s*(?P<value>.+)"),
    ),
    KNOWLEDGE_FOCUS_MODEL: (
        re.compile(r"(?:商品型号|型号)[:：]\s*(?P<value>.+)"),
    ),
    KNOWLEDGE_FOCUS_BRAND: (
        re.compile(r"品牌[:：]\s*(?P<value>.+)"),
    ),
    KNOWLEDGE_FOCUS_MATERIAL: (
        re.compile(r"(?:主要材质|材质|面料|填充|机身材质|内胆材质|杆体材质)[:：]\s*(?P<value>.+)"),
    ),
    KNOWLEDGE_FOCUS_PRICE: (
        re.compile(r"(?:直播价带|价格|售价)[:：]\s*(?P<value>.+)"),
    ),
    KNOWLEDGE_FOCUS_CATEGORY: (
        re.compile(r"类目[:：]\s*(?P<value>.+)"),
    ),
    KNOWLEDGE_FOCUS_AUDIENCE: (
        re.compile(r"(?:适配人群|适合人群|适合谁)[:：]?\s*(?P<value>.+)"),
    ),
    KNOWLEDGE_FOCUS_FEATURES: (
        re.compile(r"(?:功能亮点|核心卖点|卖点|亮点)[:：]\s*(?P<value>.+)"),
    ),
    KNOWLEDGE_FOCUS_SPECS: (
        re.compile(r"(?:规格参数|规格|参数|容量|尺寸|功率)[:：]\s*(?P<value>.+)"),
    ),
}


class QAAgentLLM(Protocol):
    # 调用支持结构化输出的 LLM 能力。
    async def ainvoke_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        ...

    # 调用纯文本输出的 LLM 能力。
    async def ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
        ...


class QAWebSearchClient(Protocol):
    async def search(self, query: str) -> dict[str, Any]:
        ...


class ChatOpenAIJsonClient:
    # 初始化通用 LLM 客户端，供 QA、Script、Analyst 复用。
    def __init__(self, label: str = "agent"):
        self._client = None
        self.label = label
        api_key = settings.LLM_API_KEY or settings.OPENAI_API_KEY
        base_url = settings.LLM_BASE_URL or settings.OPENAI_BASE_URL
        model = settings.QA_MODEL or settings.LLM_MODEL or settings.ROUTER_MODEL
        if api_key and ChatOpenAI is not None:
            self._client = ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=0,
            )

    # 从模型回复中尽量提取出 JSON 载荷，兼容 fenced code block 和前后缀噪声。
    def _extract_json_payload(self, content: str) -> dict[str, Any]:
        candidate = content.strip()
        if not candidate:
            raise json.JSONDecodeError("empty response", candidate, 0)

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        fenced = candidate.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        if fenced != candidate:
            try:
                return json.loads(fenced)
            except json.JSONDecodeError:
                pass

        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(candidate[start : end + 1])

        raise json.JSONDecodeError("no json object found", candidate, 0)

    # 直接向底层 LLM 请求纯文本结果。
    async def ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
        if self._client is None or SystemMessage is None or HumanMessage is None:
            raise RuntimeError("qa llm client unavailable")

        started = perf_counter()
        try:
            response = await self._client.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
        except Exception:
            await record_timed_tool_call(
                f"{self.label}_llm_text",
                started_at=started,
                node_name=self.label,
                category="llm",
                status="degraded",
            )
            raise
        content = str(response.content).strip()
        await record_timed_tool_call(
            f"{self.label}_llm_text",
            started_at=started,
            node_name=self.label,
            category="llm",
            output_summary=content[:200],
            status="ok",
        )
        return content

    # 基于纯文本调用结果再做一次 JSON 提取。
    async def ainvoke_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return self._extract_json_payload(await self.ainvoke_text(system_prompt, user_prompt))


class SerpApiGoogleSearchClient:
    async def search(self, query: str) -> dict[str, Any]:
        if not settings.SERPAPI_API_KEY:
            raise RuntimeError("serpapi api key unavailable")

        params = {
            "engine": settings.SERPAPI_ENGINE,
            "q": query,
            "api_key": settings.SERPAPI_API_KEY,
            "hl": settings.SERPAPI_HL,
            "gl": settings.SERPAPI_GL,
            "num": settings.SERPAPI_NUM_RESULTS,
        }

        async with httpx.AsyncClient(timeout=settings.SERPAPI_TIMEOUT_SECONDS) as client:
            response = await client.get(settings.SERPAPI_BASE_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        answer_box = payload.get("answer_box") or {}
        knowledge_graph = payload.get("knowledge_graph") or {}
        organic_results = []
        for item in payload.get("organic_results", [])[: settings.SERPAPI_NUM_RESULTS]:
            organic_results.append(
                {
                    "title": str(item.get("title", "")).strip(),
                    "link": str(item.get("link", "")).strip(),
                    "snippet": str(item.get("snippet", "")).strip(),
                    "source": str(item.get("source", "")).strip(),
                    "position": item.get("position"),
                }
            )

        return {
            "query": query,
            "answer_box": {
                "title": str(answer_box.get("title", "")).strip(),
                "answer": str(answer_box.get("answer", "") or answer_box.get("snippet", "")).strip(),
                "link": str(answer_box.get("link", "")).strip(),
            },
            "knowledge_graph": {
                "title": str(knowledge_graph.get("title", "")).strip(),
                "type": str(knowledge_graph.get("type", "")).strip(),
                "description": str(knowledge_graph.get("description", "")).strip(),
                "website": str(knowledge_graph.get("website", "")).strip(),
            },
            "organic_results": organic_results,
            "search_metadata": {
                "id": str((payload.get("search_metadata") or {}).get("id", "")).strip(),
                "status": str((payload.get("search_metadata") or {}).get("status", "")).strip(),
            },
        }


class QAAgent(BaseAgent):
    name = "qa"

    # 初始化 QA 智能体，注入检索管线和可替换的 LLM 客户端。
    def __init__(self, retrieval_pipeline=None, llm_client: QAAgentLLM | None = None):
        self.pipeline = retrieval_pipeline
        self.llm_client = llm_client or ChatOpenAIJsonClient()
        self.web_search_client = SerpApiGoogleSearchClient()
        self.high_frequency_repository = None
        self.memory_hook: QAMemoryHook | None = None
        self.tools = {
            DATETIME_TOOL_NAME: self._get_current_datetime_tool,
            WEB_SEARCH_TOOL_NAME: self._google_search_tool,
        }

    # 允许在容器装配阶段延迟注入长期高频问题仓库。
    def bind_high_frequency_repository(self, repository) -> None:
        self.high_frequency_repository = repository

    def bind_web_search_client(self, client: QAWebSearchClient) -> None:
        self.web_search_client = client

    def bind_memory_hook(self, hook: "QAMemoryHook") -> None:
        self.memory_hook = hook

    def _is_datetime_query(self, query: str) -> bool:
        normalized = str(query or "").strip()
        lowered = normalized.lower()
        return any(token in normalized for token in DATETIME_TOOL_PATTERNS) or any(
            token in lowered for token in DATETIME_TOOL_PATTERNS
        )

    def _should_use_web_search(self, query: str) -> bool:
        normalized = str(query or "").strip()
        lowered = normalized.lower()
        if self._is_datetime_query(normalized):
            return False
        if not settings.SERPAPI_API_KEY:
            return False
        return any(token in normalized for token in WEB_SEARCH_PATTERNS) or any(
            token in lowered for token in WEB_SEARCH_PATTERNS
        )

    def _normalize_tool_intent(self, tool_intent: Any) -> str:
        normalized = str(tool_intent or TOOL_INTENT_NONE).strip().lower()
        if normalized in VALID_TOOL_INTENTS:
            return normalized
        return TOOL_INTENT_NONE

    # 以 router 输出的标准 tool_intent 为准，不再用关键词兜底。
    def _resolve_tool_intent(self, state: LiveAgentState) -> str:
        normalized = self._normalize_tool_intent(state.get("tool_intent"))
        if normalized in VALID_TOOL_INTENTS:
            return normalized
        return TOOL_INTENT_NONE

    # 把 LLM 或 fallback 产出的字段意图规整成标准 knowledge_focus，后续生成与降级都走同一份协议。
    def _normalize_knowledge_focus(self, payload: Any) -> dict[str, Any]:
        alias_map = {
            "name": KNOWLEDGE_FOCUS_PRODUCT_NAME,
            "product": KNOWLEDGE_FOCUS_PRODUCT_NAME,
            "product_model": KNOWLEDGE_FOCUS_MODEL,
            "sku": KNOWLEDGE_FOCUS_MODEL,
            "materials": KNOWLEDGE_FOCUS_MATERIAL,
            "price_band": KNOWLEDGE_FOCUS_PRICE,
            "people": KNOWLEDGE_FOCUS_AUDIENCE,
            "feature": KNOWLEDGE_FOCUS_FEATURES,
            "selling_points": KNOWLEDGE_FOCUS_FEATURES,
            "spec": KNOWLEDGE_FOCUS_SPECS,
            "parameters": KNOWLEDGE_FOCUS_SPECS,
        }
        raw_focus_fields = []
        reason = ""
        if isinstance(payload, dict):
            raw_focus_fields = payload.get("focus_fields", [])
            reason = str(payload.get("reason", "")).strip()
        elif isinstance(payload, (list, tuple, set)):
            raw_focus_fields = list(payload)
        elif payload:
            raw_focus_fields = [payload]

        if isinstance(raw_focus_fields, str):
            raw_focus_fields = [raw_focus_fields]

        focus_fields: list[str] = []
        for raw_item in raw_focus_fields:
            normalized = str(raw_item or "").strip().lower()
            normalized = alias_map.get(normalized, normalized)
            if normalized in VALID_KNOWLEDGE_FOCUS_FIELDS and normalized not in focus_fields:
                focus_fields.append(normalized)

        if not focus_fields:
            focus_fields = [KNOWLEDGE_FOCUS_GENERAL]

        if KNOWLEDGE_FOCUS_GENERAL in focus_fields and len(focus_fields) > 1:
            focus_fields = [item for item in focus_fields if item != KNOWLEDGE_FOCUS_GENERAL]

        return {
            "focus_fields": focus_fields[:3],
            "reason": reason,
        }

    # LLM-first 的字段意图规划：先让模型判断用户问的是材质/型号/品牌等哪类信息，避免把所有问法写死。
    async def _plan_knowledge_focus(
        self,
        state: LiveAgentState,
        rewritten_query: str,
        retrieved_docs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        query = str(state.get("user_input", "")).strip()
        fallback = self._fallback_knowledge_focus(query)
        doc_titles = []
        for doc in retrieved_docs[:3]:
            metadata = dict(doc.get("metadata", {}) or {})
            title = (
                str(metadata.get("section_title") or "").strip()
                or str(metadata.get("product_name") or "").strip()
                or str(doc.get("doc_id") or "").strip()
            )
            if title:
                doc_titles.append(title)

        system_prompt = (
            "You are a live-commerce knowledge focus planner. "
            "Determine which product field the user is actually asking about. "
            "Allowed focus_fields: general, product_name, model, brand, material, price, category, audience, features, specs. "
            "If the user asks for a narrow fact such as material or model, return only that field. "
            "If the user asks for an overall introduction, overview, comparison, or multiple broad points, return [\"general\"]. "
            'Return strict JSON only: {"focus_fields":["..."],"reason":"..."}'
        )
        user_prompt = json.dumps(
            {
                "original_user_input": query,
                "rewritten_query": rewritten_query,
                "candidate_doc_titles": doc_titles,
            },
            ensure_ascii=False,
        )
        try:
            payload = await self.llm_client.ainvoke_json(system_prompt, user_prompt)
        except Exception:
            return fallback
        normalized = self._normalize_knowledge_focus(payload)
        if normalized.get("focus_fields") == [KNOWLEDGE_FOCUS_GENERAL] and fallback.get("focus_fields") != [KNOWLEDGE_FOCUS_GENERAL]:
            return fallback
            # 如果模型漏判成 general，但 query 里已经很明显是字段型问题，就用保守 fallback 把目标字段拉回来。
            return fallback
        return normalized

    # 只有主路径使用 LLM 规划；这里保留一层极薄的兜底，防止模型不可用时材质/型号类问题退化成整段概览。
    def _fallback_knowledge_focus(self, query: str) -> dict[str, Any]:
        normalized = str(query or "").strip().lower()
        focus_fields: list[str] = []
        for field, hints in KNOWLEDGE_FOCUS_FALLBACK_HINTS.items():
            if any(hint in normalized for hint in hints):
                focus_fields.append(field)
        if not focus_fields:
            focus_fields = [KNOWLEDGE_FOCUS_GENERAL]
        return {
            "focus_fields": focus_fields[:3],
            "reason": "heuristic_fallback",
        }

    def _normalize_catalog_line(self, raw_line: str) -> str:
        line = re.sub(r"\s+", " ", str(raw_line or "")).strip()
        line = line.lstrip("- ").strip()
        line = line.lstrip("> ").strip()
        return line

    def _collect_catalog_lines(self, retrieved_docs: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []
        for doc in retrieved_docs[:3]:
            for raw_line in str(doc.get("content", "")).splitlines():
                line = self._normalize_catalog_line(raw_line)
                if not line or line.startswith("#"):
                    continue
                lines.append(line)
        return lines

    def _merge_catalog_metadata(self, retrieved_docs: list[dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for doc in retrieved_docs[:3]:
            metadata = dict(doc.get("metadata", {}) or {})
            metadata.update(extract_catalog_attributes(doc.get("content", ""), metadata))
            for key, value in metadata.items():
                if key not in merged and value not in (None, ""):
                    merged[key] = value
        return merged

    def _focus_subject(self, retrieved_docs: list[dict[str, Any]]) -> str:
        metadata = self._merge_catalog_metadata(retrieved_docs)
        title = (
            str(metadata.get("product_name") or "").strip()
            or str(metadata.get("section_title") or "").strip()
        )
        title = re.sub(r"^#+\s*", "", title).strip()
        return title or "这款商品"

    def _extract_focus_values(self, focus_field: str, retrieved_docs: list[dict[str, Any]]) -> list[str]:
        metadata = self._merge_catalog_metadata(retrieved_docs)
        lines = self._collect_catalog_lines(retrieved_docs)
        candidate_values: list[str] = []

        direct_values = {
            KNOWLEDGE_FOCUS_PRODUCT_NAME: (
                metadata.get("product_name"),
                metadata.get("section_title"),
            ),
            KNOWLEDGE_FOCUS_MODEL: (
                metadata.get("sku"),
                metadata.get("model"),
                metadata.get("product_model"),
            ),
            KNOWLEDGE_FOCUS_BRAND: (
                metadata.get("brand"),
            ),
            KNOWLEDGE_FOCUS_PRICE: (
                metadata.get("price_band_text"),
            ),
            KNOWLEDGE_FOCUS_CATEGORY: (
                metadata.get("category"),
            ),
            KNOWLEDGE_FOCUS_AUDIENCE: (
                metadata.get("audience"),
            ),
        }
        for raw_value in direct_values.get(focus_field, ()):
            value = self._normalize_catalog_line(str(raw_value or ""))
            if value:
                candidate_values.append(value)

        for line in lines:
            for pattern in KNOWLEDGE_FOCUS_LINE_PATTERNS.get(focus_field, ()):
                match = pattern.search(line)
                if not match:
                    continue
                value = self._normalize_catalog_line(match.group("value"))
                if value:
                    candidate_values.append(value)

        deduped: list[str] = []
        seen: set[str] = set()
        for value in candidate_values:
            lookup = re.sub(r"\s+", "", value).lower()
            if lookup and lookup not in seen:
                seen.add(lookup)
                deduped.append(value)
        return deduped[:3]

    def _render_focused_fallback_answer(
        self,
        focus_fields: list[str],
        retrieved_docs: list[dict[str, Any]],
    ) -> str:
        subject = self._focus_subject(retrieved_docs)
        field_labels = {
            KNOWLEDGE_FOCUS_PRODUCT_NAME: "商品名称",
            KNOWLEDGE_FOCUS_MODEL: "商品型号",
            KNOWLEDGE_FOCUS_BRAND: "品牌",
            KNOWLEDGE_FOCUS_MATERIAL: "主要材质",
            KNOWLEDGE_FOCUS_PRICE: "直播价带",
            KNOWLEDGE_FOCUS_CATEGORY: "类目",
            KNOWLEDGE_FOCUS_AUDIENCE: "适配人群",
            KNOWLEDGE_FOCUS_FEATURES: "功能亮点",
            KNOWLEDGE_FOCUS_SPECS: "规格参数",
        }

        answer_parts: list[str] = []
        for focus_field in focus_fields:
            values = self._extract_focus_values(focus_field, retrieved_docs)
            if not values:
                answer_parts.append(f"根据当前命中的知识片段，暂时没有找到 {subject} 的{field_labels[focus_field]}信息。")
                continue
            if focus_field == KNOWLEDGE_FOCUS_PRODUCT_NAME:
                answer_parts.append(f"根据知识库，这款商品的商品名称是 {values[0]}。")
            elif focus_field == KNOWLEDGE_FOCUS_MODEL:
                answer_parts.append(f"根据知识库，{subject}的商品型号是 {values[0]}。")
            elif focus_field == KNOWLEDGE_FOCUS_BRAND:
                answer_parts.append(f"根据知识库，{subject}的品牌是 {values[0]}。")
            elif focus_field == KNOWLEDGE_FOCUS_MATERIAL:
                answer_parts.append(f"根据知识库，{subject}的主要材质是 {values[0]}。")
            elif focus_field == KNOWLEDGE_FOCUS_PRICE:
                answer_parts.append(f"根据知识库，{subject}的直播价带是 {values[0]}。")
            elif focus_field == KNOWLEDGE_FOCUS_CATEGORY:
                answer_parts.append(f"根据知识库，{subject}属于 {values[0]}。")
            elif focus_field == KNOWLEDGE_FOCUS_AUDIENCE:
                answer_parts.append(f"根据知识库，{subject}更适合 {values[0]}。")
            elif focus_field == KNOWLEDGE_FOCUS_FEATURES:
                answer_parts.append(f"根据知识库，{subject}的主要亮点包括：{'；'.join(values[:2])}。")
            elif focus_field == KNOWLEDGE_FOCUS_SPECS:
                answer_parts.append(f"根据知识库，{subject}的相关规格信息是：{'；'.join(values[:2])}。")
        return "".join(answer_parts).strip()

    # 识别“刚刚我问了什么/你上一轮怎么回答的”这类回溯型问题。
    def _is_memory_recall_query(self, query: str) -> bool:
        normalized = str(query or "").strip().lower()
        if any(pattern in normalized for pattern in MEMORY_RECALL_EXPLICIT_PATTERNS):
            return True
        return any(token in normalized for token in MEMORY_RECALL_HINTS) and any(
            token in normalized for token in MEMORY_RECALL_TARGETS
        )

    def _get_current_datetime_tool(self, *, query: str = "") -> dict[str, Any]:
        """返回真实的当前日期时间，不做任何相对日期计算。相对日期由LLM根据用户问题自行计算。"""
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        return {
            "timezone": "Asia/Shanghai",
            "iso": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "weekday": WEEKDAY_NAMES[now.weekday()],
        }

    async def _google_search_tool(self, *, query: str) -> dict[str, Any]:
        return await self.web_search_client.search(query)

    async def _run_tool(self, tool_name: str, *, query: str) -> dict[str, Any]:
        tool = self.tools[tool_name]
        started = perf_counter()
        payload = tool(query=query)
        if isawaitable(payload):
            payload = await payload
        await record_timed_tool_call(
            tool_name,
            started_at=started,
            node_name="qa",
            category="tool",
            input_payload={"query": query},
            output_summary=json.dumps(payload, ensure_ascii=False)[:200],
            status="ok",
        )
        return payload

    async def _generate_datetime_answer(
        self,
        state: LiveAgentState,
        tool_payload: dict[str, Any],
    ) -> str:
        """用LLM根据用户问题和当前真实时间生成日期回答。完全由LLM处理相对日期计算。"""
        started = perf_counter()
        system_prompt = (
            "你是日期时间助手。根据用户的问题给出简洁、准确的自然语言回答。\n"
            "规则：\n"
            "1. 只回答用户实际问的内容，不要机械地附带其他信息。\n"
            "2. 如果用户问的是相对日期（明天/后天/下周等），计算并回答目标日期。\n"
            "3. 如果用户只问星期，就只回答星期；如果只问日期，就只回答日期。\n"
            "4. 不要每次都加上'当前时间是XX:XX'，除非用户明确问了时间。\n"
            "5. 用中文自然语言简洁回答，不要输出计算过程或JSON。\n"
            "示例：\n"
            "  问：明天是哪一天？答：明天是2026年4月15日，星期三。\n"
            "  问：后天星期几？答：后天是星期三。\n"
            "  问：八天后是哪一天？答：八天后是2026年4月22日，星期三。\n"
            "  问：下周一是几号？答：下周一是4月21日。\n"
            "  问：今天几号？答：今天是4月14日。\n"
            "  问：现在几点？答：现在是下午6点21分。\n"
        )
        user_prompt = json.dumps(
            {
                "用户问题": state.get("user_input", ""),
                "当前时间": {
                    "timezone": tool_payload["timezone"],
                    "日期": tool_payload["date"],
                    "时间": tool_payload["time"],
                    "年": tool_payload["year"],
                    "月": tool_payload["month"],
                    "日": tool_payload["day"],
                    "星期": tool_payload["weekday"],
                },
            },
            ensure_ascii=False,
        )

        try:
            answer = (await self.llm_client.ainvoke_text(system_prompt, user_prompt)).strip()
        except Exception as exc:
            logger.warning(
                "qa_datetime_generation_failed trace_id=%s error=%s",
                state.get("trace_id"),
                exc,
            )
            await record_timed_tool_call(
                "qa_datetime_answer_generation",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"user_input": state.get("user_input")},
                output_summary=str(exc),
                status="degraded",
            )
            # Fallback: keep the tool response usable even when text generation is unavailable.
            answer = (
                f"今天是{tool_payload['weekday']}。"
                f"当前时间是 {tool_payload['date']} {tool_payload['time']}（{tool_payload['timezone']}）。"
            )

        await record_timed_tool_call(
            "qa_datetime_answer_generation",
            started_at=started,
            node_name="qa",
            category="llm",
            input_payload={"user_input": state.get("user_input")},
            output_summary=answer[:200],
            status="ok",
        )
        return answer

    # 去掉当前这一轮的提问，避免“刚刚我问了什么”时把当前问题自己回给自己。
    def _memory_turns_without_current_query(self, state: LiveAgentState) -> list[dict[str, str]]:
        current_query = str(state.get("user_input", "")).strip()
        skipped_current = False
        turns: list[dict[str, str]] = []
        for item in reversed(list(state.get("short_term_memory", []))):
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if not role or not content:
                continue
            if not skipped_current and role == "user" and content == current_query:
                skipped_current = True
                continue
            turns.append({"role": role, "content": content})
        turns.reverse()
        return turns

    def _memory_recall_focus(self, query: str) -> str:
        normalized = str(query or "").strip().lower()
        if any(token in normalized for token in MEMORY_RECALL_QUESTION_TARGETS):
            return "question"
        if any(token in normalized for token in MEMORY_RECALL_ANSWER_TARGETS):
            return "answer"
        if any(token in normalized for token in MEMORY_RECALL_DIALOGUE_TARGETS):
            return "dialogue"
        return "dialogue"

    # 解析“3个问题/两轮回答”这类数量表达，统一给回溯逻辑做上限控制。
    def _parse_recall_count(self, raw_count: str) -> int:
        token = str(raw_count or "").strip()
        if not token:
            return 0
        if token.isdigit():
            return int(token)
        if token == "十":
            return 10
        if len(token) == 2 and token[0] == "十":
            return 10 + CHINESE_NUMBER_MAP.get(token[1], 0)
        if len(token) == 2 and token[1] == "十":
            return CHINESE_NUMBER_MAP.get(token[0], 0) * 10
        if len(token) == 3 and token[1] == "十":
            return CHINESE_NUMBER_MAP.get(token[0], 0) * 10 + CHINESE_NUMBER_MAP.get(token[2], 0)
        return CHINESE_NUMBER_MAP.get(token, 0)

    # 规则兜底：当 recall planner 不可用时，至少能给出一个保守的结构化回溯请求。
    def _memory_recall_request_fallback(self, query: str) -> dict[str, Any]:
        normalized = str(query or "").strip().lower()
        focus = self._memory_recall_focus(normalized)
        requested_limit = 0
        count_match = MEMORY_RECALL_COUNT_PATTERN.search(normalized)
        if count_match:
            requested_limit = self._parse_recall_count(count_match.group(1))
        if any(token in normalized for token in MEMORY_RECALL_ALL_HINTS):
            requested_limit = settings.QA_MEMORY_RECALL_MAX_ITEMS
        elif requested_limit <= 0 and any(token in normalized for token in MEMORY_RECALL_LIST_HINTS):
            requested_limit = settings.QA_MEMORY_RECALL_DEFAULT_LIMIT
        limit = min(
            max(requested_limit or 1, 1),
            max(int(settings.QA_MEMORY_RECALL_MAX_ITEMS or 1), 1),
        )
        return {
            "focus": focus,
            "mode": "list" if limit > 1 else "latest",
            "limit": limit,
        }

    # 校验 recall planner 返回的结构，避免模型漏字段或返回非法值时把主链带偏。
    def _normalize_memory_recall_request(self, payload: dict[str, Any] | None, query: str) -> dict[str, Any]:
        fallback = self._memory_recall_request_fallback(query)
        candidate = dict(payload or {})
        focus = str(candidate.get("focus") or fallback["focus"]).strip().lower()
        if focus not in {"question", "answer", "dialogue"}:
            focus = str(fallback["focus"])
        mode = str(candidate.get("mode") or fallback["mode"]).strip().lower()
        if mode not in {"latest", "list"}:
            mode = str(fallback["mode"])
        try:
            limit = int(candidate.get("limit") or fallback["limit"])
        except (TypeError, ValueError):
            limit = int(fallback["limit"])
        limit = min(max(limit, 1), max(int(settings.QA_MEMORY_RECALL_MAX_ITEMS or 1), 1))
        if mode == "latest":
            limit = 1
        return {
            "focus": focus,
            "mode": mode,
            "limit": limit,
            "reason": str(candidate.get("reason") or "").strip(),
        }

    # 主路径：先让轻量 LLM 判断这是“回问题/回回答/回对话”，以及要取几条。
    async def _plan_memory_recall(self, state: LiveAgentState) -> dict[str, Any]:
        query = str(state.get("user_input", "")).strip()
        fallback = self._memory_recall_request_fallback(query)
        started = perf_counter()
        system_prompt = (
            "You are a memory recall planner for a Chinese QA agent. "
            "Do not answer the user. Only classify the recall request into a strict JSON object. "
            'Return JSON only: {"focus":"question|answer|dialogue","mode":"latest|list","limit":1,"reason":"..."} . '
            "focus=question means recalling prior user questions. "
            "focus=answer means recalling prior assistant answers. "
            "focus=dialogue means recalling conversation content or dialogue summary. "
            "mode=list means the user wants several items, recent history, or a list. "
            "mode=latest means the user wants only the most recent item. "
            "limit must be an integer between 1 and "
            f"{max(int(settings.QA_MEMORY_RECALL_MAX_ITEMS or 1), 1)}."
        )
        user_prompt = json.dumps(
            {
                "user_input": query,
                "short_term_memory_size": len(state.get("short_term_memory", [])),
                "fallback_request": fallback,
            },
            ensure_ascii=False,
        )
        try:
            payload = await self.llm_client.ainvoke_json(system_prompt, user_prompt)
            recall_request = self._normalize_memory_recall_request(payload, query)
            await record_timed_tool_call(
                "qa_memory_recall_planning",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": query},
                output_summary=json.dumps(recall_request, ensure_ascii=False)[:200],
                status="ok",
            )
            return recall_request
        except Exception as exc:
            await record_timed_tool_call(
                "qa_memory_recall_planning",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": query},
                output_summary=str(exc),
                status="degraded",
            )
            return fallback

    def _latest_memory_turn(self, turns: list[dict[str, str]], role: str) -> str:
        return next(
            (
                str(item.get("content", "")).strip()
                for item in reversed(turns)
                if str(item.get("role", "")).strip() == role and str(item.get("content", "")).strip()
            ),
            "",
        )

    # 按角色抽取最近 N 条消息，保持原始时序，给“前几个问题/回答”场景复用。
    def _recent_memory_turns(self, turns: list[dict[str, str]], role: str, limit: int) -> list[str]:
        values = [
            str(item.get("content", "")).strip()
            for item in turns
            if str(item.get("role", "")).strip() == role and str(item.get("content", "")).strip()
        ]
        return values[-limit:]

    # 将短期消息整理成最近 N 轮问答，便于回答“我们刚刚聊了什么/前几轮对话”。
    def _recent_dialogue_rounds(self, turns: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
        rounds: list[dict[str, str]] = []
        pending_user = ""
        for item in turns:
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if not role or not content:
                continue
            if role == "user":
                if pending_user:
                    rounds.append({"user": pending_user, "assistant": ""})
                pending_user = content
                continue
            if role == "assistant":
                if pending_user:
                    rounds.append({"user": pending_user, "assistant": content})
                    pending_user = ""
                else:
                    rounds.append({"user": "", "assistant": content})
        if pending_user:
            rounds.append({"user": pending_user, "assistant": ""})
        return rounds[-limit:]

    # LLM 不可用时的兜底实现：基于已提取的记忆候选做确定性回答，保证主链不空转。
    def _build_memory_recall_result_fallback(
        self,
        state: LiveAgentState,
        recent_long_term_memories: list[Any],
        recall_request: dict[str, Any],
    ) -> dict[str, Any]:
        turns = self._memory_turns_without_current_query(state)
        focus = str(recall_request.get("focus") or "dialogue")
        mode = str(recall_request.get("mode") or "latest")
        limit = max(int(recall_request.get("limit") or 1), 1)
        recent_user_questions = self._recent_memory_turns(turns, "user", limit)
        recent_assistant_answers = self._recent_memory_turns(turns, "assistant", limit)
        recent_dialogues = self._recent_dialogue_rounds(turns, limit)
        latest_user_question = recent_user_questions[-1] if recent_user_questions else ""
        latest_assistant_answer = recent_assistant_answers[-1] if recent_assistant_answers else ""

        if focus == "question":
            if mode == "list" and recent_user_questions:
                return {
                    "answer": "你刚刚问过的几个问题是：\n"
                    + "\n".join(f"{index}. {item}" for index, item in enumerate(recent_user_questions, start=1)),
                    "references": [],
                    "confidence": 0.98,
                    "unresolved": False,
                }
            if latest_user_question:
                return {
                    "answer": f"你刚刚问的是：“{latest_user_question}”。",
                    "references": [],
                    "confidence": 0.99,
                    "unresolved": False,
                }

        if focus == "answer":
            if mode == "list" and recent_assistant_answers:
                return {
                    "answer": "我最近几次回答是：\n"
                    + "\n".join(f"{index}. {item}" for index, item in enumerate(recent_assistant_answers, start=1)),
                    "references": [],
                    "confidence": 0.98,
                    "unresolved": False,
                }
            if latest_assistant_answer:
                return {
                    "answer": f"我上一轮的回答是：“{latest_assistant_answer}”。",
                    "references": [],
                    "confidence": 0.99,
                    "unresolved": False,
                }

        if mode == "list" and recent_dialogues:
            blocks = [
                f"{index}. 用户：{item.get('user') or '（无用户问题记录）'}\n助手：{item.get('assistant') or '（暂无对应回答）'}"
                for index, item in enumerate(recent_dialogues, start=1)
            ]
            return {
                "answer": "我们最近几轮对话是：\n" + "\n".join(blocks),
                "references": [],
                "confidence": 0.97,
                "unresolved": False,
            }

        if latest_user_question and latest_assistant_answer:
            return {
                "answer": (
                    f"我们刚刚聊的是：“{latest_user_question}”。"
                    f"我上一轮回复是：“{latest_assistant_answer}”。"
                ),
                "references": [],
                "confidence": 0.97,
                "unresolved": False,
            }

        if latest_user_question:
            return {
                "answer": f"你最近一次提问是：“{latest_user_question}”。",
                "references": [],
                "confidence": 0.96,
                "unresolved": False,
            }

        if latest_assistant_answer:
            return {
                "answer": f"我最近一次回复是：“{latest_assistant_answer}”。",
                "references": [],
                "confidence": 0.96,
                "unresolved": False,
            }

        if recent_long_term_memories:
            summaries = []
            for index, item in enumerate(recent_long_term_memories[:limit], start=1):
                summary = str(getattr(item, "metadata", {}).get("memory_summary") or getattr(item, "memory", "")).strip()
                if summary:
                    summaries.append(f"{index}. {summary}")
            if summaries:
                return {
                    "answer": "当前会话里的短期记忆不足以直接回溯；我在长期记忆里找到最近与你相关的内容：\n"
                    + "\n".join(summaries),
                    "references": [],
                    "confidence": 0.74,
                    "unresolved": False,
                }

        return {
            "answer": "当前会话里还没有可回溯的历史记录，长期记忆里也没有命中到相关内容。",
            "references": [],
            "confidence": 0.0,
            "unresolved": True,
        }

    # 主路径：先取出短期/长期记忆候选，再让 LLM 基于候选内容组织最终回溯答案。
    async def _build_memory_recall_result(
        self,
        state: LiveAgentState,
        recent_long_term_memories: list[Any],
        recall_request: dict[str, Any],
    ) -> dict[str, Any]:
        turns = self._memory_turns_without_current_query(state)
        limit = max(int(recall_request.get("limit") or 1), 1)
        short_term_payload = {
            "questions": self._recent_memory_turns(turns, "user", limit),
            "answers": self._recent_memory_turns(turns, "assistant", limit),
            "dialogues": self._recent_dialogue_rounds(turns, limit),
        }
        long_term_payload = [
            {
                "memory": str(getattr(item, "memory", "")).strip(),
                "summary": str(getattr(item, "metadata", {}).get("memory_summary") or getattr(item, "memory", "")).strip(),
                "score": float(getattr(item, "score", 0.0) or 0.0),
                "created_at": getattr(item, "created_at", None),
                "updated_at": getattr(item, "updated_at", None),
            }
            for item in recent_long_term_memories[:limit]
            if str(getattr(item, "memory", "")).strip()
        ]
        if not short_term_payload["questions"] and not short_term_payload["answers"] and not long_term_payload:
            return self._build_memory_recall_result_fallback(state, recent_long_term_memories, recall_request)

        started = perf_counter()
        system_prompt = (
            "You are a Chinese QA memory recall agent. "
            "Answer strictly based on the provided short-term and long-term memory candidates. "
            "Do not invent memories that are not in the evidence. "
            "If the user asks for multiple items, enumerate them clearly. "
            "If evidence is insufficient, say so explicitly. "
            'Return JSON only: {"answer":"...","confidence":0.0,"unresolved":false}.'
        )
        user_prompt = json.dumps(
            {
                "user_input": state.get("user_input"),
                "recall_request": recall_request,
                "short_term_candidates": short_term_payload,
                "long_term_candidates": long_term_payload,
            },
            ensure_ascii=False,
        )
        try:
            payload = await self.llm_client.ainvoke_json(system_prompt, user_prompt)
            answer = str(payload.get("answer", "")).strip()
            confidence = float(payload.get("confidence", 0.86))
            unresolved = bool(payload.get("unresolved", False))
            if answer:
                await record_timed_tool_call(
                    "qa_memory_recall_answer_generation",
                    started_at=started,
                    node_name="qa",
                    category="llm",
                    input_payload={"query": state.get("user_input"), "recall_request": recall_request},
                    output_summary=answer[:200],
                    status="ok",
                )
                return {
                    "answer": answer,
                    "references": [],
                    "confidence": max(min(confidence, 1.0), 0.0),
                    "unresolved": unresolved,
                }
        except Exception as exc:
            await record_timed_tool_call(
                "qa_memory_recall_answer_generation",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": state.get("user_input"), "recall_request": recall_request},
                output_summary=str(exc),
                status="degraded",
            )
        return self._build_memory_recall_result_fallback(state, recent_long_term_memories, recall_request)

    async def _generate_web_search_answer(
        self,
        state: LiveAgentState,
        rewritten_query: str,
        tool_payload: dict[str, Any],
        memory_context: str = "",
        memory_payload: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        answer_box = tool_payload.get("answer_box") or {}
        knowledge_graph = tool_payload.get("knowledge_graph") or {}
        organic_results = tool_payload.get("organic_results") or []

        direct_answer = str(answer_box.get("answer", "")).strip()
        if direct_answer:
            references = [link for link in [str(answer_box.get("link", "")).strip()] if link]
            return {
                "answer": direct_answer,
                "references": references,
                "confidence": 0.84,
                "unresolved": False,
            }

        started = perf_counter()
        system_prompt = (
            "You are a QA agent with access to live Google search results. "
            "Answer in Chinese using only the provided search results. "
            "Do not invent facts. Keep the answer concise. "
            'Return strict JSON only: {"answer":"...","references":["https://..."],"confidence":0.0}'
        )
        user_prompt = json.dumps(
            {
                "original_user_input": state.get("user_input"),
                "rewritten_query": rewritten_query,
                "long_term_memory_context": memory_context,
                "long_term_memories": memory_payload or [],
                "search_results": {
                    "answer_box": answer_box,
                    "knowledge_graph": knowledge_graph,
                    "organic_results": organic_results,
                },
            },
            ensure_ascii=False,
        )

        valid_links = [
            link
            for link in [
                str(answer_box.get("link", "")).strip(),
                str(knowledge_graph.get("website", "")).strip(),
                *[
                    str(item.get("link", "")).strip()
                    for item in organic_results
                    if str(item.get("link", "")).strip()
                ],
            ]
            if link
        ]

        try:
            payload = await self.llm_client.ainvoke_json(system_prompt, user_prompt)
            answer = str(payload.get("answer", "")).strip()
            confidence = float(payload.get("confidence", 0.72))
            refs = payload.get("references", [])
            references: list[str] = []
            if isinstance(refs, list):
                for ref in refs:
                    ref_text = str(ref).strip()
                    if ref_text and ref_text in valid_links and ref_text not in references:
                        references.append(ref_text)
            if not references:
                references = valid_links[:3]
            if answer:
                await record_timed_tool_call(
                    "qa_web_search_answer_generation",
                    started_at=started,
                    node_name="qa",
                    category="llm",
                    input_payload={"query": rewritten_query},
                    output_summary=answer[:200],
                    status="ok",
                )
                return {
                    "answer": answer,
                    "references": references,
                    "confidence": confidence,
                    "unresolved": False,
                }
        except Exception as exc:
            await record_timed_tool_call(
                "qa_web_search_answer_generation",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": rewritten_query},
                output_summary=str(exc),
                status="degraded",
            )

        fallback_answer = (
            str((organic_results[0] if organic_results else {}).get("snippet", "")).strip()
            or str(knowledge_graph.get("description", "")).strip()
            or QA_NO_ANSWER_TEXT
        )
        return {
            "answer": fallback_answer,
            "references": valid_links[:3],
            "confidence": 0.58 if fallback_answer != QA_NO_ANSWER_TEXT else 0.0,
            "unresolved": fallback_answer == QA_NO_ANSWER_TEXT,
        }

    def _clip_fallback_segment(self, text: str, *, limit: int = 72) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 1].rstrip() + "…"

    def _build_retrieval_fallback_answer(
        self,
        query: str,
        retrieved_docs: list[dict[str, Any]],
        knowledge_focus: dict[str, Any] | None = None,
        query_budget: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # 企业化降级策略：检索已经拿到资料时，不能因为 LLM 不可用就直接回答“没找到”。
        # 这里退化成“基于命中文档做结构化摘录”，至少把知识库里已有的信息稳定返回给用户。
        if not retrieved_docs:
            return self._no_answer_result()

        normalized_focus = self._normalize_knowledge_focus(knowledge_focus or {})
        focus_fields = list(normalized_focus.get("focus_fields", []))
        if focus_fields and focus_fields != [KNOWLEDGE_FOCUS_GENERAL]:
            focused_answer = self._render_focused_fallback_answer(focus_fields, retrieved_docs)
            if focused_answer:
                references = [
                    str(doc.get("doc_id", "")).strip()
                    for doc in retrieved_docs[:3]
                    if str(doc.get("doc_id", "")).strip()
                ]
                return {
                    "answer": focused_answer,
                    "references": references,
                    "confidence": 0.58,
                    "unresolved": False,
                }

        primary_doc = dict(retrieved_docs[0] or {})
        metadata = dict(primary_doc.get("metadata", {}) or {})
        metadata.update(extract_catalog_attributes(primary_doc.get("content", ""), metadata))
        budget_constraint = normalize_budget_constraint(query_budget) or extract_query_budget(query)
        title = (
            str(metadata.get("section_title") or "").strip()
            or str(metadata.get("product_name") or "").strip()
        )
        title = re.sub(r"^#+\s*", "", title).strip()

        summary_lines: list[str] = []
        bullet_lines: list[str] = []
        paragraph_lines: list[str] = []
        for raw_line in str(primary_doc.get("content", "")).splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            if line.startswith(">"):
                summary_lines.append(self._clip_fallback_segment(line.lstrip("> ").replace("｜", "，")))
                continue
            if line.startswith("-"):
                bullet_lines.append(self._clip_fallback_segment(line.lstrip("- ").strip()))
                continue
            if line.startswith("##"):
                continue
            paragraph_lines.append(self._clip_fallback_segment(line))

        snippets: list[str] = []
        snippets.extend(summary_lines[:1])
        snippets.extend(bullet_lines[:3])
        if not snippets:
            snippets.extend(paragraph_lines[:2])

        if not snippets and not title:
            return self._no_answer_result()

        answer_parts: list[str] = []
        if title and budget_constraint and metadata.get("price_band_text"):
            answer_parts.append(
                f"根据知识库，更接近你 {budget_constraint['display']} 预算的是 {title}，直播价带 {metadata['price_band_text']}。"
            )
        elif title:
            answer_parts.append(f"根据知识库，{title}。")
        if snippets:
            answer_parts.append("；".join(item for item in snippets if item) + "。")

        answer = "".join(answer_parts).strip() or QA_NO_ANSWER_TEXT
        references = [
            str(doc.get("doc_id", "")).strip()
            for doc in retrieved_docs[:3]
            if str(doc.get("doc_id", "")).strip()
        ]
        return {
            "answer": answer,
            "references": references,
            "confidence": 0.58 if answer != QA_NO_ANSWER_TEXT else 0.0,
            "unresolved": answer == QA_NO_ANSWER_TEXT,
        }

    # 读取最近若干轮对话，给查询改写和回答生成提供上下文。
    def _recent_memory(self, state: LiveAgentState, turns: int) -> list[dict[str, str]]:
        history = list(state.get("short_term_memory", []))
        if not history:
            return []
        return history[-(turns * 2) :]

    # 规范化查询改写结果里的中文空格，避免把检索 query 搞脏。
    def _normalize_rewritten_query(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text).strip()
        normalized = re.sub(fr"(?<=[{CJK_CHARS}])\s+(?=[{CJK_CHARS}])", "", normalized)
        normalized = re.sub(fr"(?<=[{CJK_CHARS}])\s+(?=[{CJK_CLOSE_PUNCT}])", "", normalized)
        normalized = re.sub(fr"(?<=[{CJK_CLOSE_PUNCT}])\s+(?=[{CJK_CHARS}])", "", normalized)
        normalized = re.sub(fr"(?<=[{CJK_OPEN_PUNCT}])\s+(?=[{CJK_CHARS}])", "", normalized)
        normalized = re.sub(fr"(?<=[{CJK_CHARS}])\s+(?=[0-9])", "", normalized)
        normalized = re.sub(fr"(?<=[0-9])\s+(?=[{CJK_CHARS}])", "", normalized)
        return normalized

    # 判断当前问题是否强依赖上下文，从而决定是否优先做查询改写。
    def _needs_contextual_rewrite(self, query: str) -> bool:
        lowered = query.lower()
        pronouns = (
            "这",
            "这个",
            "这款",
            "它",
            "那个",
            "哪款",
            "上面",
            "刚才",
            "再说",
            "那",
            "这些",
            "那些",
        )
        if len(query.strip()) <= 12:
            return True
        return any(token in lowered for token in pronouns)

    # 当模型改写失败时，用最近一轮用户表达做保守拼接兜底。
    def _fallback_rewrite(self, state: LiveAgentState) -> str:
        query = state["user_input"].strip()
        memory = self._recent_memory(state, turns=2)
        # 从 state 读取 Router LLM 的预决策，不再自己判断
        needs_rewrite = state.get("needs_contextual_rewrite", True)
        if not memory or not needs_rewrite:
            return self._normalize_rewritten_query(query)

        latest_user_turn = next(
            (
                str(item.get("content", "")).strip()
                for item in reversed(memory)
                if str(item.get("role", "")).strip() == "user" and str(item.get("content", "")).strip()
            ),
            "",
        )
        if not latest_user_turn or latest_user_turn == query:
            return self._normalize_rewritten_query(query)
        return self._normalize_rewritten_query(f"{latest_user_turn}；补充问题：{query}")

    async def _semantic_normalize_retrieval_query(self, query: str) -> str:
        # 查询改写之后，再走一层预算语义规范化。
        # 这里主路径交给轻量模型统一“80块钱左右 / 100来块 / 300出头”这类口语预算，
        # 避免后面的检索和回答继续各自猜一遍预算含义。
        normalized_query = self._normalize_rewritten_query(query)
        if self.pipeline is None or not hasattr(self.pipeline, "normalize_query_semantics"):
            return normalized_query

        try:
            semantic_plan = await self.pipeline.normalize_query_semantics(normalized_query)
        except Exception:
            return normalized_query

        semantic_query = self._normalize_rewritten_query(
            str((semantic_plan or {}).get("normalized_query") or "").strip()
        )
        return semantic_query or normalized_query

    # 调用 LLM 做查询改写，并在失败时回退到规则兜底方案。
    async def _rewrite_query(self, state: LiveAgentState) -> str:
        started = perf_counter()
        query = state["user_input"].strip()
        memory = self._recent_memory(state, turns=2)
        if not memory:
            return await self._semantic_normalize_retrieval_query(query)

        system_prompt = (
            "You rewrite live-commerce QA queries for retrieval. "
            "Resolve pronouns and omissions with recent conversation context. "
            "Do not change the user's intent. "
            'Return strict JSON only: {"rewritten_query":"..."}'
        )
        user_prompt = json.dumps(
            {
                "user_input": query,
                "recent_memory": memory,
                "current_product_id": state.get("current_product_id"),
                "live_stage": state.get("live_stage"),
            },
            ensure_ascii=False,
        )
        try:
            payload = await self.llm_client.ainvoke_json(system_prompt, user_prompt)
        except Exception:
            await record_timed_tool_call(
                "qa_query_rewrite",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": query},
                status="degraded",
            )
            return await self._semantic_normalize_retrieval_query(self._fallback_rewrite(state))

        rewritten_query = str(payload.get("rewritten_query", "")).strip()
        if not rewritten_query:
            await record_timed_tool_call(
                "qa_query_rewrite",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": query},
                status="degraded",
            )
            return await self._semantic_normalize_retrieval_query(self._fallback_rewrite(state))

        rewritten_query = await self._semantic_normalize_retrieval_query(rewritten_query)
        await record_timed_tool_call(
            "qa_query_rewrite",
            started_at=started,
            node_name="qa",
            category="llm",
            input_payload={"query": query},
            output_summary=rewritten_query,
            status="ok",
        )
        return rewritten_query

    # 把检索结果裁成 Top-3，并统一整理成后续 Prompt 使用的结构。
    def _top_retrieved_docs(self, rerank_results: list[Any], top_k: int = 3) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        for rank, result in enumerate(rerank_results[:top_k], start=1):
            metadata = dict(getattr(result, "metadata", {}) or {})
            docs.append(
                {
                    "rank": rank,
                    "doc_id": getattr(result, "doc_id", ""),
                    "content": getattr(result, "content", ""),
                    "score": getattr(result, "final_score", 0.0),
                    "source_type": getattr(result, "source_type", ""),
                    "source_file": metadata.get("source_file", ""),
                    "metadata": metadata,
                }
            )
        return docs

    # 给 planner/executor 使用的纯检索入口：只拿 docs，不在这里生成最终答案。
    async def retrieve_only(self, state: LiveAgentState) -> dict[str, Any]:
        rewritten_query = self._normalize_rewritten_query(
            str(state.get("rewritten_query") or "").strip() or await self._rewrite_query(state)
        )
        query_budget = normalize_budget_constraint(state.get("query_budget")) or extract_query_budget(rewritten_query)
        if self.pipeline is None:
            return {
                "rewritten_query": rewritten_query,
                "query_budget": query_budget,
                "retrieved_docs": [],
            }

        retrieval_started = perf_counter()
        try:
            _, rerank_results = await self.pipeline.retrieve(
                rewritten_query,
                source_hint=state.get("knowledge_scope"),
            )
            retrieved_docs = self._top_retrieved_docs(rerank_results, top_k=3)
            await record_timed_tool_call(
                "qa_retrieval",
                started_at=retrieval_started,
                node_name="qa",
                category="retrieval",
                input_payload={"query": rewritten_query},
                output_summary=f"docs={len(retrieved_docs)}",
                status="ok" if retrieved_docs else "degraded",
            )
        except Exception as exc:
            logger.warning("qa_retrieval_failed trace_id=%s error=%s", state.get("trace_id"), exc)
            await record_timed_tool_call(
                "qa_retrieval",
                started_at=retrieval_started,
                node_name="qa",
                category="retrieval",
                input_payload={"query": rewritten_query},
                output_summary=str(exc),
                status="degraded",
            )
            retrieved_docs = []

        return {
            "rewritten_query": rewritten_query,
            "query_budget": query_budget,
            "retrieved_docs": retrieved_docs,
        }

    # 只执行联网搜索工具，供 planner/executor 先拿 observation，最终文案交给后续 handoff 的 agent。
    async def web_search_only(self, state: LiveAgentState) -> dict[str, Any]:
        rewritten_query = self._normalize_rewritten_query(
            str(state.get("rewritten_query") or "").strip() or self._normalize_rewritten_query(state.get("user_input", ""))
        )
        if not rewritten_query:
            rewritten_query = await self._rewrite_query(state)
        tool_payload = await self._run_tool(WEB_SEARCH_TOOL_NAME, query=rewritten_query)
        return {
            "rewritten_query": rewritten_query,
            "tools_used": [WEB_SEARCH_TOOL_NAME],
            "tool_outputs": {WEB_SEARCH_TOOL_NAME: tool_payload},
        }

    # 返回统一的无答案结构，便于零召回和模型失败场景复用。
    def _no_answer_result(self) -> dict[str, Any]:
        return {
            "answer": QA_NO_ANSWER_TEXT,
            "references": [],
            "confidence": 0.0,
            "unresolved": True,
        }

    # 按当前商品加载长期高频问题，帮助 QA 在常见问法场景下更快进入正确语义。
    async def _load_high_frequency_questions(self, state: LiveAgentState) -> list[dict[str, Any]]:
        if self.high_frequency_repository is None:
            return []
        product_id = str(state.get("current_product_id") or "").strip()
        if not product_id:
            return []
        try:
            records = await self.high_frequency_repository.list_by_product(
                product_id,
                limit=settings.HIGH_FREQUENCY_QUESTION_LIMIT,
            )
        except Exception:
            return []
        return [{"question": record.question, "frequency": record.frequency} for record in records]

    # 当结构化回答失败时，退到纯文本回答模式尽量保住可读结果。
    async def _generate_text_answer(
        self,
        state: LiveAgentState,
        rewritten_query: str,
        retrieved_docs: list[dict[str, Any]],
        high_frequency_questions: list[dict[str, Any]],
        knowledge_focus: dict[str, Any],
        query_budget: dict[str, Any] | None = None,
        memory_context: str = "",
        memory_payload: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        system_prompt = (
            "你是直播电商 QA 助手。"
            "必须只基于给定知识片段回答，不能编造事实。"
            "请直接输出自然中文回答，不要输出 JSON。"
        )
        user_prompt = json.dumps(
            {
                "current_product_id": state.get("current_product_id"),
                "live_stage": state.get("live_stage"),
                "short_term_memory": self._recent_memory(state, turns=3),
                "long_term_memory_context": memory_context,
                "long_term_memories": memory_payload or [],
                "knowledge_context": retrieved_docs,
                "knowledge_focus": knowledge_focus,
                "high_frequency_questions": high_frequency_questions,
                "query_budget": normalize_budget_constraint(query_budget) or extract_query_budget(rewritten_query),
                "rewritten_query": rewritten_query,
                "original_user_input": state["user_input"],
            },
            ensure_ascii=False,
        )

        try:
            answer = (await self.llm_client.ainvoke_text(system_prompt, user_prompt)).strip()
        except Exception as exc:
            logger.warning("qa_text_generation_failed trace_id=%s error=%s", state.get("trace_id"), exc)
            await record_timed_tool_call(
                "qa_answer_generation_text",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": rewritten_query},
                output_summary=str(exc),
                status="degraded",
            )
            return self._build_retrieval_fallback_answer(
                rewritten_query,
                retrieved_docs,
                knowledge_focus=knowledge_focus,
                query_budget=query_budget,
            )

        if not answer:
            await record_timed_tool_call(
                "qa_answer_generation_text",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": rewritten_query},
                status="degraded",
            )
            return self._build_retrieval_fallback_answer(
                rewritten_query,
                retrieved_docs,
                knowledge_focus=knowledge_focus,
                query_budget=query_budget,
            )
        await record_timed_tool_call(
            "qa_answer_generation_text",
            started_at=started,
            node_name="qa",
            category="llm",
            input_payload={"query": rewritten_query},
            output_summary=answer[:200],
            status="ok",
        )

        references = [str(doc["doc_id"]) for doc in retrieved_docs if str(doc.get("doc_id", "")).strip()]
        return {
            "answer": answer,
            "references": references,
            "confidence": 0.68,
            "unresolved": False,
        }

    # 优先要求模型返回 JSON；若失败，再退回纯文本生成。
    async def _generate_answer(
        self,
        state: LiveAgentState,
        rewritten_query: str,
        retrieved_docs: list[dict[str, Any]],
        high_frequency_questions: list[dict[str, Any]],
        knowledge_focus: dict[str, Any],
        query_budget: dict[str, Any] | None = None,
        memory_context: str = "",
        memory_payload: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        system_prompt = (
            "You are a live-commerce QA agent. "
            "Answer in Chinese and only use the provided knowledge context. "
            "If the user gives a budget or price range, prefer documents that satisfy that budget and mention the matched price band. "
            "Do not invent facts. Keep the answer concise and practical. "
            'Return strict JSON only: {"answer":"...","references":["doc_id"],"confidence":0.0}'
        )
        system_prompt += (
            " Use knowledge_focus to determine what the user is actually asking for. "
            "If knowledge_focus points to a narrow field such as material, model, brand, price, audience or specs, "
            "answer only that field instead of dumping the whole product overview. "
            "If the requested field is missing from the provided knowledge context, say so explicitly."
        )
        user_prompt = json.dumps(
            {
                "current_product_id": state.get("current_product_id"),
                "live_stage": state.get("live_stage"),
                "short_term_memory": self._recent_memory(state, turns=3),
                "long_term_memory_context": memory_context,
                "long_term_memories": memory_payload or [],
                "knowledge_context": retrieved_docs,
                "knowledge_focus": knowledge_focus,
                "high_frequency_questions": high_frequency_questions,
                "query_budget": normalize_budget_constraint(query_budget) or extract_query_budget(rewritten_query),
                "rewritten_query": rewritten_query,
                "original_user_input": state["user_input"],
            },
            ensure_ascii=False,
        )

        try:
            payload = await self.llm_client.ainvoke_json(system_prompt, user_prompt)
            elapsed_ms = int((perf_counter() - started) * 1000)
            logger.info(f"[TIMING][{state.get('trace_id')}] qa_llm_generate t={elapsed_ms}ms query='{rewritten_query[:30]}' confidence={payload.get('confidence', '?')}")
        except Exception as exc:
            logger.warning("qa_json_generation_failed trace_id=%s error=%s", state.get("trace_id"), exc)
            await record_timed_tool_call(
                "qa_answer_generation_json",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": rewritten_query},
                output_summary=str(exc),
                status="degraded",
            )
            return await self._generate_text_answer(
                state,
                rewritten_query,
                retrieved_docs,
                high_frequency_questions,
                knowledge_focus,
                query_budget=query_budget,
                memory_context=memory_context,
                memory_payload=memory_payload,
            )

        answer = str(payload.get("answer", "")).strip()
        references = payload.get("references", [])
        confidence = payload.get("confidence", 0.0)

        if not isinstance(references, list):
            references = []

        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        if not answer:
            await record_timed_tool_call(
                "qa_answer_generation_json",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": rewritten_query},
                status="degraded",
            )
            return await self._generate_text_answer(
                state,
                rewritten_query,
                retrieved_docs,
                high_frequency_questions,
                knowledge_focus,
                query_budget=query_budget,
                memory_context=memory_context,
                memory_payload=memory_payload,
            )

        await record_timed_tool_call(
            "qa_answer_generation_json",
            started_at=started,
            node_name="qa",
            category="llm",
            input_payload={"query": rewritten_query},
            output_summary=answer[:200],
            status="ok",
        )

        return {
            "answer": answer,
            "references": references,
            "confidence": confidence,
            "unresolved": confidence < 0.5,
        }

    # 对模型给出的引用做白名单校验，只保留本轮真实召回到的文档。
    def _normalize_references(self, generated_refs: list[Any], retrieved_docs: list[dict[str, Any]]) -> list[str]:
        valid_ids = [str(doc["doc_id"]) for doc in retrieved_docs if str(doc.get("doc_id", "")).strip()]
        if not valid_ids:
            return []

        normalized: list[str] = []
        for ref in generated_refs:
            ref_id = str(ref).strip()
            if ref_id and ref_id in valid_ids and ref_id not in normalized:
                normalized.append(ref_id)
        return normalized or valid_ids

    # 执行完整 QA 主链：改写、检索、生成、引用清洗和低置信度降级。
    async def run(self, state: LiveAgentState) -> StatePatch:
        # QAAgent.run 是 QA 主链总入口：
        # 它会根据 planner 注入的 tool_intent，选择走记忆召回、时间工具、联网搜索，
        # 或常规的“改写 -> 检索 -> 生成 -> 引用清洗 -> 低置信度降级”流程。
        tool_intent = self._resolve_tool_intent(state)
        is_memory_recall_query = tool_intent == TOOL_INTENT_MEMORY_RECALL
        skip_contextual_rewrite = tool_intent in {TOOL_INTENT_DATETIME, TOOL_INTENT_WEB_SEARCH}
        preloaded_query = self._normalize_rewritten_query(str(state.get("rewritten_query") or "").strip())
        preloaded_budget = normalize_budget_constraint(state.get("query_budget"))
        # 记忆回溯问题直接保留原问句，不需要先走 query rewrite。
        # 记忆召回和工具型问题优先保留原问句，不先做 query rewrite，
        # 避免把“回忆一下我前面问了什么”这类问题改写坏。
        rewritten_query = (
            self._normalize_rewritten_query(state.get("user_input", ""))
            if is_memory_recall_query or skip_contextual_rewrite
            else preloaded_query or await self._rewrite_query(state)
        )
        retrieved_docs: list[dict[str, Any]] = list(state.get("retrieved_docs", []))
        query_budget = preloaded_budget or extract_query_budget(rewritten_query)
        # 高频问答通常用于补充固定表达或做提示词增强。
        high_frequency_questions = await self._load_high_frequency_questions(state)
        long_term_memories = []
        if self.memory_hook is not None:
            try:
                # 长期记忆检索与知识检索并行存在：
                # 记忆回答“你之前说过什么”，知识库回答“资料里写了什么”。
                long_term_memories = await self.memory_hook.search_for_state(state)
            except Exception as exc:
                logger.warning("qa_memory_search_failed trace_id=%s error=%s", state.get("trace_id"), exc)
                long_term_memories = []
        memory_payload = self.memory_hook.serialize_memories(long_term_memories) if self.memory_hook else []
        memory_context = self.memory_hook.build_prompt_context(long_term_memories) if self.memory_hook else ""

        # 记忆召回问题不走知识库检索，而是先把“要回忆什么、要几条”结构化，
        # 再从长期记忆中挑内容，由 LLM 组织最终回答。
        if tool_intent == TOOL_INTENT_MEMORY_RECALL:
            # 先用 LLM 把“回溯什么、要几条”解析成结构化请求，再去拿对应记忆。
            recall_request = await self._plan_memory_recall(state)
            recent_long_term_memories = list(long_term_memories)
            if self.memory_hook is not None and not recent_long_term_memories:
                try:
                    # 如果相似召回没命中，再退化成“最近几条记忆”兜底，避免直接回答不知道。
                    recent_long_term_memories = await self.memory_hook.list_recent_for_state(
                        state,
                        limit=max(int(recall_request.get("limit") or 1), 1),
                    )
                except Exception as exc:
                    logger.warning("qa_recent_memory_list_failed trace_id=%s error=%s", state.get("trace_id"), exc)
                    recent_long_term_memories = []
            recall_result = await self._build_memory_recall_result(state, recent_long_term_memories, recall_request)
            recall_memory_payload = (
                self.memory_hook.serialize_memories(recent_long_term_memories) if self.memory_hook else []
            )
            return {
                "rewritten_query": rewritten_query,
                "agent_output": recall_result["answer"],
                "references": list(recall_result.get("references", [])),
                "retrieved_docs": [],
                "high_frequency_questions": high_frequency_questions,
                "qa_confidence": float(recall_result.get("confidence", 0.0)),
                "unresolved": bool(recall_result.get("unresolved", False)),
                "agent_name": self.name,
                "memory_recall_request": recall_request,
                "long_term_memories": recall_memory_payload,
                "long_term_memory_hits": len(recall_memory_payload),
            }

        # 时间问题走工具直答，不需要知识库和长上下文生成。由LLM根据用户问题计算相对日期。
        if tool_intent == TOOL_INTENT_DATETIME:
            tool_payload = await self._run_tool(DATETIME_TOOL_NAME, query=state.get("user_input", ""))
            return {
                "rewritten_query": rewritten_query,
                "agent_output": await self._generate_datetime_answer(state, tool_payload),
                "references": [],
                "retrieved_docs": [],
                "high_frequency_questions": high_frequency_questions,
                "qa_confidence": 1.0,
                "unresolved": False,
                "agent_name": self.name,
                "tools_used": [DATETIME_TOOL_NAME],
                "tool_outputs": {DATETIME_TOOL_NAME: tool_payload},
                "long_term_memories": memory_payload,
                "long_term_memory_hits": len(memory_payload),
            }

        # 联网搜索问题优先复用 planner/executor 已经拿到的 observation，
        # 避免在 QA 阶段重复联网。
        if tool_intent == TOOL_INTENT_WEB_SEARCH:
            # planner/executor 已经拿到搜索结果时，直接复用 observation，避免重复联网搜索。
            tool_payload = dict((state.get("tool_outputs") or {}).get(WEB_SEARCH_TOOL_NAME) or {})
            if not tool_payload:
                # 如果前面没搜到 observation，QA 自己补做一次 web_search_only。
                web_search_result = await self.web_search_only(state | {"rewritten_query": rewritten_query})
                rewritten_query = str(web_search_result.get("rewritten_query", "")).strip() or rewritten_query
                tool_payload = dict((web_search_result.get("tool_outputs") or {}).get(WEB_SEARCH_TOOL_NAME) or {})
            web_result = await self._generate_web_search_answer(
                state,
                rewritten_query,
                tool_payload,
                memory_context=memory_context,
                memory_payload=memory_payload,
            )
            return {
                "rewritten_query": rewritten_query,
                "agent_output": str(web_result.get("answer", "")).strip() or QA_NO_ANSWER_TEXT,
                "references": list(web_result.get("references", [])),
                "retrieved_docs": [],
                "high_frequency_questions": high_frequency_questions,
                "qa_confidence": float(web_result.get("confidence", 0.0)),
                "unresolved": bool(web_result.get("unresolved", False)),
                "agent_name": self.name,
                "tools_used": [WEB_SEARCH_TOOL_NAME],
                "tool_outputs": {WEB_SEARCH_TOOL_NAME: tool_payload},
                "long_term_memories": memory_payload,
                "long_term_memory_hits": len(memory_payload),
            }

        # 常规知识问答如果还没有预取文档，这里会补一次 retrieve_only。
        # 这样 planner/executor 和 qa 既可以拆开跑，也可以在 QA 阶段独立自洽。
        if not retrieved_docs and self.pipeline is not None and state.get("requires_retrieval", True):
            retrieval_result = await self.retrieve_only(state | {"rewritten_query": rewritten_query})
            rewritten_query = str(retrieval_result.get("rewritten_query", "")).strip() or rewritten_query
            retrieved_docs = list(retrieval_result.get("retrieved_docs", []))
            query_budget = normalize_budget_constraint(retrieval_result.get("query_budget")) or query_budget

        # 知识和记忆都为空时直接返回 no-answer，
        # 避免模型在无依据情况下硬编答案。
        if not retrieved_docs and not memory_payload:
            return {
                "rewritten_query": rewritten_query,
                "query_budget": query_budget,
                "agent_output": QA_NO_ANSWER_TEXT,
                "references": [],
                "retrieved_docs": [],
                "high_frequency_questions": high_frequency_questions,
                "qa_confidence": 0.0,
                "unresolved": True,
                "agent_name": self.name,
                "long_term_memories": memory_payload,
                "long_term_memory_hits": len(memory_payload),
            }

        # 先让 LLM 统一判断“用户到底在问哪个字段”，再把这个结构化 focus 同时喂给生成链路和 fallback。
        # 在真正生成答案前，先让 LLM 判断“用户到底在问商品的哪个字段/哪个维度”，
        # 例如材质、型号、价格、适用人群，而不是把整段商品简介原样复述出去。
        knowledge_focus = await self._plan_knowledge_focus(state, rewritten_query, retrieved_docs)
        qa_result = await self._generate_answer(
            state,
            rewritten_query,
            retrieved_docs,
            high_frequency_questions,
            knowledge_focus,
            query_budget=query_budget,
            memory_context=memory_context,
            memory_payload=memory_payload,
        )
        references = self._normalize_references(qa_result.get("references", []), retrieved_docs)
        confidence = float(qa_result.get("confidence", 0.0))
        unresolved = bool(qa_result.get("unresolved", False)) or confidence < 0.5
        answer = str(qa_result.get("answer", "")).strip() or QA_NO_ANSWER_TEXT

        if unresolved and answer not in {QA_NO_ANSWER_TEXT, QA_LOW_CONFIDENCE_TEXT}:
            # 低置信度时统一降级成保守文案，避免“看起来答了，其实答错”。
            answer = QA_LOW_CONFIDENCE_TEXT

        return {
            "rewritten_query": rewritten_query,
            "agent_output": answer,
            "references": references if not unresolved or answer != QA_NO_ANSWER_TEXT else [],
            "retrieved_docs": retrieved_docs,
            "high_frequency_questions": high_frequency_questions,
            "query_budget": query_budget,
            "qa_confidence": confidence,
            "unresolved": unresolved,
            "agent_name": self.name,
            "knowledge_focus": knowledge_focus,
            "long_term_memories": memory_payload,
            "long_term_memory_hits": len(memory_payload),
        }
