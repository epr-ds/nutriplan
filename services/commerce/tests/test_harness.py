"""The QA test harness (COM-801): a clean, ephemeral Commerce database with seeded orders.

Run with ``COMMERCE_TEST_DB=postgres`` to bring Postgres up through Testcontainers (as the
``commerce-testcontainers`` CI job does); without it the same tests use ``COMMERCE_DATABASE_URL`` or
SQLite. They prove the harness itself: the database is the one asked for, the seed helpers store
orders and payment methods that read back through the repositories (owner-scoped), the teardown
helpers leave the database empty, and the same fixtures serve an integration pass through the real
API and SQL repositories -- only the token check is stubbed -- whose responses are checked against
``contracts/commerce.openapi.yaml``.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from openapi_core import OpenAPI
from openapi_core.testing import MockRequest, MockResponse
from sqlalchemy import func, inspect, select, text

from app.api.deps import get_token_verifier
from app.core.principal import Principal
from app.db.base import Base
from app.db.models import OrderModel
from app.domain.enums import OrderStatus
from app.main import app
from app.repositories.sql_order_repository import SqlOrderRepository
from app.repositories.sql_payment_method_repository import SqlPaymentMethodRepository
from tests.fakes import StubVerifier
from tests.seed import SEED_USER_ID, clear_data, create_schema, drop_schema, seed_orders

HOST = "http://localhost:8083"
TOKEN = "harness-token"
_PRINCIPAL = Principal(user_id=str(SEED_USER_ID), email="harness.user@example.com")

GATEWAY_PREFIX = "/commerce/v1"


def _spec_path(path: str) -> str:
    """Drop the gateway prefix before validating against the published contract."""
    return path[len(GATEWAY_PREFIX) :] if path.startswith(GATEWAY_PREFIX) else path


# --- the database ------------------------------------------------------------------------------


def test_the_database_is_the_one_asked_for(engine, db_backend, db_source):
    if os.environ.get("COMMERCE_TEST_DB", "").strip().lower() in {"postgres", "testcontainers"}:
        assert db_source == "testcontainers"
        assert db_backend == "postgres"
    else:
        assert db_source in {"env", "sqlite"}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
        if db_backend == "postgres":
            assert "PostgreSQL" in connection.execute(text("SELECT version()")).scalar_one()


def test_every_mapped_table_exists(engine):
    assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())


# --- seed ------------------------------------------------------------------------------------


def test_seeded_orders_are_stored_and_read_back(db_session, seeded_orders):
    repository = SqlOrderRepository(db_session)
    kitchen, grocery = seeded_orders

    stored_kitchen = repository.get(kitchen.id, user_id=SEED_USER_ID)
    stored_grocery = repository.get(grocery.id, user_id=SEED_USER_ID)

    assert stored_kitchen is not None and stored_grocery is not None
    assert stored_kitchen.status is OrderStatus.PENDING
    assert [item.name for item in stored_kitchen.items] == ["Lentil soup", "Protein bowl"]
    assert stored_kitchen.total == kitchen.total
    assert stored_grocery.status is OrderStatus.CONFIRMED
    assert stored_grocery.grocery_external_order_id == "FB-1001"
    assert {order.id for order in repository.list_for_user(SEED_USER_ID)} == {
        kitchen.id,
        grocery.id,
    }


def test_seeded_orders_are_invisible_to_other_users(db_session, seeded_orders):
    repository = SqlOrderRepository(db_session)
    stranger = uuid.uuid4()

    assert repository.get(seeded_orders[0].id, user_id=stranger) is None
    assert repository.list_for_user(stranger) == []


def test_seeded_payment_methods_are_stored_and_read_back(db_session, seeded_payment_methods):
    stored = SqlPaymentMethodRepository(db_session).list_for_user(SEED_USER_ID)

    assert {method.id for method in stored} == {method.id for method in seeded_payment_methods}
    card = next(method for method in stored if method.last4 is not None)
    assert (card.brand, card.last4) == ("visa", "4242")


def test_seed_helpers_can_seed_several_users(db_session):
    other = uuid.uuid4()
    seed_orders(db_session)
    seed_orders(db_session, user_id=other)

    repository = SqlOrderRepository(db_session)
    assert len(repository.list_for_user(SEED_USER_ID)) == 2
    assert len(repository.list_for_user(other)) == 2


# --- teardown --------------------------------------------------------------------------------


def test_clear_data_empties_every_table_but_keeps_the_schema(
    engine, db_session, seeded_orders, seeded_payment_methods
):
    clear_data(db_session)

    for table in Base.metadata.sorted_tables:
        assert db_session.execute(select(func.count()).select_from(table)).scalar_one() == 0
    # The schema is still there: seeding again works without recreating it.
    assert len(seed_orders(db_session)) == 2
    assert db_session.execute(select(func.count()).select_from(OrderModel)).scalar_one() == 2


def test_drop_and_create_schema_start_over_from_nothing(engine, db_session, seeded_orders):
    db_session.close()
    drop_schema(engine)
    assert not set(Base.metadata.tables) & set(inspect(engine).get_table_names())

    create_schema(engine)
    assert db_session.execute(select(func.count()).select_from(OrderModel)).scalar_one() == 0


def test_each_test_starts_from_an_empty_database(db_session):
    # Earlier tests seeded orders; the autouse schema fixture tore them down.
    assert db_session.execute(select(func.count()).select_from(OrderModel)).scalar_one() == 0


# --- integration through the real API and repositories ------------------------------------


def _locate_spec() -> Path | None:
    override = os.environ.get("COMMERCE_OPENAPI_SPEC")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "commerce.openapi.yaml"
        if candidate.exists():
            return candidate
    return None


@pytest.fixture(scope="module")
def openapi() -> OpenAPI:
    spec_path = _locate_spec()
    if spec_path is None:
        if os.environ.get("CI"):
            raise RuntimeError("commerce.openapi.yaml not found under CI")
        pytest.skip("commerce.openapi.yaml not found (local run)")
    return OpenAPI.from_file_path(str(spec_path))


@pytest.fixture
def api(client):
    """The real app on the harness database, with only the bearer-token check stubbed."""
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({TOKEN: _PRINCIPAL})
    yield client
    app.dependency_overrides.pop(get_token_verifier, None)


def _assert_conforms(openapi: OpenAPI, path: str, response) -> None:
    # Strict: the contract documents which members may be ``null`` (settled in COM-802).
    openapi.validate_response(
        MockRequest(host_url=HOST, method="get", path=_spec_path(path)),
        MockResponse(
            data=response.content,
            status_code=response.status_code,
            content_type="application/json",
        ),
    )


_AUTH = {"Authorization": f"Bearer {TOKEN}"}


def test_the_api_lists_the_seeded_orders_as_the_contract_says(api, openapi, seeded_orders):
    response = api.get("/commerce/v1/orders", headers=_AUTH)

    assert response.status_code == 200
    assert {order["id"] for order in response.json()} == {str(order.id) for order in seeded_orders}
    _assert_conforms(openapi, "/commerce/v1/orders", response)


def test_the_api_serves_a_seeded_order_as_the_contract_says(api, openapi, seeded_orders):
    kitchen = seeded_orders[0]

    response = api.get(f"/commerce/v1/orders/{kitchen.id}", headers=_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["fulfillmentType"] == "dark_kitchen"
    assert body["total"]["amount"] == 273.0
    assert [item["name"] for item in body["items"]] == ["Lentil soup", "Protein bowl"]
    _assert_conforms(openapi, f"/commerce/v1/orders/{kitchen.id}", response)


def test_the_api_serves_the_seeded_grocery_order(api, openapi, seeded_orders):
    grocery = seeded_orders[1]

    response = api.get(f"/commerce/v1/orders/{grocery.id}", headers=_AUTH)

    assert response.status_code == 200
    assert response.json()["groceryOrder"]["externalOrderId"] == "FB-1001"
    _assert_conforms(openapi, f"/commerce/v1/orders/{grocery.id}", response)


def test_the_api_lists_the_seeded_payment_methods_without_tokens(
    api, openapi, seeded_payment_methods
):
    response = api.get("/commerce/v1/payment-methods", headers=_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert {method["id"] for method in body} == {str(m.id) for m in seeded_payment_methods}
    assert all("token" not in method for method in body)
    _assert_conforms(openapi, "/commerce/v1/payment-methods", response)


def test_the_api_hides_the_seeded_orders_from_other_users(client, seeded_orders):
    stranger = Principal(user_id=str(uuid.uuid4()), email="stranger@example.com")
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({TOKEN: stranger})
    try:
        response = client.get(f"/commerce/v1/orders/{seeded_orders[0].id}", headers=_AUTH)
    finally:
        app.dependency_overrides.pop(get_token_verifier, None)

    assert response.status_code == 404
