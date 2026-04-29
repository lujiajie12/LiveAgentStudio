from __future__ import annotations

import pytest

from app.memory.memory_policy import MemoryPolicy
from app.memory.memory_service import InMemoryMem0Backend, LongTermMemoryService
from app.memory.qa_agent_memory_hook import QAMemoryHook


@pytest.mark.asyncio
async def test_memory_policy_masks_sensitive_fields() -> None:
    policy = MemoryPolicy()
    decision = policy.build_write_decision(
        user_input="我的手机号是13812345678，订单号 ABCD123456，收货地址 北京市朝阳区xx路88号",
        assistant_output="好的，我已记录手机号13812345678和订单号ABCD123456。",
        current_product_id="SKU-001",
        metadata={"route_target": "qa"},
    )

    assert decision.should_store is True
    joined = " ".join(item["content"] for item in decision.messages)
    assert "[PHONE]" in joined
    assert "[ORDER_ID]" in joined
    assert "[ADDRESS]" in joined


@pytest.mark.asyncio
async def test_memory_policy_skips_noise_and_greetings() -> None:
    policy = MemoryPolicy()
    assert policy.build_write_decision(
        user_input="1111",
        assistant_output="请补充更明确的问题。",
        current_product_id=None,
        metadata={},
    ).should_store is False
    assert policy.build_write_decision(
        user_input="你好",
        assistant_output="你好，请问有什么可以帮你？",
        current_product_id=None,
        metadata={},
    ).should_store is False


@pytest.mark.asyncio
async def test_memory_policy_skips_memory_recall_meta_queries() -> None:
    policy = MemoryPolicy()
    decision = policy.build_write_decision(
        user_input="我刚刚问过的几个问题是什么？",
        assistant_output="你刚刚问过的 3 个问题是：1. ... 2. ... 3. ...",
        current_product_id=None,
        metadata={"tool_intent": "memory_recall"},
    )

    assert decision.should_store is False


@pytest.mark.asyncio
async def test_long_term_memory_service_add_and_search_scope() -> None:
    service = LongTermMemoryService(
        backend=InMemoryMem0Backend(),
        enabled=True,
        similarity_threshold=0.1,
    )
    await service.add_memory(
        messages=[{"role": "user", "content": "用户经常问运费谁出"}],
        user_id="user-1",
        agent_id="qa_agent",
        app_id="liveagent-studio",
        run_id="run-1",
        metadata={"memory_types": ["faq"]},
    )
    await service.add_memory(
        messages=[{"role": "user", "content": "另一个用户问价格"}],
        user_id="user-2",
        agent_id="qa_agent",
        app_id="liveagent-studio",
        run_id="run-2",
        metadata={"memory_types": ["faq"]},
    )

    records = await service.search_memory(
        query="运费谁出",
        user_id="user-1",
        agent_id="qa_agent",
        app_id="liveagent-studio",
        top_k=3,
        threshold=0.1,
    )
    assert len(records) == 1
    assert records[0].metadata["scope_user_id"] == "user-1"


@pytest.mark.asyncio
async def test_long_term_memory_service_delete_by_filters() -> None:
    service = LongTermMemoryService(
        backend=InMemoryMem0Backend(),
        enabled=True,
        similarity_threshold=0.1,
    )
    await service.add_memory(
        messages=[{"role": "user", "content": "管理员偏好简洁回答"}],
        user_id="user-1",
        agent_id="qa_agent",
        app_id="liveagent-studio",
        run_id="run-1",
        metadata={"memory_types": ["operator_preference"]},
    )
    deleted = await service.delete_memories(
        {"user_id": "user-1", "agent_id": "qa_agent", "app_id": "liveagent-studio"}
    )
    assert deleted == 1


@pytest.mark.asyncio
async def test_qa_memory_hook_builds_prompt_context() -> None:
    service = LongTermMemoryService(
        backend=InMemoryMem0Backend(),
        enabled=True,
        similarity_threshold=0.1,
    )
    hook = QAMemoryHook(
        memory_service=service,
        policy=MemoryPolicy(),
        agent_id="qa_agent",
        app_id="liveagent-studio",
        top_k=3,
        threshold=0.1,
    )
    await service.add_memory(
        messages=[{"role": "user", "content": "这个管理员经常问发货时效"}],
        user_id="user-1",
        agent_id="qa_agent",
        app_id="liveagent-studio",
        run_id="run-1",
        metadata={"memory_summary": "常问发货时效", "memory_types": ["faq"]},
    )

    state = {
        "user_id": "user-1",
        "user_input": "现在下单多久发货",
        "app_id": "liveagent-studio",
    }
    memories = await hook.search_for_state(state)
    context = hook.build_prompt_context(memories)
    assert memories
    assert "Relevant long-term QA memories" in context
    assert "常问发货时效" in context
