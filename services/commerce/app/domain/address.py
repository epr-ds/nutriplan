"""Delivery ``Address`` entity — maps the OpenAPI ``AddressRequest`` shape."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class Address:
    street: str
    city: str
    state: str
    zip_code: str
    country: str
    apartment: str | None = None
    instructions: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    user_id: uuid.UUID | None = None
