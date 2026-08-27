import json

import pytest

from loom.contracts import (
    ContractError,
    FinishReason,
    HardwareSnapshot,
    MemoryPressure,
    ModelRequest,
    ModelResponse,
    Operation,
    PrivacyRequirement,
    RouteCandidate,
    RouteDecision,
    StructuredError,
    Timing,
    TokenUsage,
    ToolCall,
    ToolResult,
    TraceEvent,
    ValueSource,
)


def test_operation_validates_quality_and_round_trips() -> None:
    operation = Operation(
        operation_id="op-1",
        task_category="repository_search",
        context_references=("src/loom",),
        tool_needs=("search",),
        estimated_difficulty=0.3,
        privacy_requirement=PrivacyRequirement.LOCAL_ONLY,
        minimum_quality=0.8,
    )
    assert Operation.from_dict(json.loads(json.dumps(operation.to_dict()))) == operation
    with pytest.raises(ContractError, match="minimum_quality"):
        Operation("op-1", "search", minimum_quality=1.1)


def test_request_rejects_invalid_limits_and_non_json_backend_values() -> None:
    request = ModelRequest(
        request_id="req-1",
        operation_id="op-1",
        messages=({"role": "user", "content": "find auth"},),
        tool_schemas=({"name": "search", "input_schema": {"type": "object"}},),
        max_output_tokens=256,
        temperature=0,
    )
    assert ModelRequest.from_dict(request.to_dict()) == request
    with pytest.raises(ContractError, match="messages"):
        ModelRequest("req", "op", ())
    with pytest.raises(ContractError, match="JSON"):
        ModelRequest("req", "op", ({"opaque": object()},))


def test_model_response_preserves_normalized_and_raw_backend_fields() -> None:
    response = ModelResponse(
        request_id="req-1",
        content="",
        finish_reason=FinishReason.TOOL_CALL,
        raw_finish_reason="tool_calls",
        backend_id="openrouter",
        model_id="vendor/model-2026-01-01",
        tool_calls=(ToolCall("call-1", "search", {"query": "auth"}),),
        usage=TokenUsage(50, 12, ValueSource.BACKEND_REPORTED, {"total_tokens": 62}),
        timing=Timing(120, 30, source=ValueSource.MEASURED),
        raw={"provider": "vendor"},
    )
    assert ModelResponse.from_dict(json.loads(json.dumps(response.to_dict()))) == response
    with pytest.raises(ContractError, match="structured error"):
        ModelResponse("req", "", FinishReason.ERROR, "backend", "model")


def test_tool_result_records_truncation_error_and_duration() -> None:
    result = ToolResult(
        "call-1", "partial", exit_status=1, duration_ms=12.5, truncated=True,
        original_bytes=100, returned_bytes=20, error_category="command_failed",
    )
    assert ToolResult.from_dict(result.to_dict()) == result
    with pytest.raises(ContractError, match="returned_bytes"):
        ToolResult("call", original_bytes=10, returned_bytes=11)


def test_hardware_snapshot_validates_normalized_cpu_load() -> None:
    snapshot = HardwareSnapshot(
        "2026-08-27T12:00:00Z", MemoryPressure.NORMAL, 10, 20, 30, 40, 1, 2, 0.25
    )
    assert HardwareSnapshot.from_dict(snapshot.to_dict()) == snapshot
    with pytest.raises(ContractError, match="cpu_load"):
        HardwareSnapshot("now", MemoryPressure.NORMAL, 0, 0, 0, 0, 0, 0, 101)


def test_trace_event_round_trips_all_required_evidence() -> None:
    route = RouteDecision(
        "ollama", "qwen2.5-coder:3b-q4_K_M", "local_search",
        alternatives=(RouteCandidate("openrouter", "vendor/model-2026-01-01", 0.8, ("cost",)),),
        escalation_condition="local quality below 0.8",
    )
    event = TraceEvent(
        schema_version="1.0",
        event_type="operation.completed",
        run_id="run-1",
        task_id="task-1",
        operation_id="op-1",
        timestamp="2026-08-27T12:00:00Z",
        routing=route,
        telemetry={"latency_ms": 123.4, "cache_hit": True},
        usage=TokenUsage(100, 20, ValueSource.ESTIMATED),
        retry_count=1,
        outcome="success",
        artifact_references=("artifacts/result.json",),
    )
    encoded = json.dumps(event.to_dict())
    assert TraceEvent.from_dict(json.loads(encoded)) == event


def test_structured_error_round_trips_details() -> None:
    error = StructuredError("timeout", "request timed out", True, "ETIMEDOUT", {"seconds": 30})
    assert StructuredError.from_dict(error.to_dict()) == error
