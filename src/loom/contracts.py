"""Backend-neutral data contracts used at Loom's system boundaries.

The contracts deliberately depend only on the Python standard library.  Adapters
may translate their SDK objects into these values without leaking provider types
into the planner, telemetry, or agent harness.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, TypeVar

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class ContractError(ValueError):
    """Raised when a value violates a core contract."""


class PrivacyRequirement(str, Enum):
    LOCAL_ONLY = "local_only"
    ALLOW_CLOUD = "allow_cloud"


class FinishReason(str, Enum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALL = "tool_call"
    CANCELLED = "cancelled"
    ERROR = "error"
    UNKNOWN = "unknown"


class ValueSource(str, Enum):
    MEASURED = "measured"
    BACKEND_REPORTED = "backend_reported"
    ESTIMATED = "estimated"


class MemoryPressure(str, Enum):
    NORMAL = "normal"
    WARN = "warn"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


def _nonempty(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be a non-empty string")


def _nonnegative(name: str, value: float | None) -> None:
    if value is not None and value < 0:
        raise ContractError(f"{name} must be non-negative")


def _fraction(name: str, value: float) -> None:
    if not 0 <= value <= 1:
        raise ContractError(f"{name} must be between 0 and 1")


def _json(value: Any, path: str = "value") -> JsonValue:
    """Copy and validate a JSON value, rejecting opaque backend SDK objects."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json(item, f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError(f"{path} keys must be strings")
            result[key] = _json(item, f"{path}.{key}")
        return result
    raise ContractError(f"{path} is not JSON serializable")


T = TypeVar("T", bound="SerializableContract")


class SerializableContract:
    """Stable JSON-object serialization shared by all contracts."""

    def to_dict(self) -> dict[str, JsonValue]:
        return _json(asdict(self))  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class Operation(SerializableContract):
    operation_id: str
    task_category: str
    context_references: tuple[str, ...] = ()
    tool_needs: tuple[str, ...] = ()
    estimated_difficulty: float = 0.5
    privacy_requirement: PrivacyRequirement = PrivacyRequirement.ALLOW_CLOUD
    minimum_quality: float = 0.0

    def __post_init__(self) -> None:
        _nonempty("operation_id", self.operation_id)
        _nonempty("task_category", self.task_category)
        _fraction("estimated_difficulty", self.estimated_difficulty)
        _fraction("minimum_quality", self.minimum_quality)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Operation:
        values = dict(data)
        values["context_references"] = tuple(values.get("context_references", ()))
        values["tool_needs"] = tuple(values.get("tool_needs", ()))
        values["privacy_requirement"] = PrivacyRequirement(
            values.get("privacy_requirement", PrivacyRequirement.ALLOW_CLOUD)
        )
        return cls(**values)


@dataclass(frozen=True, slots=True)
class ModelRequest(SerializableContract):
    request_id: str
    operation_id: str
    messages: tuple[dict[str, JsonValue], ...]
    tool_schemas: tuple[dict[str, JsonValue], ...] = ()
    max_output_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    run_id: str | None = None
    task_id: str | None = None

    def __post_init__(self) -> None:
        _nonempty("request_id", self.request_id)
        _nonempty("operation_id", self.operation_id)
        if not self.messages:
            raise ContractError("messages must not be empty")
        _nonnegative("max_output_tokens", self.max_output_tokens)
        if self.max_output_tokens == 0:
            raise ContractError("max_output_tokens must be greater than zero")
        if self.temperature is not None and not 0 <= self.temperature <= 2:
            raise ContractError("temperature must be between 0 and 2")
        if self.top_p is not None:
            _fraction("top_p", self.top_p)
        object.__setattr__(self, "messages", tuple(_json(m, "messages") for m in self.messages))
        object.__setattr__(
            self, "tool_schemas", tuple(_json(s, "tool_schemas") for s in self.tool_schemas)
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelRequest:
        values = dict(data)
        values["messages"] = tuple(values["messages"])
        values["tool_schemas"] = tuple(values.get("tool_schemas", ()))
        return cls(**values)


@dataclass(frozen=True, slots=True)
class ToolCall(SerializableContract):
    call_id: str
    name: str
    arguments: dict[str, JsonValue]

    def __post_init__(self) -> None:
        _nonempty("call_id", self.call_id)
        _nonempty("name", self.name)
        object.__setattr__(self, "arguments", _json(self.arguments, "arguments"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ToolCall:
        return cls(**dict(data))


@dataclass(frozen=True, slots=True)
class ToolResult(SerializableContract):
    call_id: str
    output: JsonValue = None
    exit_status: int | None = None
    duration_ms: float = 0
    truncated: bool = False
    original_bytes: int | None = None
    returned_bytes: int | None = None
    error_category: str | None = None

    def __post_init__(self) -> None:
        _nonempty("call_id", self.call_id)
        _nonnegative("duration_ms", self.duration_ms)
        _nonnegative("original_bytes", self.original_bytes)
        _nonnegative("returned_bytes", self.returned_bytes)
        if (
            self.original_bytes is not None
            and self.returned_bytes is not None
            and self.returned_bytes > self.original_bytes
        ):
            raise ContractError("returned_bytes cannot exceed original_bytes")
        object.__setattr__(self, "output", _json(self.output, "output"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ToolResult:
        return cls(**dict(data))


@dataclass(frozen=True, slots=True)
class TokenUsage(SerializableContract):
    input_tokens: int = 0
    output_tokens: int = 0
    source: ValueSource = ValueSource.BACKEND_REPORTED
    raw: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonnegative("input_tokens", self.input_tokens)
        _nonnegative("output_tokens", self.output_tokens)
        object.__setattr__(self, "raw", _json(self.raw, "usage.raw"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TokenUsage:
        values = dict(data)
        values["source"] = ValueSource(values.get("source", ValueSource.BACKEND_REPORTED))
        return cls(**values)


@dataclass(frozen=True, slots=True)
class Timing(SerializableContract):
    total_ms: float
    time_to_first_token_ms: float | None = None
    model_load_ms: float | None = None
    source: ValueSource = ValueSource.MEASURED
    raw: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonnegative("total_ms", self.total_ms)
        _nonnegative("time_to_first_token_ms", self.time_to_first_token_ms)
        _nonnegative("model_load_ms", self.model_load_ms)
        object.__setattr__(self, "raw", _json(self.raw, "timing.raw"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Timing:
        values = dict(data)
        values["source"] = ValueSource(values.get("source", ValueSource.MEASURED))
        return cls(**values)


@dataclass(frozen=True, slots=True)
class StructuredError(SerializableContract):
    category: str
    message: str
    retryable: bool = False
    code: str | None = None
    details: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty("category", self.category)
        _nonempty("message", self.message)
        object.__setattr__(self, "details", _json(self.details, "error.details"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StructuredError:
        return cls(**dict(data))


@dataclass(frozen=True, slots=True)
class ModelResponse(SerializableContract):
    request_id: str
    content: str
    finish_reason: FinishReason
    backend_id: str
    model_id: str
    tool_calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage = field(default_factory=TokenUsage)
    timing: Timing | None = None
    error: StructuredError | None = None
    raw_finish_reason: str | None = None
    raw: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty("request_id", self.request_id)
        _nonempty("backend_id", self.backend_id)
        _nonempty("model_id", self.model_id)
        if self.finish_reason is FinishReason.ERROR and self.error is None:
            raise ContractError("an error response requires structured error information")
        object.__setattr__(self, "raw", _json(self.raw, "response.raw"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelResponse:
        values = dict(data)
        values["finish_reason"] = FinishReason(values["finish_reason"])
        values["tool_calls"] = tuple(ToolCall.from_dict(v) for v in values.get("tool_calls", ()))
        values["usage"] = TokenUsage.from_dict(values.get("usage", {}))
        if values.get("timing") is not None:
            values["timing"] = Timing.from_dict(values["timing"])
        if values.get("error") is not None:
            values["error"] = StructuredError.from_dict(values["error"])
        return cls(**values)


@dataclass(frozen=True, slots=True)
class HardwareSnapshot(SerializableContract):
    timestamp: str
    memory_pressure: MemoryPressure
    free_memory_bytes: int
    active_memory_bytes: int
    wired_memory_bytes: int
    compressed_memory_bytes: int
    swap_in_bytes: int
    swap_out_bytes: int
    cpu_load: float

    def __post_init__(self) -> None:
        _nonempty("timestamp", self.timestamp)
        for name in (
            "free_memory_bytes", "active_memory_bytes", "wired_memory_bytes",
            "compressed_memory_bytes", "swap_in_bytes", "swap_out_bytes",
        ):
            _nonnegative(name, getattr(self, name))
        _fraction("cpu_load", self.cpu_load)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HardwareSnapshot:
        values = dict(data)
        values["memory_pressure"] = MemoryPressure(values["memory_pressure"])
        return cls(**values)


@dataclass(frozen=True, slots=True)
class RouteCandidate(SerializableContract):
    backend_id: str
    model_id: str
    score: float | None = None
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty("backend_id", self.backend_id)
        _nonempty("model_id", self.model_id)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RouteCandidate:
        values = dict(data)
        values["rejection_reasons"] = tuple(values.get("rejection_reasons", ()))
        return cls(**values)


@dataclass(frozen=True, slots=True)
class RouteDecision(SerializableContract):
    backend_id: str
    model_id: str
    matched_rule: str
    alternatives: tuple[RouteCandidate, ...] = ()
    escalation_condition: str | None = None

    def __post_init__(self) -> None:
        _nonempty("backend_id", self.backend_id)
        _nonempty("model_id", self.model_id)
        _nonempty("matched_rule", self.matched_rule)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RouteDecision:
        values = dict(data)
        values["alternatives"] = tuple(
            RouteCandidate.from_dict(v) for v in values.get("alternatives", ())
        )
        return cls(**values)


@dataclass(frozen=True, slots=True)
class TraceEvent(SerializableContract):
    schema_version: str
    event_type: str
    run_id: str
    task_id: str
    operation_id: str
    timestamp: str
    routing: RouteDecision | None = None
    telemetry: dict[str, JsonValue] = field(default_factory=dict)
    usage: TokenUsage | None = None
    retry_count: int = 0
    outcome: str | None = None
    artifact_references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("schema_version", "event_type", "run_id", "task_id", "operation_id", "timestamp"):
            _nonempty(name, getattr(self, name))
        _nonnegative("retry_count", self.retry_count)
        object.__setattr__(self, "telemetry", _json(self.telemetry, "telemetry"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TraceEvent:
        values = dict(data)
        if values.get("routing") is not None:
            values["routing"] = RouteDecision.from_dict(values["routing"])
        if values.get("usage") is not None:
            values["usage"] = TokenUsage.from_dict(values["usage"])
        values["artifact_references"] = tuple(values.get("artifact_references", ()))
        return cls(**values)
