import pytest

from loom.benchmarks import BenchmarkMeasurement, ModelCandidate, screen_candidates


def candidate() -> ModelCandidate:
    return ModelCandidate("mlx", "org/model", "abc123", "<=2b", "4bit", "Apache-2.0")


def test_screening_requires_success_and_safe_swap() -> None:
    safe = BenchmarkMeasurement(candidate(), True, True, 100, 25, 200, 1000, 20)
    unsafe = BenchmarkMeasurement(candidate(), False, True, 0, 25, 100, 1000, 21)
    failed = BenchmarkMeasurement(candidate(), True, False, 100, 25, 200, 1000, 0, failure="timeout")
    assert screen_candidates((safe, unsafe, failed), max_swap_bytes=20) == (safe,)
    assert safe.manifest_record()["candidate"]["revision"] == "abc123"


def test_successful_measurement_cannot_include_failure() -> None:
    with pytest.raises(ValueError, match="cannot carry"):
        BenchmarkMeasurement(candidate(), True, True, 1, 1, 1, 1, 1, failure="no")
