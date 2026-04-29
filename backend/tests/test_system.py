def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}


def test_system_health(client, auth_headers):
    response = client.get("/api/v1/system/health", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] in {"ok", "degraded"}
    assert "postgres" in payload["services"]


def test_system_metrics(client, auth_headers):
    response = client.get("/api/v1/system/metrics", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "ok"
    assert "metrics" in payload


def test_trace_id_header_is_injected(client):
    response = client.get("/health")
    assert "x-trace-id" in response.headers
