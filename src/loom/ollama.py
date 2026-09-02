"""Streaming Ollama adapter with provider-independent events."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from loom.adapters import (
    AdapterEvent,
    AdapterRequest,
    StreamComplete,
    StreamError,
    StreamText,
    StreamToolCall,
)
from loom.contracts import (
    FinishReason,
    ModelResponse,
    StructuredError,
    Timing,
    TokenUsage,
    ToolCall,
)


class OllamaAdapter:
    backend_id = "ollama"

    def __init__(
        self,
        endpoint: str = "http://localhost:11434",
        *,
        keep_alive: str = "5m",
        client: Any | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.keep_alive = keep_alive
        self._client = client
        self._clock = clock
        self._cancelled: set[str] = set()

    async def cancel(self, request_id: str) -> None:
        self._cancelled.add(request_id)

    async def stream(self, request: AdapterRequest) -> AsyncIterator[AdapterEvent]:
        bound = request.request
        payload = {
            "model": request.model_id,
            "messages": list(bound.messages),
            "tools": list(bound.tool_schemas),
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {"num_predict": bound.max_output_tokens},
        }
        started = self._clock()
        sequence = 0
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        final: dict[str, Any] = {}
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=120)
        try:
            async with client.stream("POST", f"{self.endpoint}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if bound.request_id in self._cancelled:
                        yield StreamError(
                            bound.request_id,
                            sequence,
                            StructuredError("cancelled", "request was cancelled"),
                        )
                        return
                    if not line:
                        continue
                    chunk = json.loads(line)
                    final = chunk
                    message = chunk.get("message") or {}
                    if content := message.get("content"):
                        text_parts.append(content)
                        yield StreamText(bound.request_id, sequence, content, chunk)
                        sequence += 1
                    for index, raw_call in enumerate(message.get("tool_calls") or ()):
                        function = raw_call.get("function") or {}
                        call = ToolCall(
                            raw_call.get("id") or f"{bound.request_id}-{sequence}-{index}",
                            function.get("name", ""),
                            function.get("arguments") or {},
                        )
                        tool_calls.append(call)
                        yield StreamToolCall(bound.request_id, sequence, call, raw_call)
                        sequence += 1
        except httpx.HTTPStatusError as exc:
            category = "missing_model" if exc.response.status_code == 404 else "provider_error"
            yield StreamError(
                bound.request_id,
                sequence,
                StructuredError(
                    category,
                    str(exc),
                    exc.response.status_code >= 500,
                    str(exc.response.status_code),
                ),
            )
            return
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            yield StreamError(
                bound.request_id, sequence, StructuredError("unavailable", str(exc), True)
            )
            return
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            yield StreamError(
                bound.request_id, sequence, StructuredError("malformed_response", str(exc), False)
            )
            return
        finally:
            if own_client:
                await client.aclose()
        total_ms = (self._clock() - started) * 1000
        finish = FinishReason.TOOL_CALL if tool_calls else FinishReason.STOP
        yield StreamComplete(
            bound.request_id,
            sequence,
            ModelResponse(
                request_id=bound.request_id,
                content="".join(text_parts),
                finish_reason=finish,
                backend_id=self.backend_id,
                model_id=request.model_id,
                tool_calls=tuple(tool_calls),
                usage=TokenUsage(
                    final.get("prompt_eval_count", 0),
                    final.get("eval_count", 0),
                    raw={
                        "prompt_eval_count": final.get("prompt_eval_count"),
                        "eval_count": final.get("eval_count"),
                    },
                ),
                timing=Timing(
                    total_ms,
                    raw={
                        "total_duration_ns": final.get("total_duration"),
                        "load_duration_ns": final.get("load_duration"),
                        "prompt_eval_duration_ns": final.get("prompt_eval_duration"),
                        "eval_duration_ns": final.get("eval_duration"),
                    },
                ),
                raw={"done_reason": final.get("done_reason"), "keep_alive": self.keep_alive},
            ),
        )
