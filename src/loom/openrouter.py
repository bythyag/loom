"""Pinned OpenRouter adapter; credentials are accepted but never retained in results."""

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


class OpenRouterAdapter:
    backend_id = "openrouter"

    def __init__(
        self,
        api_key: str,
        provider: str,
        *,
        endpoint: str = "https://openrouter.ai/api/v1",
        official: bool = False,
        client: Any | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if not api_key.strip() or not provider.strip():
            raise ValueError("OpenRouter API key and pinned provider are required")
        self._api_key = api_key
        self.provider = provider
        self.endpoint = endpoint.rstrip("/")
        self.official = official
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
            "usage": {"include": True},
            "provider": {"order": [self.provider], "allow_fallbacks": not self.official},
        }
        started = self._clock()
        sequence = 0
        parts: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        finish_reason = "stop"
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=120)
        try:
            async with client.stream(
                "POST",
                f"{self.endpoint}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if bound.request_id in self._cancelled:
                        yield StreamError(
                            bound.request_id,
                            sequence,
                            StructuredError("cancelled", "request was cancelled"),
                        )
                        return
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    chunk = json.loads(line[6:])
                    usage.update(chunk.get("usage") or {})
                    choice = (chunk.get("choices") or [{}])[0]
                    finish_reason = choice.get("finish_reason") or finish_reason
                    delta = choice.get("delta") or {}
                    if content := delta.get("content"):
                        parts.append(content)
                        yield StreamText(bound.request_id, sequence, content, chunk)
                        sequence += 1
                    for raw in delta.get("tool_calls") or ():
                        slot = calls.setdefault(
                            raw.get("index", 0), {"id": "", "name": "", "arguments": ""}
                        )
                        slot["id"] += raw.get("id") or ""
                        fn = raw.get("function") or {}
                        slot["name"] += fn.get("name") or ""
                        slot["arguments"] += fn.get("arguments") or ""
        except httpx.HTTPStatusError as exc:
            categories = {401: "authentication", 402: "budget", 429: "rate_limit"}
            category = categories.get(exc.response.status_code, "provider_error")
            yield StreamError(
                bound.request_id,
                sequence,
                StructuredError(
                    category,
                    str(exc),
                    exc.response.status_code in {408, 429} or exc.response.status_code >= 500,
                    str(exc.response.status_code),
                ),
            )
            return
        except httpx.TimeoutException as exc:
            yield StreamError(
                bound.request_id, sequence, StructuredError("timeout", str(exc), True)
            )
            return
        except httpx.ConnectError as exc:
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
        normalized_calls: list[ToolCall] = []
        try:
            for index, item in sorted(calls.items()):
                call = ToolCall(
                    item["id"] or f"{bound.request_id}-{index}",
                    item["name"],
                    json.loads(item["arguments"] or "{}"),
                )
                normalized_calls.append(call)
                yield StreamToolCall(bound.request_id, sequence, call, item)
                sequence += 1
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            yield StreamError(
                bound.request_id,
                sequence,
                StructuredError("malformed_response", f"invalid tool call: {exc}"),
            )
            return
        mapped_finish = (
            FinishReason.TOOL_CALL
            if normalized_calls
            else (FinishReason.LENGTH if finish_reason == "length" else FinishReason.STOP)
        )
        yield StreamComplete(
            bound.request_id,
            sequence,
            ModelResponse(
                request_id=bound.request_id,
                content="".join(parts),
                finish_reason=mapped_finish,
                backend_id=self.backend_id,
                model_id=request.model_id,
                tool_calls=tuple(normalized_calls),
                usage=TokenUsage(
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    raw={
                        "reasoning_tokens": usage.get("reasoning_tokens"),
                        "cached_tokens": usage.get("prompt_tokens_details", {}).get(
                            "cached_tokens"
                        ),
                        "cost": usage.get("cost"),
                    },
                ),
                timing=Timing((self._clock() - started) * 1000),
                raw={"provider": self.provider, "fallbacks_allowed": not self.official},
            ),
        )
