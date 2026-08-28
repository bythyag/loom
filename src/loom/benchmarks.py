"""Deterministic artifacts for MLX screening and backend microbenchmarks."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    backend: Literal["mlx", "ollama"]
    repository: str
    revision: str
    parameter_class: Literal["<=2b", "3b-4b", "7b-8b"]
    quantization: str
    license: str
    context_tokens: int | None = None
    template: str | None = None
    artifact_id: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkMeasurement:
    candidate: ModelCandidate
    cold: bool
    success: bool
    load_ms: float
    ttft_ms: float
    total_ms: float
    peak_memory_bytes: int
    swap_delta_bytes: int
    prompt_tokens: int = 0
    output_tokens: int = 0
    prompt_tokens_per_second: float | None = None
    generation_tokens_per_second: float | None = None
    failure: str | None = None

    def __post_init__(self) -> None:
        if any(value < 0 for value in (self.load_ms, self.ttft_ms, self.total_ms, self.peak_memory_bytes, self.swap_delta_bytes)):
            raise ValueError("benchmark measurements cannot be negative")
        if self.success and self.failure is not None:
            raise ValueError("successful benchmark results cannot carry failures")

    def manifest_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    """A reproducible microbenchmark invocation and its retained evidence."""

    run_id: str
    prompt: str
    max_output_tokens: int
    measurements: tuple[BenchmarkMeasurement, ...]
    created_at: str

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.prompt.strip() or self.max_output_tokens <= 0:
            raise ValueError("benchmark run id, prompt, and output limit must be valid")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.run_id):
            raise ValueError("benchmark run id must be a safe filename token")

    def manifest(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "prompt": self.prompt,
            "max_output_tokens": self.max_output_tokens,
            "measurements": [measurement.manifest_record() for measurement in self.measurements],
        }

    def write(self, directory: str | Path) -> Path:
        """Persist one self-contained JSON artifact; existing runs are never overwritten."""
        output = Path(directory)
        output.mkdir(parents=True, exist_ok=True)
        path = output / f"{self.run_id}.json"
        with path.open("x") as stream:
            stream.write(json.dumps(self.manifest(), indent=2, sort_keys=True) + "\n")
        return path


MeasurementRunner = Callable[[ModelCandidate, bool, str, int], BenchmarkMeasurement]


def run_microbenchmarks(
    run_id: str,
    candidates: Iterable[ModelCandidate],
    *,
    prompt: str,
    max_output_tokens: int,
    runner: MeasurementRunner,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> BenchmarkRun:
    """Run identical cold and warm workloads and retain failures as measurements."""
    measurements: list[BenchmarkMeasurement] = []
    for candidate in candidates:
        for cold in (True, False):
            try:
                result = runner(candidate, cold, prompt, max_output_tokens)
            except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                result = BenchmarkMeasurement(
                    candidate=candidate,
                    cold=cold,
                    success=False,
                    load_ms=0,
                    ttft_ms=0,
                    total_ms=0,
                    peak_memory_bytes=0,
                    swap_delta_bytes=0,
                    failure=str(exc),
                )
            if result.candidate != candidate or result.cold != cold:
                raise ValueError("benchmark runner returned a result for the wrong candidate or mode")
            measurements.append(result)
    return BenchmarkRun(run_id, prompt, max_output_tokens, tuple(measurements), now().isoformat())


def screen_candidates(results: tuple[BenchmarkMeasurement, ...], *, max_swap_bytes: int) -> tuple[BenchmarkMeasurement, ...]:
    """Return successful safe candidates; never select from model size alone."""
    return tuple(result for result in results if result.success and result.swap_delta_bytes <= max_swap_bytes)
