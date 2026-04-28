from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")

CLASS_ORDER = [
    "direct",
    "qa",
    "script",
    "analyst",
    "datetime",
    "memory_recall",
    "web_search",
    "long_memory_write",
    "long_memory_recall",
    "long_memory_relevance",
    "long_memory_dedup",
    "long_memory_isolation",
    "long_memory_pollution_control",
    "memory_failure",
    "error",
]
ROUTE_METRIC_KEYS = ("intent", "agent_name", "route_target", "planner_action", "tool_intent", "route_label")
DEFAULT_ALL_DATASET_SIZE = 200


ROUTER_EXAMPLES: list[dict[str, Any]] = [
    {
        "inputs": {
            "case_id": "direct_identity_001",
            "case_type": "router",
            "user_input": "你是什么agent？",
            "current_product_id": None,
            "live_stage": "pitch",
        },
        "outputs": {"route_label": "direct", "intent": "direct", "agent_name": "direct"},
    },
    {
        "inputs": {
            "case_id": "direct_greeting_001",
            "case_type": "router",
            "user_input": "你好，在吗？",
            "current_product_id": "SKU-1",
            "live_stage": "warmup",
        },
        "outputs": {"route_label": "direct", "intent": "direct", "agent_name": "direct"},
    },
    {
        "inputs": {
            "case_id": "direct_capability_001",
            "case_type": "router",
            "user_input": "你能做什么？简单介绍一下你的功能。",
            "current_product_id": None,
            "live_stage": "warmup",
        },
        "outputs": {"route_label": "direct", "intent": "direct", "agent_name": "direct"},
    },
    {
        "inputs": {
            "case_id": "direct_vague_001",
            "case_type": "router",
            "user_input": "说点什么",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
        },
        "outputs": {"route_label": "direct", "intent": "direct", "agent_name": "direct"},
    },
    {
        "inputs": {
            "case_id": "direct_context_001",
            "case_type": "router",
            "user_input": "今天这场直播主推什么？",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
        },
        "outputs": {"route_label": "direct", "intent": "direct", "agent_name": "direct"},
    },
    {
        "inputs": {
            "case_id": "qa_product_audience_001",
            "case_type": "router",
            "user_input": "这款模块化拆洗的商品适合什么家庭？",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
        },
        "outputs": {"route_label": "qa", "intent": "qa", "agent_name": "qa"},
    },
    {
        "inputs": {
            "case_id": "qa_material_001",
            "case_type": "router",
            "user_input": "SKU-1 的主要材质是什么？",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
        },
        "outputs": {"route_label": "qa", "intent": "qa", "agent_name": "qa"},
    },
    {
        "inputs": {
            "case_id": "qa_shipping_001",
            "case_type": "router",
            "user_input": "下单后多久发货？运费谁出？",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
        },
        "outputs": {"route_label": "qa", "intent": "qa", "agent_name": "qa"},
    },
    {
        "inputs": {
            "case_id": "qa_after_sale_001",
            "case_type": "router",
            "user_input": "这个产品坏了怎么保修？支持退换货吗？",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
        },
        "outputs": {"route_label": "qa", "intent": "qa", "agent_name": "qa"},
    },
    {
        "inputs": {
            "case_id": "qa_compare_001",
            "case_type": "router",
            "user_input": "这款跟普通拖把相比有什么区别？",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
        },
        "outputs": {"route_label": "qa", "intent": "qa", "agent_name": "qa"},
    },
    {
        "inputs": {
            "case_id": "script_promo_001",
            "case_type": "router",
            "user_input": "帮我来一段促单话术，强调库存紧张和限时优惠。",
            "current_product_id": "SKU-1",
            "live_stage": "closing",
            "script_style": "促销型",
            "hot_keywords": ["库存", "优惠", "限时"],
            "live_offer_snapshot": {"display_stock": 92, "current_price": "89元", "countdown_seconds": 180},
        },
        "outputs": {"route_label": "script", "intent": "script", "agent_name": "script"},
    },
    {
        "inputs": {
            "case_id": "script_opening_001",
            "case_type": "router",
            "user_input": "写一段直播开场留人的话术，语气热情一点。",
            "current_product_id": "SKU-1",
            "live_stage": "warmup",
            "script_style": "热情型",
        },
        "outputs": {"route_label": "script", "intent": "script", "agent_name": "script"},
    },
    {
        "inputs": {
            "case_id": "script_gift_001",
            "case_type": "router",
            "user_input": "来一段强调赠品和优惠券的口播。",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
            "live_offer_snapshot": {"coupon_summary": "下单立减20元", "gift_summary": "赠清洁布1件"},
        },
        "outputs": {"route_label": "script", "intent": "script", "agent_name": "script"},
    },
    {
        "inputs": {
            "case_id": "script_stock_001",
            "case_type": "router",
            "user_input": "生成一段库存紧张提醒口播，别太夸张。",
            "current_product_id": "SKU-1",
            "live_stage": "closing",
            "hot_keywords": ["库存紧张"],
        },
        "outputs": {"route_label": "script", "intent": "script", "agent_name": "script"},
    },
    {
        "inputs": {
            "case_id": "script_demo_001",
            "case_type": "router",
            "user_input": "给这款商品写一段30秒讲解脚本。",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
        },
        "outputs": {"route_label": "script", "intent": "script", "agent_name": "script"},
    },
    {
        "inputs": {
            "case_id": "analyst_report_001",
            "case_type": "router",
            "user_input": "帮我生成本场直播复盘报告。",
            "current_product_id": "SKU-1",
            "live_stage": "closing",
        },
        "outputs": {"route_label": "analyst", "intent": "analyst", "agent_name": "analyst"},
    },
    {
        "inputs": {
            "case_id": "analyst_hfq_001",
            "case_type": "router",
            "user_input": "总结一下高频问题和未解决问题。",
            "current_product_id": "SKU-1",
            "live_stage": "closing",
        },
        "outputs": {"route_label": "analyst", "intent": "analyst", "agent_name": "analyst"},
    },
    {
        "inputs": {
            "case_id": "analyst_conversion_001",
            "case_type": "router",
            "user_input": "分析这场直播的转化表现，给我运营建议。",
            "current_product_id": "SKU-1",
            "live_stage": "closing",
        },
        "outputs": {"route_label": "analyst", "intent": "analyst", "agent_name": "analyst"},
    },
    {
        "inputs": {
            "case_id": "analyst_suggestions_001",
            "case_type": "router",
            "user_input": "输出一份本场直播的优化建议。",
            "current_product_id": "SKU-1",
            "live_stage": "closing",
        },
        "outputs": {"route_label": "analyst", "intent": "analyst", "agent_name": "analyst"},
    },
    {
        "inputs": {
            "case_id": "analyst_data_001",
            "case_type": "router",
            "user_input": "帮我做一份直播数据复盘。",
            "current_product_id": "SKU-1",
            "live_stage": "closing",
        },
        "outputs": {"route_label": "analyst", "intent": "analyst", "agent_name": "analyst"},
    },
    {
        "inputs": {
            "case_id": "datetime_weekday_001",
            "case_type": "router",
            "user_input": "今天是周几？",
            "current_product_id": None,
            "live_stage": "warmup",
        },
        "outputs": {"route_label": "datetime", "intent": "qa", "agent_name": "qa", "tool_intent": "datetime"},
    },
    {
        "inputs": {
            "case_id": "datetime_now_001",
            "case_type": "router",
            "user_input": "现在几点了？",
            "current_product_id": None,
            "live_stage": "warmup",
        },
        "outputs": {"route_label": "datetime", "intent": "qa", "agent_name": "qa", "tool_intent": "datetime"},
    },
    {
        "inputs": {
            "case_id": "datetime_tomorrow_001",
            "case_type": "router",
            "user_input": "明天是几月几号？",
            "current_product_id": None,
            "live_stage": "warmup",
        },
        "outputs": {"route_label": "datetime", "intent": "qa", "agent_name": "qa", "tool_intent": "datetime"},
    },
    {
        "inputs": {
            "case_id": "datetime_next_monday_001",
            "case_type": "router",
            "user_input": "下周一是几号？",
            "current_product_id": None,
            "live_stage": "warmup",
        },
        "outputs": {"route_label": "datetime", "intent": "qa", "agent_name": "qa", "tool_intent": "datetime"},
    },
    {
        "inputs": {
            "case_id": "datetime_current_date_001",
            "case_type": "router",
            "user_input": "当前日期是什么？",
            "current_product_id": None,
            "live_stage": "warmup",
        },
        "outputs": {"route_label": "datetime", "intent": "qa", "agent_name": "qa", "tool_intent": "datetime"},
    },
]


WEB_SEARCH_EXAMPLES: list[dict[str, Any]] = [
    {
        "inputs": {
            "case_id": "web_latest_001",
            "case_type": "router",
            "requires_env": ["SERPAPI_API_KEY"],
            "user_input": "帮我查一下今天黄金价格最新行情。",
            "current_product_id": None,
            "live_stage": "warmup",
        },
        "outputs": {"route_label": "web_search", "intent": "qa", "agent_name": "qa", "tool_intent": "web_search"},
    },
    {
        "inputs": {
            "case_id": "web_news_001",
            "case_type": "router",
            "requires_env": ["SERPAPI_API_KEY"],
            "user_input": "联网查一下今天直播电商有什么最新新闻。",
            "current_product_id": None,
            "live_stage": "warmup",
        },
        "outputs": {"route_label": "web_search", "intent": "qa", "agent_name": "qa", "tool_intent": "web_search"},
    },
]


MEMORY_EXAMPLES: list[dict[str, Any]] = [
    {
        "inputs": {
            "case_id": "memory_preference_001",
            "case_type": "memory",
            "steps": [
                {
                    "user_input": "我偏好直播话术短句、有紧迫感。请先记住这个偏好。",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
                {
                    "user_input": "刚刚我说的话术偏好是什么？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
            ],
        },
        "outputs": {
            "route_label": "memory_recall",
            "intent": "qa",
            "agent_name": "qa",
            "planner_action": "recall_memory",
            "tool_intent": "memory_recall",
            "expected_keywords": ["短句", "紧迫感"],
        },
    },
    {
        "inputs": {
            "case_id": "memory_latest_question_001",
            "case_type": "memory",
            "steps": [
                {
                    "user_input": "这款模块化拆洗的商品适合什么家庭？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
                {
                    "user_input": "刚刚我问的是什么问题？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
            ],
        },
        "outputs": {
            "route_label": "memory_recall",
            "intent": "qa",
            "agent_name": "qa",
            "planner_action": "recall_memory",
            "tool_intent": "memory_recall",
            "expected_keywords": ["模块化拆洗"],
        },
    },
    {
        "inputs": {
            "case_id": "memory_latest_answer_001",
            "case_type": "memory",
            "steps": [
                {
                    "user_input": "下单后多久发货？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
                {
                    "user_input": "你刚才是怎么回答我的？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
            ],
        },
        "outputs": {
            "route_label": "memory_recall",
            "intent": "qa",
            "agent_name": "qa",
            "planner_action": "recall_memory",
            "tool_intent": "memory_recall",
        },
    },
    {
        "inputs": {
            "case_id": "memory_question_list_001",
            "case_type": "memory",
            "steps": [
                {
                    "user_input": "这个产品保修多久？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
                {
                    "user_input": "这款适合有宠物的家庭吗？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
                {
                    "user_input": "前面两个问题分别是什么？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
            ],
        },
        "outputs": {
            "route_label": "memory_recall",
            "intent": "qa",
            "agent_name": "qa",
            "planner_action": "recall_memory",
            "tool_intent": "memory_recall",
            "expected_keywords": ["保修", "宠物"],
        },
    },
    {
        "inputs": {
            "case_id": "memory_dialogue_001",
            "case_type": "memory",
            "steps": [
                {
                    "user_input": "SKU-1 的主要卖点是什么？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
                {
                    "user_input": "我们刚才聊了什么？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
            ],
        },
        "outputs": {
            "route_label": "memory_recall",
            "intent": "qa",
            "agent_name": "qa",
            "planner_action": "recall_memory",
            "tool_intent": "memory_recall",
            "expected_keywords": ["卖点"],
        },
    },
]


LONG_MEMORY_EXAMPLES: list[dict[str, Any]] = [
    {
        "inputs": {
            "case_id": "ltm_write_preference_001",
            "case_type": "long_memory",
            "requires_long_memory": True,
            "insight_match_keywords": ["{marker}"],
            "write_steps": [
                {
                    "user_input": (
                        "SKU-1 讲解时请记住我的长期话术偏好，编号 {marker}："
                        "短句、有紧迫感、少用夸张词。这个偏好后续问答也请沿用。"
                    ),
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                }
            ],
        },
        "outputs": {
            "memory_label": "long_memory_write",
            "insights_enabled": True,
            "min_total_memories_delta": 1,
            "min_matching_memory_count": 1,
        },
    },
    {
        "inputs": {
            "case_id": "ltm_recall_preference_new_session_001",
            "case_type": "long_memory",
            "requires_long_memory": True,
            "insight_match_keywords": ["{marker}"],
            "write_steps": [
                {
                    "user_input": (
                        "SKU-1 直播答疑请记住我的偏好，编号 {marker}："
                        "回答要短句、有紧迫感、不要堆太多形容词。"
                    ),
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                }
            ],
            "recall_steps": [
                {
                    "user_input": "换一个新会话后，你还记得我编号 {marker} 的话术偏好吗？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                }
            ],
        },
        "outputs": {
            "memory_label": "long_memory_recall",
            "insights_enabled": True,
            "min_matching_memory_count": 1,
            "min_long_term_memory_hits": 1,
            "expected_keywords": ["短句", "紧迫感"],
        },
    },
    {
        "inputs": {
            "case_id": "ltm_recall_faq_new_session_001",
            "case_type": "long_memory",
            "requires_long_memory": True,
            "insight_match_keywords": ["{marker}"],
            "write_steps": [
                {
                    "user_input": (
                        "请记住 SKU-1 的常见 FAQ，编号 {marker}："
                        "用户经常问下单后多久发货、运费谁出，后续遇到发货问题先提醒以订单页为准。"
                    ),
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                }
            ],
            "recall_steps": [
                {
                    "user_input": "新会话里回忆一下，我之前记录的编号 {marker} 发货 FAQ 是什么？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                }
            ],
        },
        "outputs": {
            "memory_label": "long_memory_recall",
            "insights_enabled": True,
            "min_matching_memory_count": 1,
            "min_long_term_memory_hits": 1,
            "expected_keywords": ["发货", "运费"],
            "expected_memory_types_any": ["faq"],
        },
    },
    {
        "inputs": {
            "case_id": "ltm_relevance_preference_001",
            "case_type": "long_memory",
            "requires_long_memory": True,
            "insight_match_keywords": ["{marker}"],
            "write_steps": [
                {
                    "user_input": (
                        "SKU-1 的话术偏好编号 {marker}：我喜欢短句、有紧迫感、少铺垫。"
                    ),
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
                {
                    "user_input": (
                        "SKU-1 的售后 FAQ 编号 {marker}：保修和退换货以店铺规则为准。"
                    ),
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
            ],
            "recall_steps": [
                {
                    "user_input": "后续讲 SKU-1 时，我的话术风格偏好是什么？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                }
            ],
        },
        "outputs": {
            "memory_label": "long_memory_relevance",
            "insights_enabled": True,
            "min_matching_memory_count": 1,
            "min_long_term_memory_hits": 1,
            "expected_keywords": ["短句"],
            "expected_memory_types_any": ["operator_preference", "preference_signal"],
        },
    },
    {
        "inputs": {
            "case_id": "ltm_dedup_preference_001",
            "case_type": "long_memory",
            "requires_long_memory": True,
            "insight_match_keywords": ["{marker}"],
            "write_steps": [
                {
                    "user_input": (
                        "请记住 SKU-1 的重复偏好编号 {marker}：话术要短句、有紧迫感。"
                    ),
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
                {
                    "user_input": (
                        "请记住 SKU-1 的重复偏好编号 {marker}：话术要短句、有紧迫感。"
                    ),
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                },
            ],
        },
        "outputs": {
            "memory_label": "long_memory_dedup",
            "insights_enabled": True,
            "min_matching_memory_count": 1,
            "max_duplicate_memory_count": 2,
        },
    },
    {
        "inputs": {
            "case_id": "ltm_isolation_cross_user_001",
            "case_type": "long_memory",
            "requires_long_memory": True,
            "insight_match_keywords": ["{marker}"],
            "write_steps": [
                {
                    "user_input": (
                        "SKU-1 的私有话术偏好编号 {marker}：回答必须短句、有紧迫感。"
                    ),
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                }
            ],
            "other_user_recall_steps": [
                {
                    "user_input": "你还记得我的 SKU-1 话术偏好吗？",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                }
            ],
        },
        "outputs": {
            "memory_label": "long_memory_isolation",
            "insights_enabled": True,
            "min_matching_memory_count": 1,
            "other_user_max_long_term_memory_hits": 0,
            "other_user_forbidden_keywords": ["{marker}", "短句", "紧迫感"],
        },
    },
    {
        "inputs": {
            "case_id": "ltm_pollution_meta_query_not_written_001",
            "case_type": "long_memory",
            "requires_long_memory": True,
            "expect_memory_write": False,
            "insight_match_keywords": ["{marker}"],
            "write_steps": [
                {
                    "user_input": "刚刚我问的问题是什么？测试编号 {marker}",
                    "current_product_id": "SKU-1",
                    "live_stage": "pitch",
                }
            ],
        },
        "outputs": {
            "memory_label": "long_memory_pollution_control",
            "insights_enabled": True,
            "max_total_memories_delta": 0,
            "max_matching_memory_count": 0,
        },
    },
]


PRODUCT_VARIANTS = ["SKU-1", "SKU-2", "SKU-3", "SKU-4", "SKU-5"]
LIVE_STAGE_VARIANTS = ["warmup", "pitch", "closing"]

ROUTER_ONLY_DISTRIBUTION = {
    "direct": 40,
    "qa": 50,
    "script": 50,
    "analyst": 30,
    "datetime": 30,
}
ALL_DISTRIBUTION_WITH_LONG_MEMORY = {
    "direct": 25,
    "qa": 35,
    "script": 35,
    "analyst": 25,
    "datetime": 25,
    "memory_recall": 25,
    "long_memory": 30,
}
ALL_DISTRIBUTION_WITH_LONG_MEMORY_AND_WEB = {
    "direct": 25,
    "qa": 30,
    "script": 30,
    "analyst": 25,
    "datetime": 25,
    "memory_recall": 25,
    "long_memory": 30,
    "web_search": 10,
}
ALL_DISTRIBUTION_NO_LONG_MEMORY = {
    "direct": 30,
    "qa": 45,
    "script": 45,
    "analyst": 30,
    "datetime": 30,
    "memory_recall": 20,
}
ALL_DISTRIBUTION_NO_LONG_MEMORY_AND_WEB = {
    "direct": 30,
    "qa": 40,
    "script": 40,
    "analyst": 30,
    "datetime": 30,
    "memory_recall": 20,
    "web_search": 10,
}

ROUTER_PROMPTS = {
    "direct": [
        "你好，在吗？",
        "你是谁？",
        "你能做什么？",
        "先简单介绍一下你的能力。",
        "测试一下连接是否正常。",
        "收到，准备开始。",
        "你是直播中台助手吗？",
        "用一句话说明你的职责。",
        "现在先不要查商品，告诉我你能协助哪些直播工作。",
        "我想了解一下系统能力。",
        "这轮对话开始了，先打个招呼。",
        "你支持哪些智能体能力？",
    ],
    "qa": [
        "{product_id} 的核心卖点是什么？",
        "{product_id} 适合什么人群？",
        "{product_id} 的主要材质是什么？",
        "{product_id} 下单后多久发货？",
        "{product_id} 运费谁承担？",
        "{product_id} 支持退换货吗？",
        "{product_id} 坏了怎么保修？",
        "{product_id} 怎么清洗和维护？",
        "{product_id} 和普通款有什么区别？",
        "{product_id} 适合有宠物的家庭吗？",
        "{product_id} 小朋友能不能使用？",
        "{product_id} 噪音大不大？",
        "{product_id} 有哪些赠品？",
        "{product_id} 优惠价格以哪里为准？",
    ],
    "script": [
        "给 {product_id} 写一段30秒口播脚本。",
        "帮我生成 {product_id} 的促单话术，强调限时优惠。",
        "写一段 {product_id} 的开场留人话术。",
        "来一段 {product_id} 的库存紧张提醒，别太夸张。",
        "把 {product_id} 的卖点写成两版直播话术。",
        "生成 {product_id} 的福利款口播，突出赠品和优惠券。",
        "给 {product_id} 写一段适合收尾逼单的话术。",
        "写一段 {product_id} 的场景化讲解脚本。",
        "用主播口吻介绍 {product_id}，语气亲切一点。",
        "帮我把 {product_id} 的材质优势改成直播短句。",
        "给 {product_id} 写一段不浮夸的种草话术。",
        "写一段 {product_id} 的对比型讲解脚本。",
        "帮我生成 {product_id} 的三句话促单话术。",
        "给 {product_id} 写一个用户追问后的承接话术。",
    ],
    "analyst": [
        "帮我生成本场直播复盘报告。",
        "总结一下高频问题和未解决问题。",
        "分析这场直播的转化表现，给我运营建议。",
        "输出一份本场直播的优化建议。",
        "帮我做一份直播数据复盘。",
        "复盘一下刚才观众最关心哪些问题。",
        "整理本场直播的话术问题和改进方向。",
        "分析一下本场讲解节奏有什么问题。",
        "给我一份主播表现复盘。",
        "汇总本场直播的售后疑问和风险点。",
    ],
    "datetime": [
        "今天是周几？",
        "现在几点了？",
        "明天是几月几号？",
        "下周一是几号？",
        "当前日期是什么？",
        "今天距离月底还有几天？",
        "三天后是星期几？",
        "本周五是几号？",
        "现在是上午还是下午？",
        "下个月第一天是星期几？",
    ],
}

SCRIPT_STYLE_VARIANTS = ["促销型", "专业型", "亲切型", "热情型", "简洁型"]
SCRIPT_KEYWORD_VARIANTS = [
    ["库存", "优惠", "限时"],
    ["卖点", "场景", "省心"],
    ["赠品", "优惠券"],
    ["对比", "耐用"],
    ["短句", "紧迫感"],
]
OFFER_VARIANTS = [
    {"display_stock": 92, "current_price": "89元", "countdown_seconds": 180},
    {"display_stock": 56, "current_price": "129元", "coupon_summary": "下单立减20元"},
    {"display_stock": 38, "gift_summary": "赠清洁布1件", "countdown_seconds": 300},
    {"display_stock": 120, "current_price": "69元", "coupon_summary": "第二件半价"},
]


@dataclass
class EvalContext:
    base_url: str
    token: str
    chat_timeout: float
    session_prefix: str
    username: str
    user_id: str
    password: str
    role: str
    login_timeout: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run LiveAgent router and memory regression cases, optionally as a LangSmith experiment."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--username", default="langsmith_eval", help="Login username")
    parser.add_argument("--password", default="demo", help="Login password")
    parser.add_argument("--role", default="operator", help="Login role")
    parser.add_argument("--mode", choices=["router", "memory", "long_memory", "all"], default="all")
    parser.add_argument("--include-web-search", action="store_true", help="Include web-search cases requiring SerpAPI.")
    parser.add_argument("--session-prefix", default="", help="Optional fixed session prefix")
    parser.add_argument("--health-timeout", type=float, default=5.0)
    parser.add_argument("--login-timeout", type=float, default=15.0)
    parser.add_argument("--chat-timeout", type=float, default=180.0)
    parser.add_argument("--langsmith", action="store_true", help="Run through langsmith.evaluate")
    parser.add_argument(
        "--dataset-name",
        default="liveagent-router-memory-routing-v1",
        help="LangSmith dataset name for --create-dataset or --langsmith dataset runs",
    )
    parser.add_argument(
        "--create-dataset",
        action="store_true",
        help="Create/sync the LangSmith dataset, then use it for evaluation.",
    )
    parser.add_argument(
        "--sync-dataset-only",
        action="store_true",
        help="Only create/update the LangSmith dataset examples; do not call the backend or run evaluation.",
    )
    parser.add_argument(
        "--dataset-size",
        type=int,
        default=DEFAULT_ALL_DATASET_SIZE,
        help="Target example count for --mode all. Use 0 to keep only the compact seed suite.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print full outputs for every case.")
    parser.add_argument("--metrics-output", default="", help="Optional path to write metrics JSON.")
    parser.add_argument("--fail-on-mismatch", action="store_true", help="Exit non-zero when any case is misrouted.")
    return parser.parse_args()


def build_examples(
    mode: str,
    *,
    include_web_search: bool = False,
    dataset_size: int = DEFAULT_ALL_DATASET_SIZE,
) -> list[dict[str, Any]]:
    router_examples = list(ROUTER_EXAMPLES)
    if include_web_search:
        router_examples.extend(WEB_SEARCH_EXAMPLES)
    if mode == "router":
        return filter_examples_by_env(router_examples)
    if mode == "memory":
        return list(MEMORY_EXAMPLES)
    if mode == "long_memory":
        return list(LONG_MEMORY_EXAMPLES)
    if dataset_size <= 0:
        return [*filter_examples_by_env(router_examples), *MEMORY_EXAMPLES, *filter_examples_by_env(LONG_MEMORY_EXAMPLES)]
    return build_all_suite(dataset_size, include_web_search=include_web_search)


def build_all_suite(target_size: int, *, include_web_search: bool = False) -> list[dict[str, Any]]:
    include_long_memory = long_memory_env_configured()
    include_web = include_web_search and bool(os.getenv("SERPAPI_API_KEY"))
    if include_long_memory and include_web:
        distribution = ALL_DISTRIBUTION_WITH_LONG_MEMORY_AND_WEB
    elif include_long_memory:
        distribution = ALL_DISTRIBUTION_WITH_LONG_MEMORY
    elif include_web:
        distribution = ALL_DISTRIBUTION_NO_LONG_MEMORY_AND_WEB
    else:
        distribution = ALL_DISTRIBUTION_NO_LONG_MEMORY
    distribution = scale_distribution(distribution, target_size)

    examples: list[dict[str, Any]] = []
    router_targets = {label: distribution.get(label, 0) for label in ROUTER_PROMPTS}
    examples.extend(build_router_examples_by_distribution(router_targets))
    examples.extend(expand_short_memory_examples(distribution.get("memory_recall", 0)))
    if include_long_memory:
        examples.extend(expand_long_memory_examples(distribution.get("long_memory", 0)))
    if include_web:
        examples.extend(expand_pool_examples(WEB_SEARCH_EXAMPLES, distribution.get("web_search", 0), "web_search"))
    return examples[:target_size]


def build_router_suite(target_size: int, *, include_web_search: bool = False) -> list[dict[str, Any]]:
    distribution = scale_distribution(ROUTER_ONLY_DISTRIBUTION, target_size)
    examples = build_router_examples_by_distribution(distribution)
    if include_web_search and os.getenv("SERPAPI_API_KEY"):
        examples.extend(expand_pool_examples(WEB_SEARCH_EXAMPLES, min(10, max(target_size // 20, 1)), "web_search"))
    return examples[:target_size]


def build_router_examples_by_distribution(distribution: dict[str, int]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for label in ("direct", "qa", "script", "analyst", "datetime"):
        examples.extend(expand_router_label_examples(label, distribution.get(label, 0)))
    return examples


def scale_distribution(base: dict[str, int], target_size: int) -> dict[str, int]:
    if target_size <= 0:
        return {key: 0 for key in base}
    total = sum(base.values())
    if total <= 0:
        return {}
    scaled: dict[str, int] = {}
    remainders: list[tuple[float, str]] = []
    allocated = 0
    for key, value in base.items():
        raw = target_size * value / total
        floor = int(raw)
        scaled[key] = floor
        allocated += floor
        remainders.append((raw - floor, key))
    for _, key in sorted(remainders, reverse=True)[: max(target_size - allocated, 0)]:
        scaled[key] += 1
    return scaled


def expand_router_label_examples(label: str, target_count: int) -> list[dict[str, Any]]:
    existing = [deepcopy(item) for item in ROUTER_EXAMPLES if item.get("outputs", {}).get("route_label") == label]
    examples = existing[:target_count]
    generated_index = 1
    while len(examples) < target_count:
        examples.append(make_router_example(label, generated_index))
        generated_index += 1
    return examples


def make_router_example(label: str, index: int) -> dict[str, Any]:
    product_id = PRODUCT_VARIANTS[(index - 1) % len(PRODUCT_VARIANTS)]
    prompt = ROUTER_PROMPTS[label][(index - 1) % len(ROUTER_PROMPTS[label])].format(product_id=product_id)
    payload: dict[str, Any] = {
        "case_id": f"{label}_expanded_{index:03d}",
        "case_type": "router",
        "user_input": prompt,
        "current_product_id": product_id if label in {"qa", "script", "analyst"} else None,
        "live_stage": LIVE_STAGE_VARIANTS[(index - 1) % len(LIVE_STAGE_VARIANTS)],
    }
    outputs: dict[str, Any]
    if label == "datetime":
        payload["current_product_id"] = None
        outputs = {"route_label": "datetime", "intent": "qa", "agent_name": "qa", "tool_intent": "datetime"}
    else:
        outputs = {"route_label": label, "intent": label, "agent_name": label}

    if label == "qa":
        outputs = {"route_label": "qa", "intent": "qa", "agent_name": "qa"}
    elif label == "script":
        payload["script_style"] = SCRIPT_STYLE_VARIANTS[(index - 1) % len(SCRIPT_STYLE_VARIANTS)]
        payload["hot_keywords"] = SCRIPT_KEYWORD_VARIANTS[(index - 1) % len(SCRIPT_KEYWORD_VARIANTS)]
        payload["live_offer_snapshot"] = OFFER_VARIANTS[(index - 1) % len(OFFER_VARIANTS)]
    elif label == "analyst":
        payload["live_stage"] = "closing"
    elif label == "direct" and index % 3 == 0:
        payload["current_product_id"] = product_id
    return {"inputs": payload, "outputs": outputs}


def expand_short_memory_examples(target_count: int) -> list[dict[str, Any]]:
    return expand_pool_examples(MEMORY_EXAMPLES, target_count, "memory_recall")


def expand_long_memory_examples(target_count: int) -> list[dict[str, Any]]:
    return expand_pool_examples(LONG_MEMORY_EXAMPLES, target_count, "long_memory")


def expand_pool_examples(pool: list[dict[str, Any]], target_count: int, prefix: str) -> list[dict[str, Any]]:
    if target_count <= 0 or not pool:
        return []
    examples = [deepcopy(item) for item in pool[:target_count]]
    generated_index = 1
    while len(examples) < target_count:
        base = deepcopy(pool[(generated_index - 1) % len(pool)])
        product_id = PRODUCT_VARIANTS[(generated_index - 1) % len(PRODUCT_VARIANTS)]
        base = replace_product_id(base, product_id)
        stem = str(base.get("inputs", {}).get("case_id") or prefix)
        stem = stem[:-4] if stem.endswith("_001") else stem
        base["inputs"]["case_id"] = f"{stem}_expanded_{generated_index:03d}"
        examples.append(base)
        generated_index += 1
    return examples


def replace_product_id(value: Any, product_id: str) -> Any:
    if isinstance(value, str):
        return value.replace("SKU-1", product_id)
    if isinstance(value, list):
        return [replace_product_id(item, product_id) for item in value]
    if isinstance(value, tuple):
        return tuple(replace_product_id(item, product_id) for item in value)
    if isinstance(value, dict):
        return {key: replace_product_id(item, product_id) for key, item in value.items()}
    return value


def filter_examples_by_env(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = []
    for example in examples:
        if example.get("inputs", {}).get("requires_long_memory") and not long_memory_env_configured():
            continue
        required = list(example.get("inputs", {}).get("requires_env") or [])
        if all(os.getenv(name) for name in required):
            filtered.append(example)
    return filtered


def long_memory_env_configured() -> bool:
    enabled = str(os.getenv("QA_MEMORY_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}
    return enabled and bool(str(os.getenv("MEM0_API_KEY") or "").strip())


def check_health(base_url: str, timeout_s: float) -> None:
    response = requests.get(f"{base_url}/health", timeout=(5, timeout_s))
    response.raise_for_status()


def login(base_url: str, username: str, password: str, role: str, timeout_s: float) -> str:
    response = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
        timeout=(5, timeout_s),
    )
    response.raise_for_status()
    return response.json()["data"]["access_token"]


def fetch_current_user(base_url: str, token: str, timeout_s: float) -> dict[str, Any]:
    response = requests.get(
        f"{base_url}/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=(5, timeout_s),
    )
    response.raise_for_status()
    return dict(response.json()["data"])


def make_eval_context_for_user(ctx: EvalContext, username: str) -> EvalContext:
    token = login(ctx.base_url, username, ctx.password, ctx.role, ctx.login_timeout)
    current_user = fetch_current_user(ctx.base_url, token, ctx.login_timeout)
    return EvalContext(
        base_url=ctx.base_url,
        token=token,
        chat_timeout=ctx.chat_timeout,
        session_prefix=ctx.session_prefix,
        username=username,
        user_id=str(current_user.get("id") or ""),
        password=ctx.password,
        role=ctx.role,
        login_timeout=ctx.login_timeout,
    )


def case_username(base_username: str, case_id: str, suffix: str = "lm") -> str:
    stem = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in base_username)[:32] or "eval"
    return f"{stem}_{suffix}_{uuid.uuid4().hex[:12]}"[:64]


def stream_chat(ctx: EvalContext, *, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    trace_id = f"eval-{uuid.uuid4().hex[:12]}"
    response = post_chat_stream(ctx, trace_id=trace_id, session_id=session_id, payload=payload)
    if response.status_code == 401:
        ctx.token = login(ctx.base_url, ctx.username, ctx.password, ctx.role, ctx.login_timeout)
        current_user = fetch_current_user(ctx.base_url, ctx.token, ctx.login_timeout)
        ctx.user_id = str(current_user.get("id") or ctx.user_id)
        response.close()
        response = post_chat_stream(ctx, trace_id=trace_id, session_id=session_id, payload=payload)
    response.raise_for_status()

    current_event = None
    final_payload = None
    error_payload = None
    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        line = str(raw_line)
        if line.startswith("event: "):
            current_event = line[len("event: ") :]
            continue
        if line.startswith("data: "):
            data = json.loads(line[len("data: ") :])
            if current_event == "final":
                final_payload = data
            elif current_event == "error":
                error_payload = data

    if error_payload is not None:
        raise RuntimeError(f"chat stream error trace_id={trace_id}: {error_payload}")
    if final_payload is None:
        raise AssertionError(f"No final SSE payload received trace_id={trace_id}")

    message = final_payload["message"]
    metadata = message.get("metadata") or {}
    long_term_memories = list(metadata.get("long_term_memories") or [])
    output = {
        "case_id": payload.get("case_id"),
        "trace_id": trace_id,
        "session_id": session_id,
        "intent": final_payload.get("intent"),
        "guardrail_pass": final_payload.get("guardrail_pass"),
        "content": message.get("content", ""),
        "agent_name": message.get("agent_name"),
        "route_target": metadata.get("route_target"),
        "planner_action": metadata.get("planner_action"),
        "tool_intent": metadata.get("tool_intent"),
        "long_term_memory_hits": metadata.get("long_term_memory_hits", 0),
        "long_term_memories": long_term_memories,
        "long_term_memory_types": extract_memory_types(long_term_memories),
        "metadata": metadata,
    }
    output["route_label"] = derive_route_label(output)
    return output


def post_chat_stream(
    ctx: EvalContext,
    *,
    trace_id: str,
    session_id: str,
    payload: dict[str, Any],
) -> requests.Response:
    return requests.post(
        f"{ctx.base_url}/api/v1/chat/stream",
        headers={
            "Authorization": f"Bearer {ctx.token}",
            "x-trace-id": trace_id,
        },
        json={
            "session_id": session_id,
            "user_input": payload["user_input"],
            "current_product_id": payload.get("current_product_id"),
            "live_stage": payload.get("live_stage", "pitch"),
            "script_style": payload.get("script_style"),
            "hot_keywords": payload.get("hot_keywords", []),
            "live_offer_snapshot": payload.get("live_offer_snapshot", {}),
        },
        stream=True,
        timeout=(5, ctx.chat_timeout),
    )


def derive_route_label(output: dict[str, Any]) -> str:
    planner_action = str(output.get("planner_action") or "").strip()
    tool_intent = str(output.get("tool_intent") or "").strip()
    agent_name = str(output.get("agent_name") or "").strip()
    route_target = str(output.get("route_target") or "").strip()
    intent = str(output.get("intent") or "").strip()
    if planner_action == "call_datetime" or tool_intent == "datetime":
        return "datetime"
    if planner_action == "call_web_search" or tool_intent == "web_search":
        return "web_search"
    if planner_action == "recall_memory" or tool_intent == "memory_recall":
        return "memory_recall"
    if agent_name in {"direct", "qa", "script", "analyst"}:
        return agent_name
    if route_target in {"direct", "qa", "script", "analyst"}:
        return route_target
    if intent in {"direct", "qa", "script", "analyst"}:
        return intent
    return "error"


def run_router_case(ctx: EvalContext, inputs: dict[str, Any]) -> dict[str, Any]:
    session_id = inputs.get("session_id") or f"{ctx.session_prefix}-router-{uuid.uuid4().hex[:8]}"
    return stream_chat(ctx, session_id=session_id, payload=inputs)


def run_memory_case(ctx: EvalContext, inputs: dict[str, Any]) -> dict[str, Any]:
    session_id = inputs.get("session_id") or f"{ctx.session_prefix}-memory-{uuid.uuid4().hex[:8]}"
    outputs = []
    for step in inputs.get("steps", []):
        outputs.append(stream_chat(ctx, session_id=session_id, payload=step))
    if not outputs:
        raise AssertionError("memory case requires at least one step")
    final_output = dict(outputs[-1])
    final_output["case_id"] = inputs.get("case_id")
    final_output["step_outputs"] = outputs
    final_output["route_label"] = derive_route_label(final_output)
    return final_output


def run_long_memory_case(ctx: EvalContext, inputs: dict[str, Any]) -> dict[str, Any]:
    case_id = str(inputs.get("case_id") or f"ltm-{uuid.uuid4().hex[:8]}")
    marker = str(inputs.get("marker") or f"LSMEM-{uuid.uuid4().hex[:10]}")
    primary_ctx = ctx
    if not inputs.get("reuse_eval_user"):
        primary_ctx = make_eval_context_for_user(ctx, case_username(ctx.username, case_id, "lm"))

    insights_before = get_memory_insights(primary_ctx, user_id=primary_ctx.user_id)
    if not insights_before.get("enabled"):
        return {
            "case_id": case_id,
            "marker": marker,
            "content": "long-term memory is disabled",
            "guardrail_pass": True,
            "primary_username": primary_ctx.username,
            "primary_user_id": primary_ctx.user_id,
            "insights_enabled": False,
            "total_memories_before": 0,
            "total_memories_after": 0,
            "total_memories_delta": 0,
            "matching_memory_count": 0,
            "duplicate_memory_count": 0,
            "insights_before": compact_insights(insights_before),
            "insights_after": compact_insights(insights_before),
        }
    write_session_id = inputs.get("write_session_id") or make_eval_session_id(ctx.session_prefix, case_id, "lw")
    write_outputs: list[dict[str, Any]] = []
    for step in inputs.get("write_steps", []):
        payload = format_case_value(step, marker)
        payload["case_id"] = case_id
        write_outputs.append(stream_chat(primary_ctx, session_id=write_session_id, payload=payload))

    wait_seconds = float(inputs.get("post_write_wait_seconds", 1.0))
    if wait_seconds > 0:
        time.sleep(wait_seconds)

    insights_after = get_memory_insights(primary_ctx, user_id=primary_ctx.user_id)
    match_keywords = [str(item) for item in format_case_value(inputs.get("insight_match_keywords") or [], marker) if str(item)]
    if expects_long_memory_write(inputs):
        max_wait_seconds = float(inputs.get("post_write_max_wait_seconds", 8.0))
        deadline = time.monotonic() + max(max_wait_seconds - wait_seconds, 0.0)
        while time.monotonic() < deadline and match_keywords and count_matching_memories(insights_after, match_keywords) <= 0:
            time.sleep(1.0)
            insights_after = get_memory_insights(primary_ctx, user_id=primary_ctx.user_id)

    recall_session_id = inputs.get("recall_session_id") or make_eval_session_id(ctx.session_prefix, case_id, "lr")
    recall_outputs: list[dict[str, Any]] = []
    for step in inputs.get("recall_steps", []):
        payload = format_case_value(step, marker)
        payload["case_id"] = case_id
        recall_outputs.append(stream_chat(primary_ctx, session_id=recall_session_id, payload=payload))

    other_user_outputs: list[dict[str, Any]] = []
    other_ctx: EvalContext | None = None
    if inputs.get("other_user_recall_steps"):
        other_ctx = make_eval_context_for_user(ctx, case_username(ctx.username, case_id, "iso"))
        other_session_id = make_eval_session_id(ctx.session_prefix, case_id, "lo")
        for step in inputs.get("other_user_recall_steps", []):
            payload = format_case_value(step, marker)
            payload["case_id"] = case_id
            other_user_outputs.append(stream_chat(other_ctx, session_id=other_session_id, payload=payload))

    final_source = (
        other_user_outputs[-1]
        if other_user_outputs and inputs.get("use_other_user_output_as_final")
        else recall_outputs[-1]
        if recall_outputs
        else write_outputs[-1]
        if write_outputs
        else {"content": "", "guardrail_pass": True}
    )
    output = dict(final_source)
    output["case_id"] = case_id
    output["marker"] = marker
    output["primary_username"] = primary_ctx.username
    output["primary_user_id"] = primary_ctx.user_id
    output["insights_enabled"] = bool(insights_after.get("enabled"))
    output["total_memories_before"] = int((insights_before.get("overview") or {}).get("total_memories") or 0)
    output["total_memories_after"] = int((insights_after.get("overview") or {}).get("total_memories") or 0)
    output["total_memories_delta"] = output["total_memories_after"] - output["total_memories_before"]
    matching_count = count_matching_memories(insights_after, match_keywords)
    output["matching_memory_count"] = matching_count
    output["duplicate_memory_count"] = matching_count
    output["write_outputs"] = write_outputs
    output["recall_outputs"] = recall_outputs
    output["insights_before"] = compact_insights(insights_before)
    output["insights_after"] = compact_insights(insights_after)

    if other_ctx is not None:
        output["other_username"] = other_ctx.username
        output["other_user_id"] = other_ctx.user_id
        output["other_user_outputs"] = other_user_outputs
        output["other_user_content"] = other_user_outputs[-1].get("content", "") if other_user_outputs else ""
        output["other_user_long_term_memory_hits"] = (
            other_user_outputs[-1].get("long_term_memory_hits", 0) if other_user_outputs else 0
        )
        output["other_user_long_term_memory_types"] = (
            other_user_outputs[-1].get("long_term_memory_types", []) if other_user_outputs else []
        )
    return output


def expects_long_memory_write(inputs: dict[str, Any]) -> bool:
    if inputs.get("expect_memory_write") is not None:
        return bool(inputs.get("expect_memory_write"))
    text = " ".join(str(step.get("user_input") or "") for step in inputs.get("write_steps", []))
    return any(keyword in text for keyword in ("记住", "偏好", "FAQ", "faq", "我喜欢", "售后"))


def make_eval_session_id(session_prefix: str, case_id: str, kind: str) -> str:
    """Generate DB-safe session ids; production schema caps sessions.id at 36 chars."""
    prefix = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in str(session_prefix or "ls-eval"))[:16]
    case_hash = hashlib.sha1(str(case_id or "").encode("utf-8")).hexdigest()[:6]
    suffix = uuid.uuid4().hex[:8]
    return f"{prefix}-{kind[:2]}-{case_hash}-{suffix}"[:36]


def run_case(ctx: EvalContext, inputs: dict[str, Any]) -> dict[str, Any]:
    if inputs.get("case_type") == "long_memory":
        return run_long_memory_case(ctx, inputs)
    if inputs.get("case_type") == "memory":
        return run_memory_case(ctx, inputs)
    return run_router_case(ctx, inputs)


def get_memory_insights(ctx: EvalContext, *, user_id: str | None = None, limit: int = 120) -> dict[str, Any]:
    response = requests.get(
        f"{ctx.base_url}/api/v1/memory/qa/insights",
        headers={"Authorization": f"Bearer {ctx.token}"},
        params={"user_id": user_id or ctx.user_id, "limit": limit},
        timeout=(5, ctx.chat_timeout),
    )
    if response.status_code == 401:
        ctx.token = login(ctx.base_url, ctx.username, ctx.password, ctx.role, ctx.login_timeout)
        current_user = fetch_current_user(ctx.base_url, ctx.token, ctx.login_timeout)
        ctx.user_id = str(current_user.get("id") or ctx.user_id)
        response = requests.get(
            f"{ctx.base_url}/api/v1/memory/qa/insights",
            headers={"Authorization": f"Bearer {ctx.token}"},
            params={"user_id": user_id or ctx.user_id, "limit": limit},
            timeout=(5, ctx.chat_timeout),
        )
    response.raise_for_status()
    return dict(response.json().get("data") or {})


def format_case_value(value: Any, marker: str) -> Any:
    if isinstance(value, str):
        return value.replace("{marker}", marker)
    if isinstance(value, list):
        return [format_case_value(item, marker) for item in value]
    if isinstance(value, tuple):
        return tuple(format_case_value(item, marker) for item in value)
    if isinstance(value, dict):
        return {key: format_case_value(item, marker) for key, item in value.items()}
    return value


def extract_memory_types(memories: list[dict[str, Any]]) -> list[str]:
    types: list[str] = []
    for memory in memories:
        metadata = dict(memory.get("metadata") or {})
        for item in metadata.get("memory_types") or []:
            label = str(item).strip()
            if label and label not in types:
                types.append(label)
    return types


def iter_insight_memory_items(insights: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_item(item: dict[str, Any]) -> None:
        memory_id = str(item.get("memory_id") or "")
        identity = memory_id or json.dumps(item, ensure_ascii=False, sort_keys=True)
        if identity in seen:
            return
        seen.add(identity)
        items.append(item)

    for key in ("recent_memories", "operator_preferences"):
        for item in insights.get(key) or []:
            if isinstance(item, dict):
                add_item(item)

    for group in insights.get("product_facts") or []:
        if not isinstance(group, dict):
            continue
        for item in group.get("items") or []:
            if isinstance(item, dict):
                add_item(item)
    return items


def count_matching_memories(insights: dict[str, Any], keywords: list[str]) -> int:
    if not keywords:
        return 0
    count = 0
    for item in iter_insight_memory_items(insights):
        text = " ".join(
            str(item.get(key) or "")
            for key in ("summary", "question_preview", "current_product_id")
        )
        if all(keyword in text for keyword in keywords):
            count += 1
    return count


def compact_insights(insights: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": bool(insights.get("enabled")),
        "scope": insights.get("scope") or {},
        "overview": insights.get("overview") or {},
        "recent_memories": (insights.get("recent_memories") or [])[:5],
        "operator_preferences": (insights.get("operator_preferences") or [])[:5],
        "faq_hotspots": (insights.get("faq_hotspots") or [])[:5],
    }


def compare_output(outputs: dict[str, Any], expected: dict[str, Any]) -> tuple[bool, str]:
    failures: list[str] = []
    expected = format_case_value(expected, str(outputs.get("marker") or ""))
    for key in ROUTE_METRIC_KEYS:
        expected_value = expected.get(key)
        if expected_value is None:
            continue
        if outputs.get(key) != expected_value:
            failures.append(f"{key}: expected {expected_value!r}, got {outputs.get(key)!r}")

    expected_keywords = [str(item) for item in expected.get("expected_keywords", []) if str(item)]
    content = str(outputs.get("content") or "")
    missing_keywords = [item for item in expected_keywords if item not in content]
    if missing_keywords:
        failures.append(f"missing keywords in content: {missing_keywords}")

    forbidden_keywords = [str(item) for item in expected.get("forbidden_keywords", []) if str(item)]
    leaked_keywords = [item for item in forbidden_keywords if item in content]
    if leaked_keywords:
        failures.append(f"forbidden keywords in content: {leaked_keywords}")

    min_memory_hits = expected.get("min_long_term_memory_hits")
    if min_memory_hits is not None and int(outputs.get("long_term_memory_hits") or 0) < int(min_memory_hits):
        failures.append(
            "long_term_memory_hits: "
            f"expected >= {min_memory_hits}, got {outputs.get('long_term_memory_hits')!r}"
        )
    max_memory_hits = expected.get("max_long_term_memory_hits")
    if max_memory_hits is not None and int(outputs.get("long_term_memory_hits") or 0) > int(max_memory_hits):
        failures.append(
            "long_term_memory_hits: "
            f"expected <= {max_memory_hits}, got {outputs.get('long_term_memory_hits')!r}"
        )

    if expected.get("insights_enabled") is not None and bool(outputs.get("insights_enabled")) != bool(
        expected.get("insights_enabled")
    ):
        failures.append(
            "insights_enabled: "
            f"expected {bool(expected.get('insights_enabled'))!r}, got {outputs.get('insights_enabled')!r}"
        )

    min_delta = expected.get("min_total_memories_delta")
    if min_delta is not None and int(outputs.get("total_memories_delta") or 0) < int(min_delta):
        failures.append(
            "total_memories_delta: "
            f"expected >= {min_delta}, got {outputs.get('total_memories_delta')!r}"
        )
    max_delta = expected.get("max_total_memories_delta")
    if max_delta is not None and int(outputs.get("total_memories_delta") or 0) > int(max_delta):
        failures.append(
            "total_memories_delta: "
            f"expected <= {max_delta}, got {outputs.get('total_memories_delta')!r}"
        )

    min_matching = expected.get("min_matching_memory_count")
    if min_matching is not None and int(outputs.get("matching_memory_count") or 0) < int(min_matching):
        failures.append(
            "matching_memory_count: "
            f"expected >= {min_matching}, got {outputs.get('matching_memory_count')!r}"
        )
    max_matching = expected.get("max_matching_memory_count")
    if max_matching is not None and int(outputs.get("matching_memory_count") or 0) > int(max_matching):
        failures.append(
            "matching_memory_count: "
            f"expected <= {max_matching}, got {outputs.get('matching_memory_count')!r}"
        )
    max_duplicates = expected.get("max_duplicate_memory_count")
    if max_duplicates is not None and int(outputs.get("duplicate_memory_count") or 0) > int(max_duplicates):
        failures.append(
            "duplicate_memory_count: "
            f"expected <= {max_duplicates}, got {outputs.get('duplicate_memory_count')!r}"
        )

    expected_types = {str(item) for item in expected.get("expected_memory_types_any", []) if str(item)}
    if expected_types:
        actual_types = {str(item) for item in outputs.get("long_term_memory_types") or [] if str(item)}
        if not (expected_types & actual_types):
            failures.append(f"long_term_memory_types: expected any {sorted(expected_types)}, got {sorted(actual_types)}")

    other_max_hits = expected.get("other_user_max_long_term_memory_hits")
    if other_max_hits is not None and int(outputs.get("other_user_long_term_memory_hits") or 0) > int(other_max_hits):
        failures.append(
            "other_user_long_term_memory_hits: "
            f"expected <= {other_max_hits}, got {outputs.get('other_user_long_term_memory_hits')!r}"
        )
    other_content = str(outputs.get("other_user_content") or "")
    other_forbidden = [str(item) for item in expected.get("other_user_forbidden_keywords", []) if str(item)]
    other_leaks = [item for item in other_forbidden if item in other_content]
    if other_leaks:
        failures.append(f"forbidden keywords in other user content: {other_leaks}")

    if outputs.get("guardrail_pass") is not True:
        failures.append(f"guardrail_pass: expected True, got {outputs.get('guardrail_pass')!r}")

    return not failures, "; ".join(failures) if failures else "ok"


def local_eval(
    ctx: EvalContext,
    examples: list[dict[str, Any]],
    *,
    verbose: bool,
    metrics_output: str = "",
    fail_on_mismatch: bool = False,
) -> int:
    failed = 0
    rows: list[dict[str, Any]] = []
    for index, example in enumerate(examples, start=1):
        inputs = example["inputs"]
        expected = example["outputs"]
        print(f"\n[{index}/{len(examples)}] {inputs.get('case_type')} :: {case_label(inputs)}")
        try:
            outputs = run_case(ctx, inputs)
            ok, comment = compare_output(outputs, expected)
        except Exception as exc:
            ok = False
            comment = str(exc)
            outputs = {"route_label": "error", "error": str(exc)}

        row = build_metric_row(inputs, expected, outputs, ok, comment)
        rows.append(row)
        print_case_result(row, outputs, verbose=verbose)
        if not ok:
            failed += 1

    metrics = compute_classification_metrics(rows)
    print_metrics(metrics)
    write_metrics_output(metrics_output, rows, metrics)
    return 1 if failed and fail_on_mismatch else 0


def langsmith_eval(
    ctx: EvalContext,
    examples: list[dict[str, Any]],
    dataset_name: str,
    create_dataset: bool,
    *,
    metrics_output: str = "",
    fail_on_mismatch: bool = False,
) -> int:
    try:
        from langsmith import Client, evaluate
    except ImportError as exc:
        raise RuntimeError("Install langsmith first: python -m pip install langsmith") from exc

    client = Client()
    data: str | list[dict[str, Any]] = examples
    if create_dataset:
        sync_dataset(client, dataset_name, examples)
        data = dataset_name

    rows: list[dict[str, Any]] = []

    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        try:
            return run_case(ctx, inputs)
        except Exception as exc:
            return {
                "case_id": inputs.get("case_id"),
                "route_label": "error",
                "error": str(exc),
                "guardrail_pass": False,
                "content": "",
            }

    def expected_contract(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
        ok, comment = compare_output(outputs, reference_outputs)
        rows.append(build_metric_row({}, reference_outputs, outputs, ok, comment))
        return {"key": "expected_contract", "score": int(ok), "comment": comment}

    def route_summary(outputs: list[dict[str, Any]], reference_outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summary_rows = []
        for output, expected in zip(outputs, reference_outputs):
            output = output or {}
            ok, comment = compare_output(output, expected)
            summary_rows.append(build_metric_row({}, expected, output, ok, comment))
        metrics = compute_classification_metrics(summary_rows)
        return langsmith_summary_results(metrics)

    results = evaluate(
        target,
        data=data,
        evaluators=[expected_contract],
        summary_evaluators=[route_summary],
        experiment_prefix="liveagent-router-memory",
        metadata={"suite": "router_memory", "base_url": ctx.base_url, "dataset_name": dataset_name},
        max_concurrency=1,
        client=client,
    )
    if hasattr(results, "wait"):
        results.wait()

    metrics = compute_classification_metrics(rows)
    print(f"\nLangSmith experiment: {getattr(results, 'experiment_name', '(created)')}")
    print_metrics(metrics)
    write_metrics_output(metrics_output, rows, metrics)
    return 1 if metrics["accuracy"] < 1.0 and fail_on_mismatch else 0


def sync_dataset_only(dataset_name: str, examples: list[dict[str, Any]]) -> None:
    try:
        from langsmith import Client
    except ImportError as exc:
        raise RuntimeError("Install langsmith first: python -m pip install langsmith") from exc
    sync_dataset(Client(), dataset_name, examples)


def sync_dataset(client: Any, dataset_name: str, examples: list[dict[str, Any]]) -> None:
    try:
        dataset = client.read_dataset(dataset_name=dataset_name)
        existing = list(client.list_examples(dataset_id=dataset.id))
        existing_by_case_id = {str(item.inputs.get("case_id") or ""): item for item in existing}
        print(f"LangSmith dataset exists: {dataset_name} ({len(existing)} examples)")
    except Exception:
        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description=(
                "LiveAgentStudio router, short-term memory, and long-term Mem0 memory "
                "regression cases with classification and contract metrics."
            ),
        )
        existing_by_case_id = {}
        print(f"Created LangSmith dataset: {dataset_name}")

    created = 0
    updated = 0
    for example in examples:
        case_id = str(example["inputs"].get("case_id") or "").strip()
        existing = existing_by_case_id.get(case_id)
        if existing is None:
            client.create_example(
                dataset_id=dataset.id,
                inputs=example["inputs"],
                outputs=example["outputs"],
            )
            created += 1
        else:
            client.update_example(
                example_id=existing.id,
                inputs=example["inputs"],
                outputs=example["outputs"],
            )
            updated += 1
    print(f"Synced LangSmith dataset: created={created} updated={updated} total={len(examples)}")


def build_metric_row(
    inputs: dict[str, Any],
    expected: dict[str, Any],
    outputs: dict[str, Any],
    ok: bool,
    comment: str,
) -> dict[str, Any]:
    if expected.get("memory_label"):
        expected_label = str(expected.get("memory_label"))
        predicted_label = expected_label if ok else "memory_failure"
        metric_type = "long_memory"
    else:
        expected_label = str(expected.get("route_label") or "error")
        predicted_label = str(outputs.get("route_label") or "error")
        tool_labels = {"datetime", "memory_recall", "web_search"}
        metric_type = "tool" if expected_label in tool_labels or predicted_label in tool_labels else "route"
    return {
        "case_id": str(inputs.get("case_id") or outputs.get("case_id") or ""),
        "metric_type": metric_type,
        "expected": expected_label,
        "predicted": predicted_label,
        "ok": expected_label == predicted_label and bool(ok),
        "contract_ok": bool(ok),
        "comment": comment,
        "trace_id": outputs.get("trace_id"),
        "session_id": outputs.get("session_id"),
        "content_preview": preview(outputs.get("other_user_content") or outputs.get("content")),
        "raw": {
            **{key: outputs.get(key) for key in ROUTE_METRIC_KEYS if key in outputs},
            **{
                key: outputs.get(key)
                for key in (
                    "long_term_memory_hits",
                    "long_term_memory_types",
                    "insights_enabled",
                    "total_memories_delta",
                    "matching_memory_count",
                    "duplicate_memory_count",
                    "other_user_long_term_memory_hits",
                    "marker",
                )
                if key in outputs
            },
            **{
                key: outputs.get(key)
                for key in (
                    "error",
                    "primary_username",
                    "primary_user_id",
                    "other_username",
                    "other_user_id",
                )
                if key in outputs
            },
        },
    }


def compute_classification_metrics(rows: list[dict[str, Any]], *, include_breakdowns: bool = True) -> dict[str, Any]:
    labels = ordered_labels(rows)
    matrix = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    for row in rows:
        actual = str(row.get("expected") or "error")
        predicted = str(row.get("predicted") or "error")
        if actual not in matrix:
            matrix[actual] = {label: 0 for label in labels}
            labels.append(actual)
            for values in matrix.values():
                values.setdefault(actual, 0)
        if predicted not in matrix:
            for values in matrix.values():
                values[predicted] = 0
            matrix[predicted] = {label: 0 for label in [*labels, predicted]}
            labels.append(predicted)
        matrix[actual][predicted] += 1

    total = len(rows)
    correct = sum(1 for row in rows if row.get("expected") == row.get("predicted"))
    contract_correct = sum(1 for row in rows if row.get("contract_ok") is True)
    per_class: dict[str, dict[str, Any]] = {}
    for label in labels:
        tp = matrix.get(label, {}).get(label, 0)
        fp = sum(matrix.get(actual, {}).get(label, 0) for actual in labels if actual != label)
        fn = sum(count for predicted, count in matrix.get(label, {}).items() if predicted != label)
        support = sum(matrix.get(label, {}).values())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }

    non_empty = [item for item in per_class.values() if item["support"] > 0]
    macro_f1 = sum(item["f1"] for item in non_empty) / len(non_empty) if non_empty else 0.0
    weighted_f1 = (
        sum(item["f1"] * item["support"] for item in non_empty) / sum(item["support"] for item in non_empty)
        if non_empty
        else 0.0
    )
    metrics = {
        "total": total,
        "correct": correct,
        "contract_correct": contract_correct,
        "accuracy": correct / total if total else 0.0,
        "contract_pass_rate": contract_correct / total if total else 0.0,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "labels": labels,
        "per_class": per_class,
        "confusion_matrix": matrix,
        "rows": rows,
    }
    if include_breakdowns:
        by_metric_type: dict[str, dict[str, Any]] = {}
        metric_types = sorted({str(row.get("metric_type") or "route") for row in rows})
        for metric_type in metric_types:
            group_rows = [row for row in rows if str(row.get("metric_type") or "route") == metric_type]
            group_metrics = compute_classification_metrics(group_rows, include_breakdowns=False)
            group_metrics.pop("rows", None)
            by_metric_type[metric_type] = group_metrics
        metrics["by_metric_type"] = by_metric_type
    return metrics


def ordered_labels(rows: list[dict[str, Any]]) -> list[str]:
    present = {
        str(row.get("expected") or "error")
        for row in rows
    } | {
        str(row.get("predicted") or "error")
        for row in rows
    }
    return [label for label in CLASS_ORDER if label in present] + sorted(present - set(CLASS_ORDER))


def langsmith_summary_results(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    results = [
        {"key": "route_accuracy", "score": metrics["accuracy"], "comment": f"n={metrics['total']}"},
        {"key": "contract_pass_rate", "score": metrics["contract_pass_rate"], "comment": f"n={metrics['total']}"},
        {"key": "route_macro_f1", "score": metrics["macro_f1"]},
        {"key": "route_weighted_f1", "score": metrics["weighted_f1"]},
        {
            "key": "route_confusion_matrix",
            "value": json.dumps(metrics["confusion_matrix"], ensure_ascii=False, sort_keys=True),
        },
    ]
    for label in metrics["labels"]:
        item = metrics["per_class"][label]
        results.extend(
            [
                {"key": f"precision_{label}", "score": item["precision"], "comment": f"support={item['support']}"},
                {"key": f"recall_{label}", "score": item["recall"], "comment": f"support={item['support']}"},
                {"key": f"f1_{label}", "score": item["f1"], "comment": f"support={item['support']}"},
            ]
        )
    for metric_type, group in (metrics.get("by_metric_type") or {}).items():
        results.extend(
            [
                {
                    "key": f"{metric_type}_accuracy",
                    "score": group["accuracy"],
                    "comment": f"n={group['total']}",
                },
                {
                    "key": f"{metric_type}_contract_pass_rate",
                    "score": group["contract_pass_rate"],
                    "comment": f"n={group['total']}",
                },
                {"key": f"{metric_type}_macro_f1", "score": group["macro_f1"]},
            ]
        )
    return results


def print_case_result(row: dict[str, Any], outputs: dict[str, Any], *, verbose: bool) -> None:
    if verbose:
        print(json.dumps({k: v for k, v in outputs.items() if k != "metadata"}, ensure_ascii=False, indent=2))
    else:
        print(
            json.dumps(
                {
                    "case_id": row["case_id"],
                    "expected": row["expected"],
                    "predicted": row["predicted"],
                    "contract_ok": row["contract_ok"],
                    "trace_id": row.get("trace_id"),
                    "content_preview": row.get("content_preview"),
                },
                ensure_ascii=False,
            )
        )
    print(f"RESULT: {'PASS' if row['contract_ok'] else 'FAIL'} - {row['comment']}")


def print_metrics(metrics: dict[str, Any]) -> None:
    print("\n=== Classification Metrics ===")
    print(f"Total: {metrics['total']}")
    print(f"Correct: {metrics['correct']}")
    print(f"Accuracy: {metrics['accuracy']:.4f}")
    print(f"Contract Pass Rate: {metrics['contract_pass_rate']:.4f}")
    print(f"Macro F1: {metrics['macro_f1']:.4f}")
    print(f"Weighted F1: {metrics['weighted_f1']:.4f}")
    print("\nPer-class:")
    print("class\tprecision\trecall\tf1\tsupport")
    for label in metrics["labels"]:
        item = metrics["per_class"][label]
        print(
            f"{label}\t{item['precision']:.4f}\t{item['recall']:.4f}\t"
            f"{item['f1']:.4f}\t{item['support']}"
        )
    print("\nConfusion Matrix (rows=actual, columns=predicted):")
    labels = metrics["labels"]
    print("\t" + "\t".join(labels))
    for actual in labels:
        print(actual + "\t" + "\t".join(str(metrics["confusion_matrix"][actual].get(predicted, 0)) for predicted in labels))
    if metrics.get("by_metric_type"):
        print("\nBy metric type:")
        print("type\ttotal\taccuracy\tcontract_pass_rate\tmacro_f1")
        for metric_type, group in metrics["by_metric_type"].items():
            print(
                f"{metric_type}\t{group['total']}\t{group['accuracy']:.4f}\t"
                f"{group['contract_pass_rate']:.4f}\t{group['macro_f1']:.4f}"
            )


def write_metrics_output(path: str, rows: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    if target.is_dir():
        target = target / f"router_memory_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {**metrics, "rows": rows}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nMetrics written to: {target}")


def case_label(inputs: dict[str, Any]) -> str:
    if inputs.get("case_type") == "memory":
        steps = inputs.get("steps") or []
        return " -> ".join(str(step.get("user_input", ""))[:30] for step in steps)
    if inputs.get("case_type") == "long_memory":
        write_steps = inputs.get("write_steps") or []
        recall_steps = inputs.get("recall_steps") or inputs.get("other_user_recall_steps") or []
        parts = [*(str(step.get("user_input", ""))[:26] for step in write_steps[:1])]
        parts.extend(str(step.get("user_input", ""))[:26] for step in recall_steps[:1])
        return " -> ".join(parts)
    return str(inputs.get("user_input", ""))[:60]


def preview(value: Any, limit: int = 80) -> str:
    text = str(value or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def main() -> int:
    args = parse_args()
    session_prefix = args.session_prefix or f"ls-eval-{uuid.uuid4().hex[:8]}"
    examples = build_examples(args.mode, include_web_search=args.include_web_search, dataset_size=args.dataset_size)
    counts = Counter(
        str(example["outputs"].get("memory_label") or example["outputs"].get("route_label") or "error")
        for example in examples
    )
    print(f"Examples: {len(examples)} classes={dict(counts)}")
    if args.include_web_search and not os.getenv("SERPAPI_API_KEY"):
        print("SERPAPI_API_KEY is not set; web-search cases were filtered out.")
    if args.mode == "all" and not long_memory_env_configured():
        print("QA_MEMORY_ENABLED=true and MEM0_API_KEY are required; long-memory cases were filtered out.")
    if args.mode == "long_memory" and not long_memory_env_configured():
        print("QA_MEMORY_ENABLED=true and MEM0_API_KEY are required; long-memory cases are expected to fail.")

    try:
        if args.sync_dataset_only:
            sync_dataset_only(args.dataset_name, examples)
            return 0

        check_health(args.base_url, args.health_timeout)
        token = login(args.base_url, args.username, args.password, args.role, args.login_timeout)
        current_user = fetch_current_user(args.base_url.rstrip("/"), token, args.login_timeout)
        ctx = EvalContext(
            base_url=args.base_url.rstrip("/"),
            token=token,
            chat_timeout=args.chat_timeout,
            session_prefix=session_prefix,
            username=args.username,
            user_id=str(current_user.get("id") or ""),
            password=args.password,
            role=args.role,
            login_timeout=args.login_timeout,
        )
        if args.langsmith or args.create_dataset:
            return langsmith_eval(
                ctx,
                examples,
                args.dataset_name,
                args.create_dataset,
                metrics_output=args.metrics_output,
                fail_on_mismatch=args.fail_on_mismatch,
            )
        return local_eval(
            ctx,
            examples,
            verbose=args.verbose,
            metrics_output=args.metrics_output,
            fail_on_mismatch=args.fail_on_mismatch,
        )
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
