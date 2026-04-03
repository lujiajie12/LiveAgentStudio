from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.dependencies import get_container, get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.common import ApiResponse

router = APIRouter(tags=["memory"])


@router.get("/sessions/{session_id}/memory", response_model=ApiResponse)
async def get_session_memory(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    snapshot = await container.memory_service.get_memory_snapshot(session_id)
    return ApiResponse(data=snapshot)


@router.get("/memory/high-frequency-questions", response_model=ApiResponse)
async def list_high_frequency_questions(
    product_id: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    records = await container.high_frequency_repository.list_by_product(product_id, limit=limit)
    return ApiResponse(data=[item.model_dump(mode="json") for item in records])


def _sort_memories(records):
    return sorted(
        records,
        key=lambda item: (
            item.updated_at or item.created_at or "",
            item.memory_id,
        ),
        reverse=True,
    )


def _extract_question_preview(record) -> str:
    summary = str(record.metadata.get("memory_summary") or record.memory or "").strip()
    if "recent_question:" in summary:
        preview = summary.split("recent_question:", 1)[1].split("|", 1)[0].strip()
        if preview:
            return preview
    return summary[:120]


@router.get("/memory/qa/insights", response_model=ApiResponse)
async def get_qa_memory_insights(
    user_id: str | None = Query(None),
    limit: int = Query(120, ge=10, le=500),
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    service = getattr(container, "qa_long_term_memory_service", None)
    if service is None or not service.enabled:
        return ApiResponse(
            data={
                "enabled": False,
                "scope": {
                    "user_id": user_id or "",
                    "agent_id": settings.QA_MEMORY_AGENT_ID,
                    "app_id": settings.QA_MEMORY_APP_ID,
                },
                "overview": {
                    "total_memories": 0,
                    "operator_preferences": 0,
                    "product_fact_groups": 0,
                    "faq_hotspots": 0,
                },
                "operator_preferences": [],
                "product_facts": [],
                "faq_hotspots": [],
                "recent_memories": [],
            }
        )

    filters = {
        "user_id": user_id,
        "agent_id": settings.QA_MEMORY_AGENT_ID,
        "app_id": settings.QA_MEMORY_APP_ID,
    }
    records = _sort_memories(await service.get_memories(filters))[:limit]

    operator_preferences = []
    product_fact_groups: dict[tuple[str, str], dict] = {}
    faq_hotspots_map: dict[str, dict] = {}
    recent_memories = []

    for record in records:
        metadata = record.metadata
        memory_types = set(metadata.get("memory_types") or [])
        preview = _extract_question_preview(record)
        current_product_id = str(metadata.get("current_product_id") or "").strip()
        item = {
            "memory_id": record.memory_id,
            "summary": str(metadata.get("memory_summary") or record.memory).strip(),
            "question_preview": preview,
            "memory_types": list(memory_types),
            "current_product_id": current_product_id,
            "updated_at": record.updated_at or record.created_at,
            "score": record.score,
        }
        recent_memories.append(item)

        if {"operator_preference", "preference_signal"} & memory_types:
            operator_preferences.append(item)

        if "product_fact" in memory_types:
            group_key = (current_product_id or "unknown", preview or item["summary"])
            bucket = product_fact_groups.setdefault(
                group_key,
                {
                    "product_id": current_product_id or "unknown",
                    "topic": preview or item["summary"],
                    "count": 0,
                    "last_seen": item["updated_at"],
                    "items": [],
                },
            )
            bucket["count"] += 1
            bucket["items"].append(item)
            if item["updated_at"] and (bucket["last_seen"] or "") < item["updated_at"]:
                bucket["last_seen"] = item["updated_at"]

        if "faq" in memory_types:
            faq_key = preview or item["summary"]
            bucket = faq_hotspots_map.setdefault(
                faq_key,
                {
                    "question": faq_key,
                    "count": 0,
                    "last_seen": item["updated_at"],
                    "products": set(),
                },
            )
            bucket["count"] += 1
            if current_product_id:
                bucket["products"].add(current_product_id)
            if item["updated_at"] and (bucket["last_seen"] or "") < item["updated_at"]:
                bucket["last_seen"] = item["updated_at"]

    product_facts = sorted(product_fact_groups.values(), key=lambda item: (item["count"], item["last_seen"] or ""), reverse=True)
    faq_hotspots = sorted(faq_hotspots_map.values(), key=lambda item: (item["count"], item["last_seen"] or ""), reverse=True)
    for item in faq_hotspots:
        item["products"] = sorted(item["products"])

    return ApiResponse(
        data={
            "enabled": True,
            "scope": {
                "user_id": user_id or "",
                "agent_id": settings.QA_MEMORY_AGENT_ID,
                "app_id": settings.QA_MEMORY_APP_ID,
            },
            "overview": {
                "total_memories": len(records),
                "operator_preferences": len(operator_preferences),
                "product_fact_groups": len(product_facts),
                "faq_hotspots": len(faq_hotspots),
            },
            "operator_preferences": operator_preferences[:12],
            "product_facts": product_facts[:12],
            "faq_hotspots": faq_hotspots[:12],
            "recent_memories": recent_memories[:20],
        }
    )
