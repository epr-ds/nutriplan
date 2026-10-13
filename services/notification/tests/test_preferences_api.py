"""NTF-104 API tests for the preferences router (no Redis, no network).

The store is overridden with the real in-memory adapter and the token verifier with a stub, so
these exercise the genuine router, request validation, auth dependency, error mapping and wire
projection. Adapter parity is proven separately in ``test_preferences_store.py``, which runs
the same operations against Redis; repeating that here would only make the suite slower.

The two things worth reading closely are the route-shadowing test -- ``/notifications/
preferences`` is a literal that ``/notifications/{notification_id}/read`` would happily eat if
the routers were registered the other way round -- and the group of ``422`` cases, which pin
that everything the domain refuses is refused at the edge with the same status.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.adapters.in_memory_preferences_repository import InMemoryPreferencesRepository
from app.api.deps import get_preferences_repository, get_token_verifier
from app.core.principal import Principal
from app.domain.enums import NotificationChannel, NotificationType
from app.domain.preferences import NotificationPreferences
from app.main import app
from tests.fakes import StubVerifier

GOOD_TOKEN = "good-token"
OTHER_TOKEN = "other-token"

PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
OTHER_PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="b@b.com")

USER = uuid.UUID(PRINCIPAL.user_id)
OTHER_USER = uuid.UUID(OTHER_PRINCIPAL.user_id)

PATH = "/notifications/preferences"
PROBLEM_JSON = "application/problem+json"

IN_APP = NotificationChannel.IN_APP
PUSH = NotificationChannel.PUSH
CONFIRMED = NotificationType.ORDER_CONFIRMED

NIGHT = {"start": "22:00", "end": "07:00", "timeZone": "America/Mexico_City"}


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_preferences_repository, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build(*stored: NotificationPreferences) -> TestClient:
    repository = InMemoryPreferencesRepository()
    for preferences in stored:
        repository.save(preferences)
    app.dependency_overrides[get_preferences_repository] = lambda: repository
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier(
        {GOOD_TOKEN: PRINCIPAL, OTHER_TOKEN: OTHER_PRINCIPAL}
    )
    return TestClient(app)


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _row(body: dict, notification_type: NotificationType) -> dict:
    return next(row for row in body["types"] if row["type"] == notification_type.value)


def _full_matrix(**overrides: dict) -> list[dict]:
    """Every type, enabled, with named rows overridden -- what a real client sends."""
    return [
        {"type": t.value, "inApp": True, "push": True} | overrides.get(t.value, {})
        for t in NotificationType
    ]


# -- reading ----------------------------------------------------------------------------


def test_a_user_who_never_saved_gets_the_defaults_not_a_404():
    """They *do* have preferences -- the defaults -- and the settings screen must render."""
    client = _build()

    response = client.get(PATH, headers=_auth())

    assert response.status_code == 200
    body = response.json()
    assert len(body["types"]) == len(NotificationType)
    assert all(row["inApp"] and row["push"] for row in body["types"])
    assert body["quietHours"] is None
    assert body["updatedAt"]


def test_the_matrix_lists_every_type_in_declaration_order():
    """A client renders the list as it arrives; the order is part of the contract."""
    client = _build()

    body = client.get(PATH, headers=_auth()).json()

    assert [row["type"] for row in body["types"]] == [t.value for t in NotificationType]


def test_stored_mutes_are_reflected_in_the_matrix():
    client = _build(NotificationPreferences(user_id=USER).muting(CONFIRMED, PUSH))

    body = client.get(PATH, headers=_auth()).json()

    assert _row(body, CONFIRMED) == {"type": CONFIRMED.value, "inApp": True, "push": False}
    assert all(row["push"] for row in body["types"] if row["type"] != CONFIRMED.value)


def test_stored_quiet_hours_are_projected():
    client = _build()
    client.put(PATH, headers=_auth(), json={"types": [], "quietHours": NIGHT})

    body = client.get(PATH, headers=_auth()).json()

    assert body["quietHours"] == NIGHT


def test_one_user_never_sees_anothers_preferences():
    """The subject comes from the token, so there is no request that reads someone else."""
    client = _build(
        NotificationPreferences(user_id=OTHER_USER)
        .muting(CONFIRMED, PUSH)
        .muting(CONFIRMED, IN_APP)
    )

    body = client.get(PATH, headers=_auth()).json()

    assert _row(body, CONFIRMED)["push"] is True


# -- replacing --------------------------------------------------------------------------


def test_a_replacement_round_trips():
    client = _build()

    put = client.put(
        PATH,
        headers=_auth(),
        json={"types": _full_matrix(**{CONFIRMED.value: {"push": False}}), "quietHours": NIGHT},
    )

    assert put.status_code == 200
    assert _row(put.json(), CONFIRMED)["push"] is False
    assert put.json() == client.get(PATH, headers=_auth()).json()


def test_an_omitted_type_returns_to_its_default():
    """Replacement, not patch: what the client did not mention is what it is already showing."""
    client = _build(NotificationPreferences(user_id=USER).muting(CONFIRMED, PUSH))

    body = client.put(PATH, headers=_auth(), json={"types": [], "quietHours": None}).json()

    assert _row(body, CONFIRMED)["push"] is True


def test_an_empty_types_array_is_how_a_client_asks_for_the_defaults():
    client = _build()

    response = client.put(PATH, headers=_auth(), json={"types": [], "quietHours": None})

    assert response.status_code == 200
    assert all(row["inApp"] and row["push"] for row in response.json()["types"])


def test_null_quiet_hours_clears_the_window():
    client = _build()
    client.put(PATH, headers=_auth(), json={"types": [], "quietHours": NIGHT})

    body = client.put(PATH, headers=_auth(), json={"types": [], "quietHours": None}).json()

    assert body["quietHours"] is None


def test_omitting_quiet_hours_entirely_also_clears_it():
    """It defaults to ``None``, and the write is a replacement -- so absence means cleared."""
    client = _build()
    client.put(PATH, headers=_auth(), json={"types": [], "quietHours": NIGHT})

    assert client.put(PATH, headers=_auth(), json={"types": []}).json()["quietHours"] is None


def test_quiet_hours_default_to_the_services_time_zone():
    client = _build()

    body = client.put(
        PATH, headers=_auth(), json={"types": [], "quietHours": {"start": "22:00", "end": "07:00"}}
    ).json()

    assert body["quietHours"]["timeZone"] == "America/Mexico_City"


def test_a_replacement_by_one_user_does_not_touch_another():
    client = _build()

    client.put(
        PATH,
        headers=_auth(OTHER_TOKEN),
        json={"types": _full_matrix(**{CONFIRMED.value: {"push": False}})},
    )

    assert _row(client.get(PATH, headers=_auth()).json(), CONFIRMED)["push"] is True


# -- rejections -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"quietHours": None}, "types is required, so a forgotten field cannot re-enable all"),
        ({"types": [{"type": "order_teleported"}]}, "unknown notification type"),
        ({"types": {}}, "types must be an array of rows, not a map"),
        ({"types": [], "quietHours": {"start": "9pm", "end": "07:00"}}, "start is not HH:MM"),
        ({"types": [], "quietHours": {"start": "22:00", "end": "24:00"}}, "24:00 is not a time"),
        ({"types": [], "quietHours": {"start": "22:00"}}, "end is required"),
        (
            {"types": [], "quietHours": NIGHT | {"timeZone": "Mars/Ares"}},
            "unknown IANA zone",
        ),
        (
            {"types": [], "quietHours": {"start": "22:00", "end": "22:00"}},
            "start == end is ambiguous, so it is refused",
        ),
        (
            {"types": [{"type": "order_confirmed"}, {"type": "order_confirmed", "push": False}]},
            "a duplicate row carries two answers to one question",
        ),
    ],
)
def test_an_unacceptable_replacement_is_422(body, reason):
    client = _build()

    response = client.put(PATH, headers=_auth(), json=body)

    assert response.status_code == 422, reason
    assert response.headers["content-type"].startswith(PROBLEM_JSON)


def test_a_rejected_replacement_stores_nothing():
    client = _build(NotificationPreferences(user_id=USER).muting(CONFIRMED, PUSH))

    client.put(
        PATH,
        headers=_auth(),
        json={"types": [{"type": "order_confirmed"}, {"type": "order_confirmed", "push": False}]},
    )

    assert _row(client.get(PATH, headers=_auth()).json(), CONFIRMED)["push"] is False


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_no_token_is_401_problem_json(method):
    client = _build()

    response = client.request(method, PATH, json={"types": []})

    assert response.status_code == 401
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_a_rejected_token_is_401(method):
    client = _build()

    response = client.request(method, PATH, headers=_auth("nope"), json={"types": []})

    assert response.status_code == 401


# -- routing ----------------------------------------------------------------------------


def test_preferences_resolves_to_the_preferences_handler():
    """``preferences`` is a literal sitting under ``/notifications``, where the feed's
    parameterised routes live. Registration order decides which wins, so pin that a settings
    read reaches the settings handler -- a matrix, not a notification and not a 422 about an
    unparseable id -- before anyone adds a ``GET /notifications/{notification_id}``.
    """
    client = _build()

    response = client.get(PATH, headers=_auth())

    assert response.status_code == 200
    assert "types" in response.json()


def test_the_feed_routes_still_work_alongside_it():
    """The preferences router is included first; it must not swallow the feed's own paths."""
    client = _build()

    assert client.get("/notifications", headers=_auth()).status_code == 200
    assert client.get("/notifications/unread-count", headers=_auth()).status_code == 200
