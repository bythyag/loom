"""MLX-LM adapter with an import-safe, testable boundary.

MLX is optional in Loom.  Nothing imports it until a caller creates the
adapter, which keeps non-Apple CI and ``loom doctor`` useful.
"""

from __future__ import annotations

import importlib
import re
import time
from collections.abc import AsyncIterator, Callable, Iterable
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
        if not re.fullmatch(r"[0-9a-fA-F]{40}", self.revision):
            raise ValueError("MLX model revision must be a 40-character immutable commit SHA")


class MlxUnavailableError(RuntimeError):
    """MLX-LM was not installed on the current machine."""


Loader = Callable[[str], tuple[Any, Any]]
Generator = Callable[..., Any]
Resolver = Callable[[MlxModelIdentity], str]


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
        resolver: Resolver | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.identity = identity
        self._loader = loader
        self._generator = generator
        self._resolver = resolver or _resolve_snapshot
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
        return runtime.load, runtime.stream_generate

    def _ensure_loaded(self) -> float:
        if self._model is not None:
            return 0.0
        loader, _ = self._runtime()
        started = self._clock()
        self._model, self._tokenizer = loader(self._resolver(self.identity))
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
        if bound.tool_schemas:
            yield StreamError(
                bound.request_id,
                0,
                StructuredError(
                    "unsupported_output",
                    "MLX-LM tool-call normalization is not implemented for this model",
                    False,
                ),
            )
            return
        try:
            load_ms = self._ensure_loaded()
            _, generator = self._runtime()
            started = self._clock()
            output = generator(
                self._model,
                self._tokenizer,
                prompt=self._prompt(bound.messages),
                max_tokens=bound.max_output_tokens or 256,
            )
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
        chunks = (output,) if isinstance(output, str) else output
        if not isinstance(chunks, Iterable):
            yield StreamError(bound.request_id, 0, StructuredError("provider_error", "MLX returned a non-stream output", True))
            return
        text_parts: list[str] = []
        first_token_ms: float | None = None
        sequence = 0
        try:
            for chunk in chunks:
                text = str(getattr(chunk, "text", chunk))
                if not text:
                    continue
                if first_token_ms is None:
                    first_token_ms = (self._clock() - started) * 1000
                text_parts.append(text)
                yield StreamText(bound.request_id, sequence, text)
                sequence += 1
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            yield StreamError(
                bound.request_id,
                sequence,
                StructuredError("provider_error", str(exc), True),
            )
            return
        text = "".join(text_parts)
        total_ms = (self._clock() - started) * 1000
        yield StreamComplete(
            bound.request_id,
            sequence,
            ModelResponse(
                request_id=bound.request_id,
                content=text,
                finish_reason=FinishReason.STOP,
                backend_id=self.backend_id,
                model_id=self.identity.repository + "@" + self.identity.revision,
                usage=TokenUsage(
                    input_tokens=len(self._prompt(bound.messages).split()),
                    output_tokens=len(text.split()),
                    source="estimated",
                ),
                timing=Timing(
                    total_ms=total_ms,
                    time_to_first_token_ms=first_token_ms,
                    model_load_ms=load_ms,
                    raw={"generation_ms": max(0.0, total_ms - (first_token_ms or total_ms))},
                ),
                raw={"identity": {"repository": self.identity.repository, "revision": self.identity.revision, "quantization": self.identity.quantization, "artifact_id": self.identity.artifact_id}},
            ),
        )


def _resolve_snapshot(identity: MlxModelIdentity) -> str:
    """Resolve one immutable Hub revision before MLX receives a local path."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise MlxUnavailableError("huggingface_hub is required to resolve a pinned MLX model") from exc
    return snapshot_download(repo_id=identity.repository, revision=identity.revision)
