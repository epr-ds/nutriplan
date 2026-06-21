import uuid


def _auth(client, email="avatar@example.com"):
    body = client.post(
        "/auth/register",
        json={"email": email, "password": "supersecret", "name": "Ava"},
    ).json()
    headers = {"Authorization": f"Bearer {body['accessToken']}"}
    return headers, body["user"]["id"]


def test_avatar_upload_url_returns_presigned_put(client):
    headers, user_id = _auth(client)
    resp = client.post(
        "/users/me/avatar-upload-url", json={"contentType": "image/jpeg"}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"].startswith(f"{user_id}/")
    assert body["key"].endswith(".jpg")
    assert body["expiresIn"] == 900
    assert body["requiredHeaders"]["Content-Type"] == "image/jpeg"
    # A real presigned S3 URL, signed locally (no network).
    assert f"/avatars/{user_id}/" in body["uploadUrl"]
    assert "X-Amz-Signature=" in body["uploadUrl"]


def test_avatar_upload_url_rejects_unsupported_content_type(client):
    headers, _ = _auth(client)
    resp = client.post(
        "/users/me/avatar-upload-url", json={"contentType": "image/gif"}, headers=headers
    )
    assert resp.status_code == 422


def test_avatar_upload_url_requires_auth(client):
    resp = client.post("/users/me/avatar-upload-url", json={"contentType": "image/png"})
    assert resp.status_code == 401


def test_confirm_avatar_sets_profile(client):
    headers, user_id = _auth(client)
    key = client.post(
        "/users/me/avatar-upload-url", json={"contentType": "image/png"}, headers=headers
    ).json()["key"]

    confirm = client.put("/users/me/avatar", json={"key": key}, headers=headers)
    assert confirm.status_code == 200
    avatar_url = confirm.json()["avatarUrl"]
    assert avatar_url.endswith(f"/avatars/{key}")

    me = client.get("/users/me", headers=headers)
    assert me.json()["avatarUrl"] == avatar_url


def test_confirm_avatar_rejects_foreign_key(client):
    headers, _ = _auth(client)
    foreign_key = f"{uuid.uuid4()}/evil.png"
    resp = client.put("/users/me/avatar", json={"key": foreign_key}, headers=headers)
    assert resp.status_code == 403
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_confirm_avatar_requires_auth(client):
    resp = client.put("/users/me/avatar", json={"key": "whatever/x.png"})
    assert resp.status_code == 401
