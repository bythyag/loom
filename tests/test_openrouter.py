import asyncio
import json

import httpx

from loom.adapters import AdapterRequest, StreamComplete, StreamError, StreamToolCall
from loom.contracts import FinishReason, ModelRequest
from loom.openrouter import OpenRouterAdapter


def request(tools=()):
    return AdapterRequest(
        ModelRequest("req", "op", ({"role": "user", "content": "hi"},), tools),
        "openai/gpt-5.1-2025-11-13",
    )


def consume(adapter, req=None):
    async def run():
        return [event async for event in adapter.stream(req or request())]

    return asyncio.run(run())


def test_official_route_disables_fallback_and_records_usage():
    def handler(req):
        body = json.loads(req.content)
        assert body["provider"] == {"order": ["openai"], "allow_fallbacks": False}
        assert req.headers["authorization"] == "Bearer secret"
        chunks = [
            {"choices": [{"delta": {"content": "ok"}, "finish_reason": None}]},
            {
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "cost": 0.01},
            },
        ]
        return httpx.Response(
            200, text="\n".join("data: " + json.dumps(x) for x in chunks) + "\ndata: [DONE]\n"
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    events = consume(
        OpenRouterAdapter(
            "secret", "openai", official=True, client=client, clock=iter((1.0, 1.1)).__next__
        )
    )
    assert isinstance(events[-1], StreamComplete)
    assert events[-1].response.usage.raw["cost"] == 0.01
    assert events[-1].response.raw["fallbacks_allowed"] is False


def test_normalizes_streamed_tool_call():
    chunks = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call",
                                "function": {"name": "search", "arguments": '{"q":'},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"x"}'}}]},
                    "finish_reason": "tool_calls",
                }
            ]
        },
    ]
    response = httpx.Response(200, text="\n".join("data: " + json.dumps(x) for x in chunks))
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response))
    events = consume(
        OpenRouterAdapter("secret", "openai", client=client),
        request(({"function": {"name": "search"}},)),
    )
    assert any(isinstance(event, StreamToolCall) for event in events)
    assert events[-1].response.finish_reason is FinishReason.TOOL_CALL


def test_classifies_auth_rate_limit_timeout_and_malformed():
    for status, category in ((401, "authentication"), (429, "rate_limit")):
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _, status=status: httpx.Response(status))
        )
        assert (
            consume(OpenRouterAdapter("secret", "openai", client=client))[0].error.category
            == category
        )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="data: nope"))
    )
    event = consume(OpenRouterAdapter("secret", "openai", client=client))[0]
    assert isinstance(event, StreamError)
    assert event.error.category == "malformed_response"


def test_requires_explicit_provider_and_key():
    for key, provider in (("", "openai"), ("secret", "")):
        try:
            OpenRouterAdapter(key, provider)
        except ValueError:
            pass
        else:
            raise AssertionError("expected invalid credentials or route")
