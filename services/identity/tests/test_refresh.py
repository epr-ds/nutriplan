def _register(client):
    return client.post(
        "/auth/register",
        json={"email": "bob@example.com", "password": "supersecret", "name": "Bob"},
    ).json()


def test_refresh_rotates_tokens(client):
    tokens = _register(client)
    response = client.post("/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert response.status_code == 200
    rotated = response.json()
    assert rotated["accessToken"]
    assert rotated["refreshToken"] != tokens["refreshToken"]


def test_refresh_reuse_revokes_whole_family(client):
    tokens = _register(client)
    original = tokens["refreshToken"]

    first = client.post("/auth/refresh", json={"refreshToken": original})
    assert first.status_code == 200
    rotated = first.json()["refreshToken"]

    # Replaying the already-rotated original token is detected as reuse.
    reuse = client.post("/auth/refresh", json={"refreshToken": original})
    assert reuse.status_code == 401

    # ...and the entire family (including the freshly rotated token) is revoked.
    after = client.post("/auth/refresh", json={"refreshToken": rotated})
    assert after.status_code == 401


def test_refresh_invalid_token_unauthorized(client):
    response = client.post("/auth/refresh", json={"refreshToken": "not-a-real-token"})
    assert response.status_code == 401
