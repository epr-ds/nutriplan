"""DPL-305 API tests for ``GET /nutrition/disclaimer`` (Mongo-free).

The endpoint is static metadata, so only the auth dependency is overridden: the real router,
projection and payload are exercised without MongoDB or network access.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_token_verifier
from app.core.principal import Principal
from app.core.security import InvalidTokenError
from app.main import app

GOOD_TOKEN = "good-token"
_NUTRIENTS = ("calories", "protein", "carbs", "fat", "sugar")


class StubVerifier:
    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    def verify(self, token: str) -> Principal:
        try:
            return self._principals[token]
        except KeyError as exc:
            raise InvalidTokenError("unknown token") from exc


@pytest.fixture
def client() -> TestClient:
    principal = Principal(user_id="user-123", email="a@b.com")
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: principal})
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {GOOD_TOKEN}"}


def test_disclaimer_requires_authentication(client):
    assert client.get("/nutrition/disclaimer").status_code == 401


def test_disclaimer_returns_sources_and_disclaimer(client):
    response = client.get("/nutrition/disclaimer", headers=_auth())

    assert response.status_code == 200
    data = response.json()
    assert data["disclaimer"].strip()
    assert data["medicalAdvice"] is False
    assert data["lastReviewed"]

    sources = data["sources"]
    assert sources, "at least one source must be listed"
    assert {source["id"] for source in sources}
    for source in sources:
        assert source["name"].strip()
        assert source["url"].startswith("http")
        assert source["verified"] is True


def test_every_nutrient_is_traceable_to_a_listed_verified_source(client):
    data = client.get("/nutrition/disclaimer", headers=_auth()).json()

    field_sources = data["fieldSources"]
    assert set(field_sources) == set(_NUTRIENTS)

    verified_ids = {source["id"] for source in data["sources"] if source["verified"] is True}
    for nutrient, source_id in field_sources.items():
        assert source_id in verified_ids, nutrient


def test_disclaimer_makes_no_medical_or_health_claims(client):
    payload = client.get("/nutrition/disclaimer", headers=_auth()).json()
    lowered = json.dumps(payload).lower()

    # Assertive treatment/health claims must not appear anywhere in the payload.
    banned = (
        "cures",
        "treats",
        "heals",
        "diagnoses",
        "prescribes",
        "guaranteed",
        "clinically proven",
        "prevents disease",
    )
    for phrase in banned:
        assert phrase not in lowered, phrase

    # The disclaimer is a negation, not a claim, and is explicitly flagged non-medical.
    assert "not a substitute for professional medical advice" in lowered
    assert payload["medicalAdvice"] is False
