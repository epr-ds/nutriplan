"""NTF-105 API tests for the in-app feed router (no Redis, no network).

The store is overridden with the real in-memory adapter and the token verifier with a stub,
so these exercise the genuine router, query-param validation, auth dependency, error mapping,
and wire projection. Adapter parity for the underlying behaviour is proven separately in
``test_feed.py``, which runs the same use cases against Redis as well; duplicating that here
would only make the suite slower without testing anything new.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.adapters.retention import RetentionPolicy
from app.api.deps import get_notification_repository, get_token_verifier
from app.core.principal import Principal
from app.domain.enums import DeliveryStatus, NotificationChannel, NotificationType
from app.domain.notification import Notification
from app.main import app
from tests.fakes import StubVerifier

GOOD_TOKEN = "good-token"
OTHER_TOKEN = "other-token"
OPAQUE_SUBJECT_TOKEN = "opaque-subject-token"

PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
OTHER_PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="b@b.com")
OPAQUE_PRINCIPAL = Principal(user_id="not-a-uuid", email="c@b.com")

USER = uuid.UUID(PRINCIPAL.user_id)
OTHER_USER = uuid.UUID(OTHER_PRINCIPAL.user_id)

NOW = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=30)
POLICY = RetentionPolicy(ttl_seconds=3_600, max_entries=100)

PROBLEM_JSON = "application/problem+json"


def _notification(
    *,
    user_id: uuid.UUID = USER,
    age_seconds: int = 0,
    read: bool = False,
    type_: NotificationType = NotificationType.ORDER_CONFIRMED,
    payload: dict | None = None,
) -> Notification:
    created = NOW - timedelta(seconds=age_seconds)
    return Notification(
        user_id=user_id,
        type=type_,
        payload={"orderId": "abc"} if payload is None else payload,
        channels=(NotificationChannel.IN_APP, NotificationChannel.PUSH),
        status=DeliveryStatus.SENT,
        created_at=created,
        read_at=created if read else None,
    )


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_notification_repository, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build(*notifications: Notification) -> TestClient:
    repository = InMemoryNotificationRepository(policy=POLICY)
    for notification in notifications:
        repository.add(notification)
    app.dependency_overrides[get_notification_repository] = lambda: repository
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier(
        {
            GOOD_TOKEN: PRINCIPAL,
            OTHER_TOKEN: OTHER_PRINCIPAL,
            OPAQUE_SUBJECT_TOKEN: OPAQUE_PRINCIPAL,
        }
    )
    return TestClient(app)


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# -- authentication --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/notifications"),
        ("get", "/notifications/unread-count"),
        ("post", f"/notifications/{uuid.uuid4()}/read"),
    ],
)
def test_every_feed_endpoint_requires_a_token(method, path):
    client = _build()
    response = getattr(client, method)(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_an_unknown_token_is_rejected():
    client = _build()
    assert client.get("/notifications", headers=_auth("nope")).status_code == 401


def test_a_token_whose_subject_is_not_a_user_id_is_rejected():
    """The feed is addressed solely by the token subject, so a subject that cannot be a user
    id is refused outright rather than coerced into something that would address a stranger's
    feed -- or, worse, a feed that silently belongs to nobody."""
    client = _build()
    response = client.get("/notifications", headers=_auth(OPAQUE_SUBJECT_TOKEN))
    assert response.status_code == 401


def test_an_auth_failure_is_a_problem_document():
    client = _build()
    response = client.get("/notifications")
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.json()["status"] == 401
    assert response.json()["title"] == "Unauthorized"


# -- listing ---------------------------------------------------------------------------


def test_listing_an_empty_feed():
    response = _build().get("/notifications", headers=_auth())
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "page": 1,
        "limit": 20,
        "unreadCount": 0,
        "hasMore": False,
    }


def test_listing_returns_newest_first():
    older = _notification(age_seconds=200)
    newer = _notification(age_seconds=100)
    response = _build(older, newer).get("/notifications", headers=_auth())

    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [str(newer.id), str(older.id)]


def test_a_listed_notification_carries_the_full_wire_shape():
    notification = _notification(payload={"orderId": "o-1", "items": [{"name": "Bowl"}]})
    response = _build(notification).get("/notifications", headers=_auth())

    item = response.json()["items"][0]
    assert item == {
        "id": str(notification.id),
        "type": "order_confirmed",
        "payload": {"orderId": "o-1", "items": [{"name": "Bowl"}]},
        "channels": ["in_app", "push"],
        "status": "sent",
        "createdAt": item["createdAt"],
        "readAt": None,
        "isRead": False,
    }


def test_a_listed_notification_never_echoes_the_owner():
    """The caller *is* the owner -- the id came from their token -- so returning it adds
    nothing and only widens the response."""
    response = _build(_notification()).get("/notifications", headers=_auth())
    assert "userId" not in response.json()["items"][0]


def test_listing_is_scoped_to_the_caller():
    mine = _notification()
    theirs = _notification(user_id=OTHER_USER)
    client = _build(mine, theirs)

    assert [i["id"] for i in client.get("/notifications", headers=_auth()).json()["items"]] == [
        str(mine.id)
    ]
    assert [
        i["id"] for i in client.get("/notifications", headers=_auth(OTHER_TOKEN)).json()["items"]
    ] == [str(theirs.id)]


def test_listing_paginates():
    notifications = [_notification(age_seconds=index * 10) for index in range(5)]
    client = _build(*notifications)

    first = client.get("/notifications?page=1&limit=2", headers=_auth()).json()
    second = client.get("/notifications?page=2&limit=2", headers=_auth()).json()
    third = client.get("/notifications?page=3&limit=2", headers=_auth()).json()

    assert [i["id"] for i in first["items"]] == [str(n.id) for n in notifications[:2]]
    assert [i["id"] for i in second["items"]] == [str(n.id) for n in notifications[2:4]]
    assert [i["id"] for i in third["items"]] == [str(notifications[4].id)]
    assert (first["hasMore"], second["hasMore"], third["hasMore"]) == (True, True, False)
    assert (first["page"], first["limit"]) == (1, 2)


def test_listing_reports_the_unread_badge_alongside_the_page():
    client = _build(
        _notification(age_seconds=10),
        _notification(age_seconds=20),
        _notification(age_seconds=30, read=True),
    )
    assert client.get("/notifications", headers=_auth()).json()["unreadCount"] == 2


def test_listing_can_be_filtered_to_unread():
    unread = _notification(age_seconds=10)
    client = _build(unread, _notification(age_seconds=20, read=True))

    body = client.get("/notifications?unreadOnly=true", headers=_auth()).json()

    assert [item["id"] for item in body["items"]] == [str(unread.id)]
    assert body["unreadCount"] == 1


@pytest.mark.parametrize("query", ["page=0", "limit=0", "limit=101", "page=-1", "limit=abc"])
def test_listing_rejects_out_of_range_paging(query):
    response = _build().get(f"/notifications?{query}", headers=_auth())
    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.json()["errors"]


def test_listing_accepts_the_maximum_page_size():
    assert _build().get("/notifications?limit=100", headers=_auth()).status_code == 200


# -- unread count ----------------------------------------------------------------------


def test_the_unread_count_endpoint_resolves_and_counts():
    """Also pins the route ordering: ``unread-count`` is a literal segment and must never be
    captured as a notification id by a neighbouring parameterised route."""
    client = _build(_notification(age_seconds=10), _notification(age_seconds=20, read=True))

    response = client.get("/notifications/unread-count", headers=_auth())

    assert response.status_code == 200
    assert response.json() == {"unreadCount": 1}


def test_the_unread_count_is_per_caller():
    client = _build(_notification(), _notification(user_id=OTHER_USER), _notification())

    assert client.get("/notifications/unread-count", headers=_auth()).json() == {"unreadCount": 2}
    assert client.get("/notifications/unread-count", headers=_auth(OTHER_TOKEN)).json() == {
        "unreadCount": 1
    }


# -- mark read -------------------------------------------------------------------------


def test_marking_read_returns_the_updated_notification():
    notification = _notification()
    client = _build(notification)

    response = client.post(f"/notifications/{notification.id}/read", headers=_auth())

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(notification.id)
    assert body["isRead"] is True
    assert body["readAt"] is not None


def test_marking_read_updates_the_badge():
    notification = _notification()
    client = _build(notification, _notification(age_seconds=10))

    client.post(f"/notifications/{notification.id}/read", headers=_auth())

    assert client.get("/notifications/unread-count", headers=_auth()).json() == {"unreadCount": 1}


def test_marking_read_twice_is_idempotent():
    notification = _notification()
    client = _build(notification)

    first = client.post(f"/notifications/{notification.id}/read", headers=_auth())
    second = client.post(f"/notifications/{notification.id}/read", headers=_auth())

    assert second.status_code == 200
    assert second.json()["readAt"] == first.json()["readAt"]


def test_marking_an_unknown_notification_read_is_not_found():
    response = _build().post(f"/notifications/{uuid.uuid4()}/read", headers=_auth())
    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_JSON)


def test_marking_another_users_notification_read_is_indistinguishable_from_unknown():
    """Two requests, one for a stranger's real notification and one for an id that does not
    exist at all, must produce the same answer -- otherwise the endpoint is an oracle for
    discovering other users' notification ids."""
    theirs = _notification(user_id=OTHER_USER)
    unknown_id = uuid.uuid4()
    client = _build(theirs)

    stranger = client.post(f"/notifications/{theirs.id}/read", headers=_auth())
    unknown = client.post(f"/notifications/{unknown_id}/read", headers=_auth())

    assert stranger.status_code == unknown.status_code == 404
    assert stranger.json()["title"] == unknown.json()["title"]
    # Identical but for the id the caller already supplied: the response tells them nothing
    # they did not already know.
    assert stranger.json()["detail"].replace(str(theirs.id), "<id>") == unknown.json()[
        "detail"
    ].replace(str(unknown_id), "<id>")


def test_a_refused_mark_read_leaves_the_owners_notification_untouched():
    theirs = _notification(user_id=OTHER_USER)
    client = _build(theirs)

    client.post(f"/notifications/{theirs.id}/read", headers=_auth())

    owner_view = client.get("/notifications", headers=_auth(OTHER_TOKEN)).json()
    assert owner_view["items"][0]["isRead"] is False
    assert owner_view["unreadCount"] == 1


def test_a_malformed_notification_id_is_unprocessable():
    response = _build().post("/notifications/not-a-uuid/read", headers=_auth())
    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
