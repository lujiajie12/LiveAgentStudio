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
from typing import Any

from app.core.config import settings

try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover
    ChatOpenAI = None


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
        api_key  = settings.LLM_API_KEY or settings.OPENAI_API_KEY
        base_url = settings.LLM_BASE_URL or settings.OPENAI_BASE_URL
        model    = settings.LLM_MODEL or settings.ROUTER_MODEL

        if api_key and ChatOpenAI is not None:
            self._client = ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                timeout=settings.ROUTER_TIMEOUT_MS / 1000,
                temperature=0,
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

        try:
            response = await self._client.ainvoke(
                [
                    ("system", system_prompt),  # 系统角色消息
                    ("human", user_prompt),  # 用户消息
                ]
            )
        except Exception as exc:
            if self._is_timeout_error(exc):
                raise TimeoutError("LLM request timed out") from exc
            return self._heuristic_response(user_prompt)

        try:
            return self._extract_json_payload(str(response.content))
        except Exception:
            return self._heuristic_response(user_prompt)

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
        
        # 基于关键词匹配识别意图
        if any(keyword in lowered for keyword in ["卖点", "促单", "话术", "库存"]):
            # 销售话术相关
            intent = "script"
        elif any(keyword in lowered for keyword in ["复盘", "统计", "高频", "report"]):
            # 复盘分析相关
            intent = "analyst"
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
            "confidence": 0.72 if intent != "unknown" else 0.55,
            "reason": "heuristic_fallback",
            "knowledge_scope": self._infer_knowledge_scope(lowered),
        }
