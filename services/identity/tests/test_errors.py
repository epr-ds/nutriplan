def _is_problem(response):
    return response.headers["content-type"].startswith("application/problem+json")


def test_unknown_route_returns_problem_json(client):
    response = client.get("/no-such-route")
    assert response.status_code == 404
    assert _is_problem(response)
    body = response.json()
    assert body["status"] == 404
    assert body["title"]
    assert body["instance"] == "/no-such-route"


def test_validation_error_returns_problem_json(client):
    response = client.post(
        "/auth/register", json={"email": "not-an-email", "password": "x", "name": "y"}
    )
    assert response.status_code == 422
    assert _is_problem(response)
    body = response.json()
    assert body["status"] == 422
    assert isinstance(body["errors"], list) and body["errors"]


def test_unauthorized_returns_problem_json(client):
    response = client.get("/users/me")
    assert response.status_code == 401
    assert _is_problem(response)
    assert response.json()["status"] == 401
