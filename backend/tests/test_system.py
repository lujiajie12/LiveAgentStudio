def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_system_health(client):
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    assert response.json()["services"]["graph"] == "ok"


def test_trace_id_header_is_injected(client):
    response = client.get("/health")
    assert "x-trace-id" in response.headers
