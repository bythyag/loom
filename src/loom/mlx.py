"""MLX-LM adapter with an import-safe, testable boundary.

MLX is optional in Loom.  Nothing imports it until a caller creates the
adapter, which keeps non-Apple CI and ``loom doctor`` useful.
"""

from __future__ import annotations

import asyncio
import importlib
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from loom.adapters import AdapterEvent, AdapterRequest, StreamComplete, StreamError, StreamText
from loom.contracts import FinishReason, ModelResponse, StructuredError, Timing, TokenUsage


@dataclass(frozen=True, slots=True)
class MlxModelIdentity:
    """Immutable model information recorded beside every MLX result."""

    repository: str
    revision: str
    quantization: str | None = None
    artifact_id: str | None = None

    def __post_init__(self) -> None:
        if not self.repository.strip() or not self.revision.strip():
            raise ValueError("MLX model repository and revision must be non-empty")


class MlxUnavailableError(RuntimeError):
    """MLX-LM was not installed on the current machine."""


Loader = Callable[[str], tuple[Any, Any]]
Generator = Callable[..., Any]


class MlxLmAdapter:
    """Normalize a non-streaming ``mlx_lm.generate`` response into Loom events.

    ``loader`` and ``generator`` make the provider boundary deterministic in
    tests and let production import the optional package only when needed.
    """

    backend_id = "mlx-lm"

    def __init__(
        self,
        identity: MlxModelIdentity,
        *,
        loader: Loader | None = None,
        generator: Generator | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.identity = identity
        self._loader = loader
        self._generator = generator
        self._clock = clock
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._cancelled: set[str] = set()

    def _runtime(self) -> tuple[Loader, Generator]:
        if self._loader is not None and self._generator is not None:
            return self._loader, self._generator
        try:
            runtime = importlib.import_module("mlx_lm")
        except ImportError as exc:
            raise MlxUnavailableError(
                "MLX-LM is not installed; install Loom with the 'mlx' extra on Apple Silicon"
            ) from exc
        return runtime.load, runtime.generate

    def _ensure_loaded(self) -> float:
        if self._model is not None:
            return 0.0
        loader, _ = self._runtime()
        started = self._clock()
        self._model, self._tokenizer = loader(self.identity.repository)
        return (self._clock() - started) * 1000

    @staticmethod
    def _prompt(messages: tuple[dict[str, Any], ...]) -> str:
        return "\n".join(f"{message.get('role', 'user')}: {message.get('content', '')}" for message in messages)

    async def cancel(self, request_id: str) -> None:
        self._cancelled.add(request_id)

    async def release(self) -> None:
        """Drop Loom's references so MLX can reclaim model memory when eligible."""
        self._model = None
        self._tokenizer = None

    async def stream(self, request: AdapterRequest) -> AsyncIterator[AdapterEvent]:
        bound = request.request
        if bound.request_id in self._cancelled:
            yield StreamError(bound.request_id, 0, StructuredError("cancelled", "request was cancelled"))
            return
        try:
            load_ms = self._ensure_loaded()
            _, generator = self._runtime()
            started = self._clock()
            output = await asyncio.to_thread(
                generator,
                self._model,
                self._tokenizer,
                prompt=self._prompt(bound.messages),
                max_tokens=bound.max_output_tokens or 256,
            )
            total_ms = (self._clock() - started) * 1000
        except MlxUnavailableError as exc:
            yield StreamError(bound.request_id, 0, StructuredError("unavailable", str(exc), False))
            return
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            # Provider failures are represented inside the common contract.
            yield StreamError(bound.request_id, 0, StructuredError("provider_error", str(exc), True))
            return
        if bound.request_id in self._cancelled:
            yield StreamError(bound.request_id, 0, StructuredError("cancelled", "request was cancelled"))
            return
        text = str(output)
        if text:
            yield StreamText(bound.request_id, 0, text)
        yield StreamComplete(
            bound.request_id,
            1,
            ModelResponse(
                request_id=bound.request_id,
                content=text,
                finish_reason=FinishReason.STOP,
                backend_id=self.backend_id,
                model_id=self.identity.repository + "@" + self.identity.revision,
                usage=TokenUsage(source="estimated"),
                timing=Timing(total_ms=total_ms, model_load_ms=load_ms),
                raw={"identity": self.identity.__dict__ if hasattr(self.identity, "__dict__") else {"repository": self.identity.repository, "revision": self.identity.revision, "quantization": self.identity.quantization, "artifact_id": self.identity.artifact_id}},
            ),
        )
