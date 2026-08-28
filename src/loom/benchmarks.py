"""Deterministic artifacts for MLX screening and backend microbenchmarks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    backend: Literal["mlx", "ollama"]
    repository: str
    revision: str
    parameter_class: Literal["<=2b", "3b-4b", "7b-8b"]
    quantization: str
    license: str


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
    failure: str | None = None

    def __post_init__(self) -> None:
        if any(value < 0 for value in (self.load_ms, self.ttft_ms, self.total_ms, self.peak_memory_bytes, self.swap_delta_bytes)):
            raise ValueError("benchmark measurements cannot be negative")
        if self.success and self.failure is not None:
            raise ValueError("successful benchmark results cannot carry failures")

    def manifest_record(self) -> dict[str, object]:
        return asdict(self)


def screen_candidates(results: tuple[BenchmarkMeasurement, ...], *, max_swap_bytes: int) -> tuple[BenchmarkMeasurement, ...]:
    """Return successful safe candidates; never select from model size alone."""
    return tuple(result for result in results if result.success and result.swap_delta_bytes <= max_swap_bytes)
