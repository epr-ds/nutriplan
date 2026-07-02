from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.domain.repositories import OrderRepository
from app.repositories.sql_order_repository import SqlOrderRepository

DbSession = Annotated[Session, Depends(get_db)]


def get_order_repository(db: DbSession) -> OrderRepository:
    """Provide the SQL-backed order repository bound to the request session."""
    return SqlOrderRepository(db)


OrderRepositoryDep = Annotated[OrderRepository, Depends(get_order_repository)]
