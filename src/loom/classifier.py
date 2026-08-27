"""Deterministic repository-operation classification for routing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from loom.contracts import Operation, PrivacyRequirement


class OperationCategory(str, Enum):
    NAVIGATION = "navigation"
    RETRIEVAL = "retrieval"
    EXPLANATION = "explanation"
    SINGLE_FILE_EDIT = "single_file_edit"
    MULTI_FILE_EDIT = "multi_file_edit"
    TEST_FAILURE_DIAGNOSIS = "test_failure_diagnosis"
    UNKNOWN_HIGH_RISK = "unknown_high_risk"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class ClassifierState:
    """Stable execution facts that can affect classification."""

    action: str
    context_tokens: int = 0
    prior_failures: int = 0
    affected_files: int = 0

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError("action must not be empty")
        for name in ("context_tokens", "prior_failures", "affected_files"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class Classification:
    category: OperationCategory
    risk: RiskLevel
    default_backend: str
    matched_rule: str
    confidence: float
    reasoning: tuple[str, ...]

    @property
    def requires_cloud(self) -> bool:
        return self.default_backend == "cloud"


_NAVIGATION_TERMS = frozenset({"navigate", "navigation", "locate", "find", "where"})
_RETRIEVAL_TERMS = frozenset({"retrieve", "retrieval", "read", "search", "lookup"})
_EXPLANATION_TERMS = frozenset({"explain", "explanation", "summarize", "describe"})
_EDIT_TERMS = frozenset({"edit", "modify", "patch", "implement", "change", "refactor"})
_TEST_TERMS = frozenset({"test", "failure", "diagnose", "debug", "pytest", "traceback"})
_MUTATING_TOOLS = frozenset({"apply_patch", "write_file", "edit_file"})
_TEST_TOOLS = frozenset({"run_tests", "shell", "exec"})


def _words(value: str) -> frozenset[str]:
    normalized = "".join(character.lower() if character.isalnum() else " " for character in value)
    return frozenset(normalized.split())


def classify_operation(operation: Operation, state: ClassifierState) -> Classification:
    """Classify identical operation/state inputs identically, without model calls."""
    words = _words(f"{state.action} {operation.task_category}")
    tools = frozenset(tool.lower() for tool in operation.tool_needs)
    reasoning = [
        f"context_tokens={state.context_tokens}",
        f"prior_failures={state.prior_failures}",
        f"affected_files={state.affected_files}",
        f"tool_needs={','.join(sorted(tools)) or 'none'}",
    ]

    if operation.privacy_requirement is PrivacyRequirement.LOCAL_ONLY:
        reasoning.append("privacy requires local execution")

    if words & _TEST_TERMS and (state.prior_failures > 0 or tools & _TEST_TOOLS):
        category = OperationCategory.TEST_FAILURE_DIAGNOSIS
        rule = "test_failure_with_execution_evidence"
        confidence = 0.96
    elif words & _EDIT_TERMS or tools & _MUTATING_TOOLS:
        file_count = max(state.affected_files, len(operation.context_references))
        if file_count == 1:
            category = OperationCategory.SINGLE_FILE_EDIT
            rule = "mutating_operation_one_file"
            confidence = 0.94
        elif file_count > 1:
            category = OperationCategory.MULTI_FILE_EDIT
            rule = "mutating_operation_multiple_files"
            confidence = 0.96
        else:
            return _unknown(
                reasoning + ["mutating intent has no bounded affected-file set"],
                "unbounded_mutating_operation",
            )
    elif words & _EXPLANATION_TERMS:
        category = OperationCategory.EXPLANATION
        rule = "explanation_intent"
        confidence = 0.91
    elif words & _NAVIGATION_TERMS:
        category = OperationCategory.NAVIGATION
        rule = "repository_navigation_intent"
        confidence = 0.91
    elif words & _RETRIEVAL_TERMS:
        category = OperationCategory.RETRIEVAL
        rule = "repository_retrieval_intent"
        confidence = 0.91
    else:
        return _unknown(reasoning + ["no deterministic category rule matched"], "unknown_action")

    risk = RiskLevel.LOW
    default_backend = "local"
    if category in {OperationCategory.MULTI_FILE_EDIT, OperationCategory.TEST_FAILURE_DIAGNOSIS}:
        risk = RiskLevel.MEDIUM
    if state.context_tokens > 32_000:
        risk = RiskLevel.HIGH
        default_backend = "cloud"
        reasoning.append("context exceeds deterministic local threshold")
    if state.prior_failures >= 2:
        risk = RiskLevel.HIGH
        default_backend = "cloud"
        reasoning.append("repeated prior failures require escalation")
    if operation.estimated_difficulty >= 0.8 or operation.minimum_quality >= 0.9:
        risk = RiskLevel.HIGH
        default_backend = "cloud"
        reasoning.append("difficulty or quality threshold requires cloud by default")
    if operation.privacy_requirement is PrivacyRequirement.LOCAL_ONLY:
        default_backend = "local"

    reasoning.append(f"matched {rule}")
    return Classification(category, risk, default_backend, rule, confidence, tuple(reasoning))


def _unknown(reasoning: list[str], rule: str) -> Classification:
    reasoning.append(f"matched {rule}; unknown or unbounded work defaults to cloud")
    return Classification(
        OperationCategory.UNKNOWN_HIGH_RISK,
        RiskLevel.HIGH,
        "cloud",
        rule,
        1.0,
        tuple(reasoning),
    )
