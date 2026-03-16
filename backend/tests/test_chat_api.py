def test_chat_stream_returns_sse_events(client, auth_headers):
    response = client.post(
        "/api/v1/chat/stream",
        headers=auth_headers,
        json={
            "session_id": "session-test",
            "user_input": "帮我写一段促单话术",
            "current_product_id": "SKU-1",
            "live_stage": "pitch",
        },
    )

    assert response.status_code == 200
    assert "event: meta" in response.text
    assert "event: token" in response.text
    assert "event: final" in response.text


def test_get_session_messages(client, auth_headers):
    client.post(
        "/api/v1/chat/stream",
        headers=auth_headers,
        json={
            "session_id": "session-history",
            "user_input": "这个产品适合敏感肌吗",
            "current_product_id": "SKU-1",
            "live_stage": "intro",
        },
    )
    response = client.get("/api/v1/sessions/session-history/messages", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()["data"]) >= 2
