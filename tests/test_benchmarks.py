from datetime import UTC, datetime

import pytest

from loom.benchmarks import (
    BenchmarkMeasurement,
    ModelCandidate,
    run_microbenchmarks,
    screen_candidates,
)


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


def test_runner_uses_identical_cold_and_warm_workloads_and_retains_failures(tmp_path) -> None:
    calls: list[tuple[bool, str, int]] = []

    def runner(model, cold, prompt, maximum):
        calls.append((cold, prompt, maximum))
        if not cold:
            raise RuntimeError("local runtime unavailable")
        return BenchmarkMeasurement(model, cold, True, 10, 20, 30, 40, 0)

    run = run_microbenchmarks(
        "run-1", [candidate()], prompt="same prompt", max_output_tokens=42, runner=runner,
        now=lambda: datetime(2026, 8, 28, tzinfo=UTC),
    )
    assert calls == [(True, "same prompt", 42), (False, "same prompt", 42)]
    assert run.measurements[1].failure == "local runtime unavailable"
    artifact = run.write(tmp_path)
    assert '"run_id": "run-1"' in artifact.read_text()
    with pytest.raises(FileExistsError):
        run.write(tmp_path)


@pytest.mark.parametrize("run_id", ["../escape", "/absolute", "with space"])
def test_artifact_rejects_unsafe_run_ids(run_id) -> None:
    with pytest.raises(ValueError, match="safe filename"):
        run_microbenchmarks(run_id, [], prompt="prompt", max_output_tokens=1, runner=lambda *_args: None)
