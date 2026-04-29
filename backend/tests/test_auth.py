def test_login_and_me(client):
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "demo",
            "role": "operator",
        },
    )
    assert login_response.status_code == 200
    token = login_response.json()["data"]["access_token"]

    me_response = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["data"]["username"] == "alice"


def test_me_requires_token(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
