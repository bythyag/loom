import pytest

from loom.classifier import (
    ClassifierState,
    OperationCategory,
    RiskLevel,
    classify_operation,
)
from loom.contracts import Operation, PrivacyRequirement


def operation(category: str, **kwargs: object) -> Operation:
    return Operation("op-1", category, **kwargs)


@pytest.mark.parametrize(
    ("task_category", "state", "kwargs", "expected"),
    [
        ("find symbol", ClassifierState("navigate repository"), {}, OperationCategory.NAVIGATION),
        ("read file", ClassifierState("retrieve content"), {}, OperationCategory.RETRIEVAL),
        ("explain code", ClassifierState("summarize module"), {}, OperationCategory.EXPLANATION),
        (
            "edit",
            ClassifierState("change function", affected_files=1),
            {"tool_needs": ("apply_patch",)},
            OperationCategory.SINGLE_FILE_EDIT,
        ),
        (
            "refactor",
            ClassifierState("modify API", affected_files=3),
            {"tool_needs": ("apply_patch",)},
            OperationCategory.MULTI_FILE_EDIT,
        ),
        (
            "test failure",
            ClassifierState("diagnose pytest traceback", prior_failures=1),
            {"tool_needs": ("run_tests",)},
            OperationCategory.TEST_FAILURE_DIAGNOSIS,
        ),
    ],
)
def test_classifies_supported_operations(
    task_category: str,
    state: ClassifierState,
    kwargs: dict[str, object],
    expected: OperationCategory,
) -> None:
    result = classify_operation(operation(task_category, **kwargs), state)
    assert result.category is expected
    assert result.matched_rule in result.reasoning[-1]
    assert 0 <= result.confidence <= 1


def test_unknown_and_unbounded_edits_default_to_cloud() -> None:
    unknown = classify_operation(operation("invent new workflow"), ClassifierState("do something"))
    unbounded = classify_operation(operation("edit"), ClassifierState("change code"))
    for result in (unknown, unbounded):
        assert result.category is OperationCategory.UNKNOWN_HIGH_RISK
        assert result.risk is RiskLevel.HIGH
        assert result.requires_cloud


def test_context_failures_tools_and_quality_affect_routing() -> None:
    result = classify_operation(
        operation("explain", minimum_quality=0.95, tool_needs=("search_text",)),
        ClassifierState("explain architecture", context_tokens=40_000, prior_failures=2),
    )
    assert result.requires_cloud
    assert result.risk is RiskLevel.HIGH
    assert "tool_needs=search_text" in result.reasoning
    assert any("context" in reason for reason in result.reasoning)
    assert any("failures" in reason for reason in result.reasoning)


def test_local_only_privacy_overrides_cloud_default() -> None:
    result = classify_operation(
        operation(
            "explain",
            estimated_difficulty=0.95,
            privacy_requirement=PrivacyRequirement.LOCAL_ONLY,
        ),
        ClassifierState("explain private code"),
    )
    assert result.default_backend == "local"
    assert result.risk is RiskLevel.HIGH


def test_identical_inputs_produce_identical_results() -> None:
    op = operation("single file edit", tool_needs=("apply_patch",))
    state = ClassifierState("modify parser", context_tokens=1_000, affected_files=1)
    assert classify_operation(op, state) == classify_operation(op, state)


@pytest.mark.parametrize(
    "state",
    [
        ClassifierState("valid"),
    ],
)
def test_state_is_hashable_for_deterministic_cache_keys(state: ClassifierState) -> None:
    assert hash(state) == hash(state)


def test_state_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="action"):
        ClassifierState(" ")
    with pytest.raises(ValueError, match="prior_failures"):
        ClassifierState("explain", prior_failures=-1)
