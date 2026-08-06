"""COM-207: saved payment methods (list / add / delete, tokenized).

Covers the ``SavedPaymentMethod`` domain invariants, the SQL repository round-trip and its
owner-scoping, the ``PaymentMethodService`` use cases, and the HTTP surface — including the security
guarantee that the stored provider token is never returned and that one user can never see or delete
another user's method.

The API tests are Postgres-free: the service is backed by an in-memory repository and a stub
verifier via ``dependency_overrides``; the repository tests exercise the real SQL adapter.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_payment_method_service, get_token_verifier
from app.application.commands import AddPaymentMethodCommand, DeletePaymentMethodCommand
from app.application.payment_methods import PaymentMethodService
from app.application.queries import ListPaymentMethodsQuery
from app.core.principal import Principal
from app.domain.enums import PaymentMethodType
from app.domain.errors import PaymentMethodNotFoundError, PaymentMethodValidationError
from app.domain.payment_method import SavedPaymentMethod
from app.main import app
from app.repositories.sql_payment_method_repository import SqlPaymentMethodRepository
from tests.fakes import InMemoryPaymentMethodRepository, StubVerifier

GOOD_TOKEN = "good-token"
PROBLEM_JSON = "application/problem+json"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")
USER = uuid.UUID(PRINCIPAL.user_id)
OTHER = uuid.uuid4()

_CARD_BODY = {
    "type": "credit_card",
    "token": "tok_visa_secret",
    "brand": "visa",
    "last4": "4242",
    "expMonth": 12,
    "expYear": 2030,
}


def _ct(response) -> str:
    return response.headers["content-type"].split(";")[0].strip()


# --------------------------------------------------------------------------- domain invariants


def test_saved_method_defaults_id_and_created_at():
    method = SavedPaymentMethod(user_id=USER, type=PaymentMethodType.CREDIT_CARD, token="tok_1")
    assert isinstance(method.id, uuid.UUID)
    assert method.created_at is not None


def test_blank_token_is_rejected():
    with pytest.raises(PaymentMethodValidationError):
        SavedPaymentMethod(user_id=USER, type=PaymentMethodType.CREDIT_CARD, token="   ")


@pytest.mark.parametrize("last4", ["123", "12345", "abcd", "12a4"])
def test_malformed_last4_is_rejected(last4: str):
    with pytest.raises(PaymentMethodValidationError):
        SavedPaymentMethod(
            user_id=USER, type=PaymentMethodType.CREDIT_CARD, token="tok_1", last4=last4
        )


@pytest.mark.parametrize("month", [0, 13, -1])
def test_exp_month_out_of_range_is_rejected(month: int):
    with pytest.raises(PaymentMethodValidationError):
        SavedPaymentMethod(
            user_id=USER, type=PaymentMethodType.CREDIT_CARD, token="tok_1", exp_month=month
        )


def test_exp_year_before_2000_is_rejected():
    with pytest.raises(PaymentMethodValidationError):
        SavedPaymentMethod(
            user_id=USER, type=PaymentMethodType.CREDIT_CARD, token="tok_1", exp_year=1999
        )


def test_wallet_method_needs_no_card_metadata():
    method = SavedPaymentMethod(user_id=USER, type=PaymentMethodType.PAYPAL, token="tok_pp")
    assert method.brand is None
    assert method.last4 is None
    assert method.exp_month is None


# --------------------------------------------------------------------------- SQL repository


@pytest.fixture
def payment_method_repo(db_session) -> SqlPaymentMethodRepository:
    return SqlPaymentMethodRepository(db_session)


def _card(
    user_id: uuid.UUID, *, token: str = "tok_visa", last4: str = "4242"
) -> SavedPaymentMethod:
    return SavedPaymentMethod(
        user_id=user_id,
        type=PaymentMethodType.CREDIT_CARD,
        token=token,
        brand="visa",
        last4=last4,
        exp_month=12,
        exp_year=2030,
    )


def test_add_then_list_round_trips(payment_method_repo):
    saved = payment_method_repo.add(_card(USER))
    listed = payment_method_repo.list_for_user(USER)
    assert [m.id for m in listed] == [saved.id]
    assert listed[0].token == "tok_visa"
    assert listed[0].last4 == "4242"
    assert listed[0].brand == "visa"


def test_list_is_owner_scoped(payment_method_repo):
    payment_method_repo.add(_card(USER))
    assert payment_method_repo.list_for_user(OTHER) == []


def test_get_is_owner_scoped(payment_method_repo):
    saved = payment_method_repo.add(_card(USER))
    assert payment_method_repo.get(saved.id, user_id=USER) is not None
    assert payment_method_repo.get(saved.id, user_id=OTHER) is None


def test_delete_is_owner_scoped(payment_method_repo):
    saved = payment_method_repo.add(_card(USER))
    assert payment_method_repo.delete(saved.id, user_id=OTHER) is False
    assert payment_method_repo.get(saved.id, user_id=USER) is not None
    assert payment_method_repo.delete(saved.id, user_id=USER) is True
    assert payment_method_repo.get(saved.id, user_id=USER) is None


def test_delete_unknown_returns_false(payment_method_repo):
    assert payment_method_repo.delete(uuid.uuid4(), user_id=USER) is False


def test_list_is_newest_first(payment_method_repo):
    older = SavedPaymentMethod(
        user_id=USER,
        type=PaymentMethodType.CREDIT_CARD,
        token="tok_old",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = SavedPaymentMethod(
        user_id=USER,
        type=PaymentMethodType.PAYPAL,
        token="tok_new",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    payment_method_repo.add(older)
    payment_method_repo.add(newer)
    listed = payment_method_repo.list_for_user(USER)
    assert [m.token for m in listed] == ["tok_new", "tok_old"]


# --------------------------------------------------------------------------- service use cases


def _service() -> tuple[PaymentMethodService, InMemoryPaymentMethodRepository]:
    repo = InMemoryPaymentMethodRepository()
    return PaymentMethodService(repo), repo


def test_service_add_persists_and_returns():
    service, repo = _service()
    saved = service.add(
        AddPaymentMethodCommand(
            user_id=USER,
            type=PaymentMethodType.CREDIT_CARD,
            token="tok_visa",
            brand="visa",
            last4="4242",
            exp_month=12,
            exp_year=2030,
        )
    )
    assert repo.get(saved.id, user_id=USER) is not None
    assert saved.token == "tok_visa"


def test_service_list_is_scoped():
    service, _ = _service()
    service.add(AddPaymentMethodCommand(user_id=USER, type=PaymentMethodType.PAYPAL, token="tok_a"))
    service.add(
        AddPaymentMethodCommand(user_id=OTHER, type=PaymentMethodType.PAYPAL, token="tok_b")
    )
    mine = service.list(ListPaymentMethodsQuery(user_id=USER))
    assert [m.token for m in mine] == ["tok_a"]


def test_service_delete_removes():
    service, repo = _service()
    saved = service.add(
        AddPaymentMethodCommand(user_id=USER, type=PaymentMethodType.PAYPAL, token="tok_a")
    )
    service.delete(DeletePaymentMethodCommand(user_id=USER, payment_method_id=saved.id))
    assert repo.get(saved.id, user_id=USER) is None


def test_service_delete_unknown_raises():
    service, _ = _service()
    with pytest.raises(PaymentMethodNotFoundError):
        service.delete(DeletePaymentMethodCommand(user_id=USER, payment_method_id=uuid.uuid4()))


def test_service_delete_other_users_method_raises():
    service, _ = _service()
    saved = service.add(
        AddPaymentMethodCommand(user_id=OTHER, type=PaymentMethodType.PAYPAL, token="tok_b")
    )
    with pytest.raises(PaymentMethodNotFoundError):
        service.delete(DeletePaymentMethodCommand(user_id=USER, payment_method_id=saved.id))


# --------------------------------------------------------------------------- API surface


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    for dep in (get_payment_method_service, get_token_verifier):
        app.dependency_overrides.pop(dep, None)


def _build() -> tuple[TestClient, InMemoryPaymentMethodRepository]:
    repo = InMemoryPaymentMethodRepository()
    app.dependency_overrides[get_payment_method_service] = lambda: PaymentMethodService(repo)
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app), repo


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def test_add_returns_201_without_token():
    client, repo = _build()
    response = client.post("/payment-methods", json=_CARD_BODY, headers=_auth())
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "credit_card"
    assert body["brand"] == "visa"
    assert body["last4"] == "4242"
    assert body["expMonth"] == 12
    assert body["expYear"] == 2030
    assert "id" in body
    assert "createdAt" in body
    # Security: the stored provider token is never echoed back to the client.
    assert "token" not in body
    assert "tok_visa_secret" not in response.text
    # It was actually persisted for the caller.
    assert len(repo.list_for_user(USER)) == 1


def test_add_wallet_without_metadata_returns_201():
    client, repo = _build()
    response = client.post(
        "/payment-methods", json={"type": "paypal", "token": "tok_pp"}, headers=_auth()
    )
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "paypal"
    assert body["brand"] is None
    assert body["last4"] is None
    assert len(repo.list_for_user(USER)) == 1


def test_list_returns_saved_methods_without_token():
    client, repo = _build()
    repo.add(SavedPaymentMethod(user_id=USER, type=PaymentMethodType.PAYPAL, token="tok_secret"))
    response = client.get("/payment-methods", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["type"] == "paypal"
    assert "token" not in body[0]
    assert "tok_secret" not in response.text


def test_list_excludes_other_users_methods():
    client, repo = _build()
    repo.add(SavedPaymentMethod(user_id=OTHER, type=PaymentMethodType.PAYPAL, token="tok_other"))
    response = client.get("/payment-methods", headers=_auth())
    assert response.status_code == 200
    assert response.json() == []


def test_delete_returns_204_and_removes():
    client, repo = _build()
    saved = repo.add(SavedPaymentMethod(user_id=USER, type=PaymentMethodType.PAYPAL, token="tok_a"))
    response = client.delete(f"/payment-methods/{saved.id}", headers=_auth())
    assert response.status_code == 204
    assert response.content == b""
    assert repo.get(saved.id, user_id=USER) is None


def test_delete_unknown_returns_404():
    client, _ = _build()
    response = client.delete(f"/payment-methods/{uuid.uuid4()}", headers=_auth())
    assert response.status_code == 404
    assert _ct(response) == PROBLEM_JSON


def test_delete_other_users_method_returns_404_and_leaves_it():
    client, repo = _build()
    saved = repo.add(
        SavedPaymentMethod(user_id=OTHER, type=PaymentMethodType.PAYPAL, token="tok_other")
    )
    response = client.delete(f"/payment-methods/{saved.id}", headers=_auth())
    assert response.status_code == 404
    assert repo.get(saved.id, user_id=OTHER) is not None


def test_add_with_malformed_last4_returns_422():
    client, _ = _build()
    response = client.post("/payment-methods", json={**_CARD_BODY, "last4": "12"}, headers=_auth())
    assert response.status_code == 422
    assert _ct(response) == PROBLEM_JSON


def test_add_with_unknown_type_returns_422():
    client, _ = _build()
    body = {"type": "bitcoin", "token": "tok_x"}
    response = client.post("/payment-methods", json=body, headers=_auth())
    assert response.status_code == 422
    assert _ct(response) == PROBLEM_JSON


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/payment-methods"),
        ("POST", "/payment-methods"),
        ("DELETE", "/payment-methods/{}"),
    ],
)
def test_routes_require_authentication(method: str, path: str):
    client, _ = _build()
    response = client.request(method, path.format(uuid.uuid4()))
    assert response.status_code == 401
    assert _ct(response) == PROBLEM_JSON
    assert response.headers["WWW-Authenticate"] == "Bearer"
