import asyncio
from collections.abc import AsyncIterator

import pytest

from loom.adapters import (
    AdapterEvent,
    AdapterFailure,
    AdapterRequest,
    ModelAdapter,
    StreamComplete,
    StreamError,
    StreamText,
    StreamTiming,
    StreamToolCall,
    StreamUsage,
    validate_model_id,
)
from loom.contracts import (
    ContractError,
    FinishReason,
    ModelRequest,
    ModelResponse,
    StructuredError,
    Timing,
    TokenUsage,
    ToolCall,
    ValueSource,
)


def _request() -> ModelRequest:
    return ModelRequest("req-1", "op-1", ({"role": "user", "content": "hello"},))


class FakeAdapter:
    backend_id = "fake"

    def __init__(self) -> None:
        self.cancelled: set[str] = set()

    async def cancel(self, request_id: str) -> None:
        self.cancelled.add(request_id)

    async def stream(self, bound: AdapterRequest) -> AsyncIterator[AdapterEvent]:
        yield StreamText(bound.request.request_id, 0, "hello", {"provider_chunk": 1})
        yield StreamToolCall(
            bound.request.request_id, 1, ToolCall("call-1", "search", {"q": "loom"})
        )
        yield StreamUsage(
            bound.request.request_id,
            2,
            TokenUsage(3, 2, ValueSource.BACKEND_REPORTED, {"total": 5}),
        )
        yield StreamTiming(
            bound.request.request_id,
            3,
            Timing(12, 2, source=ValueSource.MEASURED, raw={"clock": "monotonic"}),
        )
        yield StreamComplete(
            bound.request.request_id,
            4,
            ModelResponse(
                bound.request.request_id,
                "hello",
                FinishReason.STOP,
                self.backend_id,
                bound.model_id,
                raw_finish_reason="end_turn",
                raw={"provider": "fake"},
            ),
        )


def test_protocol_streams_all_normalized_events_asynchronously() -> None:
    async def consume() -> list[AdapterEvent]:
        adapter = FakeAdapter()
        assert isinstance(adapter, ModelAdapter)
        return [event async for event in adapter.stream(AdapterRequest(_request(), "model-v1"))]

    events = asyncio.run(consume())
    assert [event.sequence for event in events] == list(range(5))
    assert isinstance(events[0], StreamText)
    assert isinstance(events[1], StreamToolCall)
    assert isinstance(events[2], StreamUsage)
    assert events[2].usage.raw == {"total": 5}
    assert isinstance(events[3], StreamTiming)
    assert events[3].timing.source is ValueSource.MEASURED
    assert isinstance(events[4], StreamComplete)
    assert events[4].response.raw_finish_reason == "end_turn"


def test_cancellation_is_async_and_idempotent() -> None:
    async def cancel_twice() -> set[str]:
        adapter = FakeAdapter()
        await adapter.cancel("req-1")
        await adapter.cancel("req-1")
        return adapter.cancelled

    assert asyncio.run(cancel_twice()) == {"req-1"}


@pytest.mark.parametrize("model_id", ["", "latest", "vendor/latest", "model:latest", "auto"])
def test_moving_or_missing_model_identifiers_are_rejected(model_id: str) -> None:
    with pytest.raises(ContractError, match="model_id"):
        AdapterRequest(_request(), model_id)


def test_pinned_and_versioned_model_identifiers_are_accepted() -> None:
    for model_id in ("qwen2.5-coder:3b-q4_K_M", "vendor/model-2026-08-27", "mlx/model-v1"):
        validate_model_id(model_id)


def test_events_reject_invalid_metadata_and_preserve_raw_error() -> None:
    error = StructuredError("rate_limit", "slow down", True, "429")
    event = StreamError("req-1", 0, error, {"retry_after": 2})
    assert event.raw == {"retry_after": 2}
    with pytest.raises(ContractError, match="sequence"):
        StreamText("req-1", -1, "bad")
    with pytest.raises(ContractError, match="must not be empty"):
        StreamText("req-1", 0, "")
    with pytest.raises(ContractError, match="does not match"):
        StreamComplete(
            "req-1", 0, ModelResponse("other", "", FinishReason.STOP, "fake", "model-v1")
        )


def test_adapter_failure_exposes_structured_error() -> None:
    error = StructuredError("timeout", "deadline exceeded", True)
    failure = AdapterFailure("ollama", "req-1", error)
    assert failure.error is error
    assert "deadline exceeded" in str(failure)
