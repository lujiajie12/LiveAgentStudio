"""
LLM 网关模块

提供与大语言模型交互的统一接口。支持 OpenAI API 调用，
当 API 不可用时自动降级到启发式规则匹配。

主要功能：
- 初始化和管理 LLM 客户端
- 异步调用 LLM 获取 JSON 格式响应
- 故障转移到启发式意图识别
"""

import json
import re
from time import perf_counter
from typing import Any

from app.core.config import settings
from app.core.observability import record_timed_tool_call

try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover
    ChatOpenAI = None

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None


class LLMGateway:
    """
    LLM 网关基类
    
    定义与大语言模型交互的标准接口。
    子类应实现具体的 LLM 调用逻辑。
    """
    
    async def ainvoke_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """
        异步调用 LLM 并返回 JSON 格式响应
        
        Args:
            system_prompt: 系统提示词，定义 LLM 的行为和角色
            user_prompt: 用户输入提示词
            
        Returns:
            dict: LLM 返回的 JSON 格式响应
            
        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError

    async def ainvoke_tool_call(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raise NotImplementedError


class OpenAILLMGateway(LLMGateway):
    """
    OpenAI LLM 网关实现
    
    使用 LangChain 的 ChatOpenAI 客户端与 OpenAI API 交互。
    支持故障转移到启发式规则匹配。
    
    配置项（来自 app.core.config）：
    - OPENAI_API_KEY: OpenAI API 密钥
    - OPENAI_BASE_URL: API 基础 URL（可选，支持代理）
    - ROUTER_MODEL: 使用的模型名称（如 gpt-4o-mini）
    - ROUTER_TIMEOUT_MS: 请求超时时间（毫秒）
    """
    
    def __init__(self):
        self._client = None
        self._tool_client = None
        api_key  = settings.LLM_API_KEY or settings.OPENAI_API_KEY
        base_url = settings.LLM_BASE_URL or settings.OPENAI_BASE_URL
        model = settings.ROUTER_MODEL or settings.LLM_MODEL
        self._planner_model = settings.PLANNER_MODEL or settings.LLM_MODEL or settings.ROUTER_MODEL

        if api_key and ChatOpenAI is not None:
            self._client = ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                timeout=settings.ROUTER_TIMEOUT_MS / 1000,
                temperature=0.8,
            )
        if api_key and AsyncOpenAI is not None:
            self._tool_client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=settings.PLANNER_TIMEOUT_MS / 1000,
            )

    def _extract_json_payload(self, content: str) -> dict[str, Any]:
        candidate = content.strip()
        if not candidate:
            raise json.JSONDecodeError("empty response", candidate, 0)

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        fenced = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        fenced = re.sub(r"\s*```$", "", fenced)
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

    def _is_timeout_error(self, exc: Exception) -> bool:
        timeout_type_names = {
            "APITimeoutError",
            "ReadTimeout",
            "ConnectTimeout",
            "TimeoutException",
        }
        if isinstance(exc, TimeoutError):
            return True
        if exc.__class__.__name__ in timeout_type_names:
            return True
        return "timeout" in str(exc).lower()

    def _infer_knowledge_scope(self, lowered: str) -> str:
        detail_keywords = (
            "价格", "多少钱", "规格", "参数", "功率", "容量", "尺寸", "材质",
            "成分", "型号", "技术", "性能", "适合", "区别", "对比", "卖点",
            "细节", "配置", "功能", "特点",
        )
        faq_keywords = (
            "发货", "物流", "售后", "保修", "退货", "退款", "换货", "赠品",
            "下单", "支付", "发票", "包邮", "多久", "质保", "注意事项", "怎么清洗",
            "怎么安装", "使用说明", "客服", "规则",
        )

        detail_hits = sum(keyword in lowered for keyword in detail_keywords)
        faq_hits = sum(keyword in lowered for keyword in faq_keywords)

        if detail_hits and faq_hits:
            return "mixed"
        if detail_hits:
            return "product_detail"
        if faq_hits:
            return "faq"
        return "mixed"

    def _is_tool_capability_question(self, lowered: str) -> bool:
        compact = re.sub(r"\s+", "", lowered)
        capability_markers = ("你能", "你会", "你可以", "是否支持", "支持", "能不能", "可不可以", "会不会")
        web_topics = ("联网搜索", "联网搜", "联网查", "上网搜索", "上网查", "访问互联网", "网上搜索")
        memory_topics = ("记住", "记忆", "保存对话", "保存问题", "记下来")
        web_action_markers = (
            "帮我搜",
            "帮我查",
            "搜一下",
            "查一下",
            "查下",
            "搜索一下",
            "搜索下",
            "最新",
            "实时",
            "新闻",
            "官网",
            "天气",
            "汇率",
            "股价",
            "金价",
            "油价",
        )
        if (
            any(marker in compact for marker in capability_markers)
            and any(topic in compact for topic in web_topics)
            and not any(marker in compact for marker in web_action_markers)
        ):
            return True
        return any(marker in compact for marker in capability_markers) and any(
            topic in compact for topic in memory_topics
        )

    def _infer_tool_intent(self, lowered: str) -> str:
        if self._is_tool_capability_question(lowered):
            return "none"

        datetime_keywords = (
            "今天周几",
            "今天是周几",
            "今天星期几",
            "今天是星期几",
            "礼拜几",
            "周几",
            "星期几",
            "现在几点",
            "几点了",
            "几号",
            "几月几号",
            "当前日期",
            "当前时间",
            "日期",
            "时间",
        )
        memory_recall_hint_keywords = (
            "刚刚",
            "刚才",
            "上一轮",
            "上一个",
            "前面",
            "之前",
            "记得",
            "回顾",
            "回忆",
        )
        memory_recall_target_keywords = (
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
        web_search_keywords = (
            "最新",
            "实时",
            "新闻",
            "官网",
            "搜索",
            "搜一下",
            "查一下",
            "帮我查",
            "联网查",
            "上网查",
            "天气",
            "汇率",
            "股价",
            "金价",
            "油价",
            "票房",
            "行情",
        )

        if any(keyword in lowered for keyword in datetime_keywords):
            return "datetime"
        if any(keyword in lowered for keyword in memory_recall_hint_keywords) and any(
            keyword in lowered for keyword in memory_recall_target_keywords
        ):
            return "memory_recall"
        if any(keyword in lowered for keyword in web_search_keywords):
            return "web_search"
        return "none"

    async def ainvoke_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """
        异步调用 OpenAI LLM 获取 JSON 格式响应
        
        流程：
        1. 如果 LLM 客户端不可用，使用启发式规则匹配
        2. 否则调用 OpenAI API
        3. 解析响应内容为 JSON 格式
        
        Args:
            system_prompt: 系统提示词，定义 LLM 的行为
            user_prompt: 用户输入提示词
            
        Returns:
            dict: 包含意图识别结果的 JSON 对象
                {
                    "intent": str,  # 识别的意图类型
                    "confidence": float,  # 置信度
                    "reason": str,  # 识别原因
                    ...其他字段
                }
        """
        # 如果 LLM 客户端不可用，使用启发式规则
        if self._client is None:
            return self._heuristic_response(user_prompt)

        started = perf_counter()
        try:
            response = await self._client.ainvoke(
                [
                    ("system", system_prompt),  # 系统角色消息
                    ("human", user_prompt),  # 用户消息
                ]
            )
        except Exception as exc:
            if self._is_timeout_error(exc):
                await record_timed_tool_call(
                    "router_llm",
                    started_at=started,
                    node_name="router",
                    category="llm",
                    output_summary="timeout",
                    status="degraded",
                )
                raise TimeoutError("LLM request timed out") from exc
            await record_timed_tool_call(
                "router_llm",
                started_at=started,
                node_name="router",
                category="llm",
                output_summary=str(exc),
                status="degraded",
            )
            return self._heuristic_response(user_prompt)

        try:
            payload = self._extract_json_payload(str(response.content))
            await record_timed_tool_call(
                "router_llm",
                started_at=started,
                node_name="router",
                category="llm",
                output_summary=str(payload)[:200],
                status="ok",
            )
            return payload
        except Exception:
            await record_timed_tool_call(
                "router_llm",
                started_at=started,
                node_name="router",
                category="llm",
                output_summary="parse_fallback",
                status="degraded",
            )
            return self._heuristic_response(user_prompt)

    async def ainvoke_tool_call(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self._tool_client is None:
            raise RuntimeError("planner tool client unavailable")

        started = perf_counter()
        try:
            response = await self._tool_client.chat.completions.create(
                model=self._planner_model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                tools=tools,
                tool_choice="auto",
            )
        except Exception as exc:
            if self._is_timeout_error(exc):
                await record_timed_tool_call(
                    "planner_llm_function_call",
                    started_at=started,
                    node_name="router",
                    category="llm",
                    output_summary="timeout",
                    status="degraded",
                )
                raise TimeoutError("planner tool call timed out") from exc
            await record_timed_tool_call(
                "planner_llm_function_call",
                started_at=started,
                node_name="router",
                category="llm",
                output_summary=str(exc),
                status="degraded",
            )
            raise

        message = response.choices[0].message
        tool_calls = list(getattr(message, "tool_calls", []) or [])
        if tool_calls:
            tool_call = tool_calls[0]
            raw_arguments = getattr(tool_call.function, "arguments", "") or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {}
            payload = {
                "tool_name": str(getattr(tool_call.function, "name", "") or "").strip(),
                "arguments": arguments,
                "content": str(getattr(message, "content", "") or "").strip(),
            }
            await record_timed_tool_call(
                "planner_llm_function_call",
                started_at=started,
                node_name="router",
                category="llm",
                output_summary=str(payload)[:200],
                status="ok",
            )
            return payload

        payload = {
            "tool_name": "",
            "arguments": {},
            "content": str(getattr(message, "content", "") or "").strip(),
        }
        await record_timed_tool_call(
            "planner_llm_function_call",
            started_at=started,
            node_name="router",
            category="llm",
            output_summary=str(payload)[:200],
            status="degraded",
        )
        return payload

    def _heuristic_response(self, user_prompt: str) -> dict[str, Any]:
        """
        启发式规则匹配，用于 LLM 不可用时的降级方案
        
        基于关键词匹配识别用户意图：
        - script: 销售话术、促单、卖点、库存等
        - analyst: 复盘、统计、高频问题、报告等
        - unknown: 无关或随机输入
        - qa: 默认意图（常见问题解答）
        
        Args:
            user_prompt: 用户输入提示词
            
        Returns:
            dict: 包含识别结果的字典
                {
                    "intent": str,  # 识别的意图
                    "confidence": float,  # 置信度（0.55-0.72）
                    "reason": str,  # 识别原因（"heuristic_fallback"）
                }
        """
        try:
            # 尝试解析 user_prompt 为 JSON
            payload = json.loads(user_prompt)
            lowered = str(payload.get("user_input", "")).lower()
        except json.JSONDecodeError:
            # 如果不是 JSON，直接转小写
            lowered = user_prompt.lower()

        tool_intent = self._infer_tool_intent(lowered)

        # 基于关键词匹配识别意图
        if any(keyword in lowered for keyword in ["卖点", "促单", "话术", "库存"]):
            # 销售话术相关
            intent = "script"
        elif any(keyword in lowered for keyword in ["复盘", "统计", "高频", "report"]):
            # 复盘分析相关
            intent = "analyst"
        elif tool_intent != "none":
            # 工具型问题统一归到 qa，由下游根据标准 tool_intent 调工具。
            intent = "qa"
        elif any(keyword in lowered for keyword in ["你好", "天气", "random", "乱码"]):
            # 无关或随机输入
            intent = "unknown"
        else:
            # 默认为常见问题解答
            intent = "qa"

        # 返回识别结果
        # unknown 意图的置信度较低（0.55），其他意图置信度为 0.72
        return {
            "intent": intent,
            "tool_intent": tool_intent,
            "confidence": 0.72 if intent != "unknown" else 0.55,
            "reason": "heuristic_fallback",
            "knowledge_scope": self._infer_knowledge_scope(lowered),
        }
    

    async def ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
        if self._client is None:
            raise RuntimeError("text client unavailable")

        started = perf_counter()
        try:
            response = await self._client.ainvoke(
                [
                    ("system", system_prompt),
                    ("human", user_prompt),
                ]
            )
        except Exception as exc:
            if self._is_timeout_error(exc):
                await record_timed_tool_call(
                    "direct_llm_text",
                    started_at=started,
                    node_name="direct",
                    category="llm",
                    output_summary="timeout",
                    status="degraded",
                )
                raise TimeoutError("direct text request timed out") from exc

            await record_timed_tool_call(
                "direct_llm_text",
                started_at=started,
                node_name="direct",
                category="llm",
                output_summary=str(exc),
                status="degraded",
            )
            raise

        content = str(response.content or "").strip()

        await record_timed_tool_call(
            "direct_llm_text",
            started_at=started,
            node_name="direct",
            category="llm",
            output_summary=content[:200],
            status="ok",
        )
        return content
