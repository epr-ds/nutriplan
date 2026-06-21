def _register(client, email="alice@example.com", password="supersecret", name="Alice"):
    return client.post(
        "/auth/register",
        json={"email": email, "password": password, "name": name},
    )


def test_register_returns_201_and_tokens(client):
    response = _register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["accessToken"]
    assert body["refreshToken"]
    assert body["expiresIn"] == 900
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["name"] == "Alice"
    assert body["user"]["id"]


def test_register_duplicate_email_conflicts(client):
    _register(client)
    response = _register(client)
    assert response.status_code == 409


def test_register_short_password_unprocessable(client):
    response = _register(client, password="short")
    assert response.status_code == 422


def test_login_success(client):
    _register(client)
    response = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "supersecret"}
    )
    assert response.status_code == 200
    assert response.json()["accessToken"]


def test_login_wrong_password_unauthorized(client):
    _register(client)
    response = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "not-the-password"}
    )
    assert response.status_code == 401


def test_login_locks_out_after_repeated_failures(client):
    _register(client)
    for _ in range(5):
        client.post(
            "/auth/login", json={"email": "alice@example.com", "password": "wrong-password"}
        )
    # Even the correct password is now refused while the lockout window is open.
    response = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "supersecret"}
    )
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_users_me_with_valid_token(client):
    body = _register(client).json()
    response = client.get("/users/me", headers={"Authorization": f"Bearer {body['accessToken']}"})
    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"


def test_users_me_without_token_unauthorized(client):
    response = client.get("/users/me")
    assert response.status_code == 401
