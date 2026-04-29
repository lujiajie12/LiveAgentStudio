import asyncio

from app.schemas.domain import MessageRecord, MessageRole, ReportRecord, SessionRecord, ToolCallLogRecord


def test_memory_reports_settings_and_ops_endpoints(client, auth_headers):
    container = client.app.state.container
    session_id = "ops-session"
    trace_id = "trace-management-001"

    asyncio.run(container.session_repository.save(SessionRecord(id=session_id, user_id="seed-user")))
    asyncio.run(
        container.message_repository.create(
            MessageRecord(
                session_id=session_id,
                role=MessageRole.user,
                content="今天这场直播主推什么？",
            )
        )
    )
    asyncio.run(
        container.message_repository.create(
            MessageRecord(
                session_id=session_id,
                role=MessageRole.assistant,
                content="今天主推青岚超净蒸汽拖洗一体机，当前重点在讲解适用家庭场景。",
                intent="qa",
                agent_name="qa",
                metadata={
                    "agent_name": "qa",
                    "references": ["doc-1", "doc-2"],
                    "unresolved": False,
                    "guardrail_pass": True,
                    "guardrail_action": "pass",
                    "guardrail_violations": [],
                },
            )
        )
    )
    asyncio.run(
        container.message_repository.create(
            MessageRecord(
                session_id=session_id,
                role=MessageRole.assistant,
                content="库存紧张，可适当加强优惠节奏和限时提醒。",
                intent="script",
                agent_name="script",
                metadata={
                    "agent_name": "script",
                    "script_reason": "根据库存与优惠节奏生成促单建议。",
                    "references": ["doc-3"],
                    "guardrail_pass": True,
                    "guardrail_action": "pass",
                    "guardrail_violations": [],
                },
            )
        )
    )
    asyncio.run(container.memory_service.refresh_short_term_memory(session_id, "SKU-1", "pitch", ["库存", "优惠"]))
    asyncio.run(container.high_frequency_repository.upsert_many("SKU-1", ["今天这场直播主推什么？"], session_id))
    asyncio.run(
        container.report_repository.create(
            ReportRecord(
                session_id=session_id,
                summary="本场直播的高频问题集中在商品讲解和优惠节奏。",
                total_messages=3,
                intent_distribution={"qa": 0.67, "script": 0.33},
                top_questions=["今天这场直播主推什么？"],
                unresolved_questions=[],
                hot_products=["SKU-1"],
                script_usage=[{"script_type": "promotion", "count": 1}],
                suggestions=["继续强化商品卖点和促单节奏。"],
            )
        )
    )
    asyncio.run(
        container.tool_log_repository.create(
            ToolCallLogRecord(
                session_id=session_id,
                trace_id=trace_id,
                tool_name="router_enter",
                node_name="router",
                category="graph",
                status="ok",
            )
        )
    )

    memory_response = client.get(f"/api/v1/sessions/{session_id}/memory", headers=auth_headers)
    assert memory_response.status_code == 200
    assert memory_response.json()["data"]["turns"]

    hfq_response = client.get(
        "/api/v1/memory/high-frequency-questions",
        params={"product_id": "SKU-1"},
        headers=auth_headers,
    )
    assert hfq_response.status_code == 200
    assert hfq_response.json()["data"][0]["product_id"] == "SKU-1"

    reports_response = client.get("/api/v1/reports", headers=auth_headers)
    assert reports_response.status_code == 200
    assert reports_response.json()["data"]

    save_settings = client.put(
        "/api/v1/settings/agent-preferences",
        json={"script_style": "promotional", "custom_sensitive_terms": ["保过", "包治百病"]},
        headers=auth_headers,
    )
    assert save_settings.status_code == 200
    get_settings = client.get("/api/v1/settings/agent-preferences", headers=auth_headers)
    assert get_settings.status_code == 200
    assert get_settings.json()["data"]["script_style"] == "promotional"

    traces_response = client.get("/api/v1/ops/traces", headers=auth_headers)
    assert traces_response.status_code == 200
    assert any(item["trace_id"] == trace_id for item in traces_response.json()["data"])

    trace_detail = client.get(f"/api/v1/ops/traces/{trace_id}", headers=auth_headers)
    assert trace_detail.status_code == 200
    assert trace_detail.json()["data"]["trace_id"] == trace_id

    priority_queue = client.get(
        "/api/v1/ops/priority-queue",
        params={"session_id": session_id},
        headers=auth_headers,
    )
    assert priority_queue.status_code == 200
    assert priority_queue.json()["data"]
    assert priority_queue.json()["data"][0]["prompt"].startswith("请帮我处理这个直播间问题：")

    action_center = client.get(
        "/api/v1/ops/action-center",
        params={"session_id": session_id},
        headers=auth_headers,
    )
    assert action_center.status_code == 200
    cards = action_center.json()["data"]["cards"]
    assert [card["key"] for card in cards] == ["qa", "guardrail", "ops"]
    assert cards[0]["title"] == "RAG 知识 Agent"

    tts_response = client.post(
        "/api/v1/ops/tts/broadcast",
        json={"session_id": session_id, "text": "请播放这段话术", "voice": "xiaoyun"},
        headers=auth_headers,
    )
    assert tts_response.status_code == 200
    assert tts_response.json()["data"]["status"] == "accepted"


def test_rag_management_endpoints(client, auth_headers):
    container = client.app.state.container

    async def fake_online_debug(**kwargs):
        return {
            "query": kwargs["query"],
            "rewritten_query": kwargs["query"],
            "source_hint": kwargs.get("source_hint") or "mixed",
            "expanded_queries": {"original": [(kwargs["query"], 1.0)], "expansions": []},
            "bm25_results": [],
            "vector_results": [],
            "fused_results": [],
            "rerank_results": [],
            "context": "debug-context",
            "timings_ms": {"rewrite": 1, "expand": 1, "retrieve": 1, "fusion": 1, "rerank": 1},
            "degraded": {"bm25": True, "vector": True},
        }

    async def fake_overview():
        return {
            "docs_dir": "docs/data",
            "source_file_count": 2,
            "bm25_count": 10,
            "vector_count": 20,
            "recent_jobs": [],
        }

    async def fake_start_offline_job(**kwargs):
        return {
            "id": "job-001",
            "job_type": kwargs["job_type"],
            "status": "running",
            "docs_dir": kwargs["docs_dir"],
            "args": kwargs,
            "log_path": "backend/logs/job-001.log",
            "pid": 1234,
            "error_message": None,
            "created_at": "2026-03-24T00:00:00",
            "updated_at": "2026-03-24T00:00:00",
        }

    async def fake_job_detail(job_id):
        return {
            "id": job_id,
            "job_type": "incremental",
            "status": "completed",
            "docs_dir": "docs/data",
            "args": {},
            "log_path": "backend/logs/job-001.log",
            "pid": 1234,
            "error_message": None,
            "created_at": "2026-03-24T00:00:00",
            "updated_at": "2026-03-24T00:01:00",
            "log_tail": ["done"],
        }

    container.rag_ops_service.online_debug = fake_online_debug
    container.rag_ops_service.get_offline_overview = fake_overview
    container.rag_ops_service.start_offline_job = fake_start_offline_job
    container.rag_ops_service.get_job_detail = fake_job_detail

    debug_response = client.post(
        "/api/v1/rag/online/debug",
        json={"query": "青岚拖洗机的卖点是什么？", "current_product_id": "SKU-1", "live_stage": "pitch"},
        headers=auth_headers,
    )
    assert debug_response.status_code == 200
    assert debug_response.json()["data"]["context"] == "debug-context"

    overview_response = client.get("/api/v1/rag/offline/overview", headers=auth_headers)
    assert overview_response.status_code == 200
    assert overview_response.json()["data"]["vector_count"] == 20

    create_job_response = client.post(
        "/api/v1/rag/offline/jobs",
        json={"job_type": "incremental", "docs_dir": "docs/data"},
        headers=auth_headers,
    )
    assert create_job_response.status_code == 200
    assert create_job_response.json()["data"]["status"] == "running"

    job_detail_response = client.get("/api/v1/rag/offline/jobs/job-001", headers=auth_headers)
    assert job_detail_response.status_code == 200
    assert job_detail_response.json()["data"]["log_tail"] == ["done"]


def test_live_barrage_and_teleprompter_endpoints(client, auth_headers):
    token = auth_headers["Authorization"].split(" ", 1)[1]
    session_id = "studio-live-room-001"

    update_response = client.post(
        "/api/v1/live/overview/update",
        json={
            "session_id": session_id,
            "current_product_id": "SKU-001",
            "live_stage": "intro",
            "online_viewers": 12001,
            "conversion_rate": 3.12,
            "interaction_rate": 6.5,
            "metadata": {"source": "test-suite"},
        },
        headers=auth_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["online_viewers"] == 12001

    first_ingest = client.post(
        "/api/v1/live/barrages/ingest",
        json={
            "session_id": session_id,
            "display_name": "User_101",
            "user_id": "user-101",
            "text": "今天这场直播主推什么？",
            "source": "simulator",
            "current_product_id": "SKU-001",
            "live_stage": "intro",
            "online_viewers": 12345,
            "conversion_rate": 3.24,
            "interaction_rate": 7.8,
        },
        headers=auth_headers,
    )
    assert first_ingest.status_code == 200
    assert first_ingest.json()["data"]["text"] == "今天这场直播主推什么？"

    overview_response = client.get(
        "/api/v1/live/overview",
        params={"session_id": session_id},
        headers=auth_headers,
    )
    assert overview_response.status_code == 200
    overview = overview_response.json()["data"]
    assert overview["current_product_id"] == "SKU-001"
    assert "agent_status_summary" in overview

    with client.websocket_connect(
        f"/api/v1/live/barrages/stream?session_id={session_id}&token={token}"
    ) as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["items"]

        stream_overview = websocket.receive_json()
        assert stream_overview["type"] == "overview"

        client.post(
            "/api/v1/live/barrages/ingest",
            json={
                "session_id": session_id,
                "display_name": "User_202",
                "user_id": "user-202",
                "text": "这款产品适合什么家庭使用？",
                "source": "simulator",
                "current_product_id": "SKU-001",
                "live_stage": "pitch",
                "online_viewers": 12520,
                "conversion_rate": 3.36,
                "interaction_rate": 8.1,
            },
            headers=auth_headers,
        )

        barrage_event = websocket.receive_json()
        assert barrage_event["type"] == "barrage"
        assert barrage_event["item"]["text"] == "这款产品适合什么家庭使用？"

        overview_event = websocket.receive_json()
        assert overview_event["type"] == "overview"

    priority_queue = client.get(
        "/api/v1/ops/priority-queue",
        params={"session_id": session_id},
        headers=auth_headers,
    )
    assert priority_queue.status_code == 200
    prompts = [item["prompt"] for item in priority_queue.json()["data"]]
    assert any("今天这场直播主推什么" in prompt or "适合什么家庭使用" in prompt for prompt in prompts)

    push_response = client.post(
        "/api/v1/teleprompter/push",
        json={
            "session_id": session_id,
            "title": "RAG 知识 Agent",
            "content": "今天主推青岚超净蒸汽拖洗一体机，重点讲适用家庭和清洁效率。",
            "source_agent": "qa",
            "priority": "normal",
        },
        headers=auth_headers,
    )
    assert push_response.status_code == 200
    pushed = push_response.json()["data"]
    assert pushed["content"].startswith("今天主推青岚超净蒸汽拖洗一体机")

    current_response = client.get(
        "/api/v1/teleprompter/current",
        params={"session_id": session_id},
        headers=auth_headers,
    )
    assert current_response.status_code == 200
    assert current_response.json()["data"]["title"] == "RAG 知识 Agent"

    with client.websocket_connect(
        f"/api/v1/teleprompter/stream?session_id={session_id}&token={token}"
    ) as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["item"]["title"] == "RAG 知识 Agent"

        client.post(
            "/api/v1/teleprompter/push",
            json={
                "session_id": session_id,
                "title": "运营控场编排",
                "content": "库存紧张，马上切促单节奏，提醒用户点购物袋下单。",
                "source_agent": "ops",
                "priority": "high",
            },
            headers=auth_headers,
        )

        teleprompter_event = websocket.receive_json()
        assert teleprompter_event["type"] == "teleprompter"
        assert teleprompter_event["item"]["source_agent"] == "ops"
