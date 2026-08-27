"""Typed asynchronous boundary implemented by every model backend.

Backend adapters translate provider-specific streams into these events.  The
planner and agent harness therefore never need to import an Ollama, MLX, or
cloud-provider SDK type.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol, TypeAlias, runtime_checkable

from loom.contracts import (
    ContractError,
    JsonValue,
    ModelRequest,
    ModelResponse,
    StructuredError,
    Timing,
    TokenUsage,
    ToolCall,
    _json,
    _nonempty,
)

_MOVING_MODEL_ALIASES = frozenset({"auto", "automatic", "default", "latest"})


def validate_model_id(model_id: str) -> None:
    """Reject missing and moving model identifiers used in non-reproducible runs."""
    _nonempty("model_id", model_id)
    normalized = model_id.strip().lower()
    final_component = normalized.rsplit("/", 1)[-1]
    tag = final_component.rsplit(":", 1)[-1]
    if normalized in _MOVING_MODEL_ALIASES or tag in _MOVING_MODEL_ALIASES:
        raise ContractError(f"model_id must be explicit, not the moving alias {model_id!r}")


@dataclass(frozen=True, slots=True)
class AdapterRequest:
    """A model request bound to one exact backend and model."""

    request: ModelRequest
    model_id: str

    def __post_init__(self) -> None:
        validate_model_id(self.model_id)


@dataclass(frozen=True, slots=True)
class StreamText:
    request_id: str
    sequence: int
    text: str
    raw: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_event(self.request_id, self.sequence)
        if not self.text:
            raise ContractError("streamed text must not be empty")
        object.__setattr__(self, "raw", _json(self.raw, "stream_text.raw"))


@dataclass(frozen=True, slots=True)
class StreamToolCall:
    request_id: str
    sequence: int
    tool_call: ToolCall
    raw: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_event(self.request_id, self.sequence)
        object.__setattr__(self, "raw", _json(self.raw, "stream_tool_call.raw"))


@dataclass(frozen=True, slots=True)
class StreamUsage:
    request_id: str
    sequence: int
    usage: TokenUsage

    def __post_init__(self) -> None:
        _validate_event(self.request_id, self.sequence)


@dataclass(frozen=True, slots=True)
class StreamTiming:
    request_id: str
    sequence: int
    timing: Timing

    def __post_init__(self) -> None:
        _validate_event(self.request_id, self.sequence)


@dataclass(frozen=True, slots=True)
class StreamComplete:
    request_id: str
    sequence: int
    response: ModelResponse

    def __post_init__(self) -> None:
        _validate_event(self.request_id, self.sequence)
        if self.response.request_id != self.request_id:
            raise ContractError("completion response request_id does not match its stream")
        validate_model_id(self.response.model_id)


@dataclass(frozen=True, slots=True)
class StreamError:
    request_id: str
    sequence: int
    error: StructuredError
    raw: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_event(self.request_id, self.sequence)
        object.__setattr__(self, "raw", _json(self.raw, "stream_error.raw"))


AdapterEvent: TypeAlias = (
    StreamText | StreamToolCall | StreamUsage | StreamTiming | StreamComplete | StreamError
)


def _validate_event(request_id: str, sequence: int) -> None:
    _nonempty("request_id", request_id)
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ContractError("sequence must be a non-negative integer")


@runtime_checkable
class ModelAdapter(Protocol):
    """Backend-neutral asynchronous streaming adapter.

    ``stream`` is an async-iterator factory, allowing callers to consume the
    first event immediately. ``cancel`` must be idempotent: cancelling an
    unknown or already-finished request is a no-op.
    """

    @property
    def backend_id(self) -> str:
        """Stable backend identity recorded in responses and traces."""
        ...

    def stream(self, request: AdapterRequest) -> AsyncIterator[AdapterEvent]:
        """Yield ordered normalized events, ending in completion or error."""
        ...

    async def cancel(self, request_id: str) -> None:
        """Request cancellation without blocking the event consumer."""
        ...


class AdapterFailure(RuntimeError):
    """Raised when an adapter cannot produce a normalized stream error."""

    def __init__(self, backend_id: str, request_id: str, error: StructuredError) -> None:
        _nonempty("backend_id", backend_id)
        _nonempty("request_id", request_id)
        self.backend_id = backend_id
        self.request_id = request_id
        self.error = error
        super().__init__(f"{backend_id} request {request_id} failed: {error.message}")
