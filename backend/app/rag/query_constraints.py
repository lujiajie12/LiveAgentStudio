from __future__ import annotations

import re
from typing import Any


VALID_BUDGET_MODES = {"around", "range", "ceiling", "floor"}
CURRENCY_UNIT_FRAGMENT = r"(?:元|元钱|块钱|块|人民币|rmb|RMB|￥|¥)"
AROUND_SUFFIX_FRAGMENT = r"(?:左右|上下|前后|附近)"
CEILING_SUFFIX_FRAGMENT = r"(?:以内|以下|不超过|别超过|不能超过|不到|封顶)"
FLOOR_SUFFIX_FRAGMENT = r"(?:以上|起步|起)"
RANGE_CONNECTOR_FRAGMENT = r"(?:-|~|到|至)"
COLLOQUIAL_AROUND_PATTERN = re.compile(r"(?P<price>\d{2,5})(?:来块|来元|出头)")
BARE_AROUND_PATTERN = re.compile(r"(?P<price>\d{2,5})(?:左右|上下|前后)")
CURRENCY_VARIANT_PATTERN = re.compile(CURRENCY_UNIT_FRAGMENT)
WHITESPACE_PATTERN = re.compile(r"\s+")


PRICE_BAND_PATTERN = re.compile(
    r"直播价带[:：]\s*(?P<low>\d{2,5})(?:\s*[-~到至]\s*(?P<high>\d{2,5}))?\s*元(?P<suffix>起|左右|上下)?"
)
CATEGORY_PATTERN = re.compile(r"类目[:：]\s*(?P<category>[^｜|\n]+)")
AUDIENCE_PATTERN = re.compile(r"适配人群[:：]\s*(?P<audience>[^\n]+)")
PRODUCT_TYPE_PATTERN = re.compile(r"商品类型[:：]\s*(?P<product_type>[^\n]+)")
QUERY_PRICE_RANGE_PATTERN = re.compile(
    rf"(?P<low>\d{{2,5}})(?:\s*{CURRENCY_UNIT_FRAGMENT})?\s*{RANGE_CONNECTOR_FRAGMENT}\s*(?P<high>\d{{2,5}})(?:\s*{CURRENCY_UNIT_FRAGMENT})?"
)
QUERY_PRICE_AROUND_PATTERN = re.compile(
    rf"(?P<price>\d{{2,5}})(?:\s*{CURRENCY_UNIT_FRAGMENT})?{AROUND_SUFFIX_FRAGMENT}"
)
QUERY_PRICE_CEILING_PATTERN = re.compile(
    rf"(?P<price>\d{{2,5}})(?:\s*{CURRENCY_UNIT_FRAGMENT})?{CEILING_SUFFIX_FRAGMENT}"
)
QUERY_PRICE_FLOOR_PATTERN = re.compile(
    rf"(?P<price>\d{{2,5}})(?:\s*{CURRENCY_UNIT_FRAGMENT})?{FLOOR_SUFFIX_FRAGMENT}"
)
QUERY_GENERIC_PRICE_PATTERN = re.compile(rf"(?P<price>\d{{2,5}})(?:\s*{CURRENCY_UNIT_FRAGMENT})")
BUDGET_HINT_KEYWORDS = (
    "预算",
    "价位",
    "左右",
    "上下",
    "想买",
    "买个",
    "买一",
    "推荐",
    "求推荐",
    "找个",
    "找一款",
    "有没有",
    "控制在",
    "想要",
    "大概",
)


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _normalize_raw_query_text(query: str) -> str:
    text = WHITESPACE_PATTERN.sub("", str(query or ""))
    if not text:
        return ""
    # 统一口语化货币表达，保证“80块钱”“80块”“80元”都能落到同一预算语义上。
    text = re.sub(rf"(?P<price>\d{{2,5}})\s*{CURRENCY_UNIT_FRAGMENT}", r"\g<price>元", text)
    text = COLLOQUIAL_AROUND_PATTERN.sub(lambda match: f"{match.group('price')}元左右", text)
    text = BARE_AROUND_PATTERN.sub(lambda match: f"{match.group('price')}元左右", text)
    return text


def _build_budget_payload(
    *,
    mode: str,
    target: int | float | None,
    min_price: int | None,
    max_price: int | None,
    display: str | None = None,
) -> dict[str, Any] | None:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in VALID_BUDGET_MODES:
        return None

    if normalized_mode == "range":
        if min_price is None or max_price is None:
            return None
        low, high = sorted((int(min_price), int(max_price)))
        return {
            "mode": "range",
            "display": display or f"{low}-{high}元",
            "target": float(target if target is not None else (low + high) / 2),
            "min_price": low,
            "max_price": high,
        }

    numeric_target = _to_int(target)
    if numeric_target is None:
        numeric_target = _to_int(min_price if min_price is not None else max_price)
    if numeric_target is None:
        return None

    if normalized_mode == "around":
        tolerance = max(60, int(numeric_target * 0.25))
        return {
            "mode": "around",
            "display": display or f"{numeric_target}元左右",
            "target": numeric_target,
            "min_price": max(_to_int(min_price) if min_price is not None else numeric_target - tolerance, 0),
            "max_price": _to_int(max_price) if max_price is not None else numeric_target + tolerance,
        }
    if normalized_mode == "ceiling":
        ceiling = _to_int(max_price) if max_price is not None else numeric_target
        return {
            "mode": "ceiling",
            "display": display or f"{ceiling}元以内",
            "target": numeric_target,
            "min_price": max(_to_int(min_price) if min_price is not None else 0, 0),
            "max_price": ceiling,
        }
    if normalized_mode == "floor":
        floor = _to_int(min_price) if min_price is not None else numeric_target
        return {
            "mode": "floor",
            "display": display or f"{floor}元以上",
            "target": numeric_target,
            "min_price": floor,
            "max_price": _to_int(max_price),
        }
    return None


def normalize_budget_constraint(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    # 把 LLM 或上游链路给出的预算对象校正成统一结构，后续检索和回答都消费这一份标准对象。
    if not isinstance(payload, dict):
        return None
    mode = str(payload.get("mode") or "").strip().lower()
    return _build_budget_payload(
        mode=mode,
        target=payload.get("target"),
        min_price=_to_int(payload.get("min_price")),
        max_price=_to_int(payload.get("max_price")),
        display=str(payload.get("display") or "").strip() or None,
    )


def canonicalize_query_with_budget(query: str, budget: dict[str, Any] | None) -> str:
    # 统一把预算口语写法折叠成标准 query，避免“80块钱”和“80元左右”进入两条不同检索路径。
    normalized_query = _normalize_raw_query_text(query)
    normalized_budget = normalize_budget_constraint(budget)
    if normalized_budget is None:
        return normalized_query

    display = str(normalized_budget.get("display") or "").strip()
    if not display:
        return normalized_query

    if display in normalized_query:
        return normalized_query

    price = normalized_budget.get("target")
    if price is not None:
        normalized_query = re.sub(
            rf"{int(float(price))}(?:元(?:左右|上下|前后|以内|以下|以上)?|块钱(?:左右|上下|前后)?|块(?:左右|上下|前后)?|来块|来元|出头)",
            display,
            normalized_query,
            count=1,
        )
    return normalized_query


def extract_catalog_attributes(content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    # 把正文里的“类目 / 直播价带 / 商品类型 / 适配人群”抽成结构化字段，供索引与排序复用。
    text = str(content or "")
    base = dict(metadata or {})

    category = str(base.get("category", "") or "").strip()
    audience = str(base.get("audience", "") or "").strip()
    product_type = str(base.get("product_type", "") or "").strip()
    price_band_text = str(base.get("price_band_text", "") or "").strip()
    price_band_low = _to_int(base.get("price_band_low"))
    price_band_high = _to_int(base.get("price_band_high"))

    if not category:
        match = CATEGORY_PATTERN.search(text)
        if match:
            category = match.group("category").strip()
    if not audience:
        match = AUDIENCE_PATTERN.search(text)
        if match:
            audience = match.group("audience").strip()
    if not product_type:
        match = PRODUCT_TYPE_PATTERN.search(text)
        if match:
            product_type = match.group("product_type").strip()
    if not price_band_text or price_band_low is None:
        match = PRICE_BAND_PATTERN.search(text)
        if match:
            low = _to_int(match.group("low"))
            high = _to_int(match.group("high"))
            suffix = str(match.group("suffix") or "").strip()
            price_band_low = low
            price_band_high = high
            if high is not None:
                price_band_text = f"{low}-{high}元"
            elif suffix:
                price_band_text = f"{low}元{suffix}"
            elif low is not None:
                price_band_text = f"{low}元"

    if price_band_low is None and price_band_high is not None:
        price_band_low = price_band_high
    if price_band_high is None and price_band_low is not None:
        price_band_anchor = price_band_low
    elif price_band_low is not None and price_band_high is not None:
        price_band_anchor = (price_band_low + price_band_high) / 2
    else:
        price_band_anchor = None

    return {
        "category": category,
        "audience": audience,
        "product_type": product_type,
        "price_band_text": price_band_text,
        "price_band_low": price_band_low,
        "price_band_high": price_band_high,
        "price_band_anchor": price_band_anchor,
    }


def extract_query_budget(query: str, budget_hint: dict[str, Any] | None = None) -> dict[str, Any] | None:
    # 预算约束主路径优先吃上游 LLM 规范化结果；只有缺失时才退回正则兜底。
    normalized_hint = normalize_budget_constraint(budget_hint)
    if normalized_hint is not None:
        return normalized_hint

    normalized = _normalize_raw_query_text(query)
    if not normalized:
        return None

    range_match = QUERY_PRICE_RANGE_PATTERN.search(normalized)
    if range_match:
        low = _to_int(range_match.group("low"))
        high = _to_int(range_match.group("high"))
        if low is not None and high is not None:
            return _build_budget_payload(mode="range", target=(low + high) / 2, min_price=low, max_price=high)

    around_match = QUERY_PRICE_AROUND_PATTERN.search(normalized)
    if around_match:
        target = _to_int(around_match.group("price"))
        if target is not None:
            return _build_budget_payload(mode="around", target=target, min_price=None, max_price=None)

    ceiling_match = QUERY_PRICE_CEILING_PATTERN.search(normalized)
    if ceiling_match:
        ceiling = _to_int(ceiling_match.group("price"))
        if ceiling is not None:
            return _build_budget_payload(mode="ceiling", target=ceiling, min_price=0, max_price=ceiling)

    floor_match = QUERY_PRICE_FLOOR_PATTERN.search(normalized)
    if floor_match:
        floor = _to_int(floor_match.group("price"))
        if floor is not None:
            return _build_budget_payload(mode="floor", target=floor, min_price=floor, max_price=None)

    generic_match = QUERY_GENERIC_PRICE_PATTERN.search(normalized)
    if generic_match and any(keyword in normalized for keyword in BUDGET_HINT_KEYWORDS):
        target = _to_int(generic_match.group("price"))
        if target is not None:
            return _build_budget_payload(mode="around", target=target, min_price=None, max_price=None)

    return None


def price_constraint_bonus(
    query: str,
    metadata: dict[str, Any] | None = None,
    content: str = "",
    budget_hint: dict[str, Any] | None = None,
) -> float:
    # 预算属于强排序信号。用户给出预算时，检索排序必须显式利用，而不是指望生成阶段自己悟出来。
    budget = extract_query_budget(query, budget_hint=budget_hint)
    if budget is None:
        return 0.0

    attributes = extract_catalog_attributes(content, metadata)
    anchor = attributes.get("price_band_anchor")
    low = attributes.get("price_band_low")
    high = attributes.get("price_band_high")
    if anchor is None and low is None and high is None:
        return 0.0

    if anchor is None:
        anchor = low if low is not None else high
    if anchor is None:
        return 0.0

    mode = str(budget.get("mode") or "around")
    target = float(budget.get("target") or anchor)
    min_price = budget.get("min_price")
    max_price = budget.get("max_price")

    if mode == "around":
        tolerance = max(60.0, target * 0.25)
        distance = abs(float(anchor) - target)
        if distance <= tolerance:
            return 0.34 * (1.0 - distance / tolerance)
        return -min(0.18, 0.04 + ((distance - tolerance) / max(target, 1.0)) * 0.15)

    if mode == "range":
        if min_price is not None and max_price is not None and min_price <= float(anchor) <= max_price:
            width = max(float(max_price - min_price), 1.0)
            center = (float(min_price) + float(max_price)) / 2
            distance = abs(float(anchor) - center)
            return 0.30 * (1.0 - min(distance / (width / 2 + 1.0), 1.0))
        if min_price is not None and float(anchor) < min_price:
            return -min(0.16, 0.04 + ((float(min_price) - float(anchor)) / max(float(min_price), 1.0)) * 0.12)
        if max_price is not None and float(anchor) > max_price:
            return -min(0.16, 0.04 + ((float(anchor) - float(max_price)) / max(float(max_price), 1.0)) * 0.12)
        return 0.0

    if mode == "ceiling":
        if max_price is not None and float(anchor) <= max_price:
            tolerance = max(80.0, float(max_price) * 0.3)
            headroom = float(max_price) - float(anchor)
            return 0.24 + 0.10 * max(0.0, 1.0 - headroom / tolerance)
        if max_price is not None:
            overflow = float(anchor) - float(max_price)
            return -min(0.20, 0.06 + overflow / max(float(max_price), 1.0) * 0.18)
        return 0.0

    if mode == "floor":
        if min_price is not None and float(anchor) >= min_price:
            tolerance = max(80.0, float(min_price) * 0.3)
            overshoot = float(anchor) - float(min_price)
            return 0.18 + 0.08 * max(0.0, 1.0 - overshoot / tolerance)
        if min_price is not None:
            deficit = float(min_price) - float(anchor)
            return -min(0.20, 0.06 + deficit / max(float(min_price), 1.0) * 0.18)
        return 0.0

    return 0.0
