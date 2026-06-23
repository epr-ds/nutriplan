"""Tests for the constrain/parse/retry/fallback loop (AIA-104, AC1 + AC3)."""

import dataclasses

import pytest
from pydantic import BaseModel

from app.llm.client import LLMClient
from app.llm.fake import FakeLLMProvider
from app.llm.retry import RetryPolicy
from app.llm.types import LLMMessage, LLMRequest, LLMResponse, Role
from app.structured.errors import StructuredOutputError
from app.structured.parser import StructuredOutputParser
from app.structured.service import StructuredCompletion


class Plan(BaseModel):
    name: str


_REQUEST = LLMRequest.of([LLMMessage(Role.USER, "make a plan")])


def _response(text: str) -> LLMResponse:
    return LLMResponse(content=text, model="fake")


def _completion(
    provider: FakeLLMProvider,
    *,
    max_attempts: int = 2,
    fallback=None,
) -> StructuredCompletion[Plan]:
    client = LLMClient(provider, RetryPolicy(max_retries=0))
    parser = StructuredOutputParser(Plan)
    return StructuredCompletion(client, parser, max_attempts=max_attempts, fallback=fallback)


def test_returns_validated_model_and_attaches_constraint() -> None:
    provider = FakeLLMProvider([_response('{"name": "Cutting"}')])

    result = _completion(provider).complete(_REQUEST)

    assert result == Plan(name="Cutting")
    # AC1: the schema constraint was attached to the outgoing request.
    assert provider.calls[0].response_format is not None
    assert provider.calls[0].response_format.name == "Plan"


def test_retries_invalid_output_then_succeeds() -> None:
    provider = FakeLLMProvider([_response("nope"), _response('{"name": "Bulking"}')])

    result = _completion(provider, max_attempts=2).complete(_REQUEST)

    assert result.name == "Bulking"
    assert provider.call_count == 2
    # The retry re-prompted with a corrective message appended to the conversation.
    assert len(provider.calls[1].messages) > len(provider.calls[0].messages)
    assert provider.calls[1].messages[-1].role is Role.USER


def test_falls_back_after_exhausting_attempts() -> None:
    provider = FakeLLMProvider([_response("nope"), _response("still bad")])

    def fallback(error: StructuredOutputError) -> Plan:
        return Plan(name="curated")

    result = _completion(provider, max_attempts=2, fallback=fallback).complete(_REQUEST)

    assert result.name == "curated"
    assert provider.call_count == 2


def test_raises_typed_error_when_no_fallback() -> None:
    provider = FakeLLMProvider([_response("nope"), _response("still bad")])

    with pytest.raises(StructuredOutputError):
        _completion(provider, max_attempts=2).complete(_REQUEST)


def test_respects_a_caller_supplied_response_format() -> None:
    provider = FakeLLMProvider([_response('{"name": "X"}')])
    preset = StructuredOutputParser(Plan, name="Custom").response_format()

    _completion(provider).complete(dataclasses.replace(_REQUEST, response_format=preset))

    assert provider.calls[0].response_format.name == "Custom"


def test_rejects_zero_attempts() -> None:
    client = LLMClient(FakeLLMProvider(), RetryPolicy(max_retries=0))
    with pytest.raises(ValueError):
        StructuredCompletion(client, StructuredOutputParser(Plan), max_attempts=0)
