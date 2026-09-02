import asyncio
import json

import httpx

from loom.adapters import AdapterRequest, StreamComplete, StreamError, StreamText, StreamToolCall
from loom.contracts import FinishReason, ModelRequest
from loom.ollama import OllamaAdapter


def req(tools=()):
    return AdapterRequest(
        ModelRequest("req", "op", ({"role": "user", "content": "hi"},), tools), "qwen2.5:1.5b"
    )


def consume(adapter, request):
    async def run():
        return [event async for event in adapter.stream(request)]

    return asyncio.run(run())


def client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_streams_text_usage_and_timings():
    def handler(request):
        assert json.loads(request.content)["keep_alive"] == "0"
        body = "\n".join(
            (
                json.dumps({"message": {"content": "hi"}, "done": False}),
                json.dumps(
                    {
                        "message": {"content": "!"},
                        "done": True,
                        "prompt_eval_count": 2,
                        "eval_count": 1,
                        "total_duration": 9,
                        "load_duration": 2,
                    }
                ),
            )
        )
        return httpx.Response(200, text=body)

    events = consume(
        OllamaAdapter(keep_alive="0", client=client(handler), clock=iter((1.0, 1.2)).__next__),
        req(),
    )
    assert [e.text for e in events if isinstance(e, StreamText)] == ["hi", "!"]
    assert isinstance(events[-1], StreamComplete)
    assert events[-1].response.usage.input_tokens == 2


def test_normalizes_tool_calls():
    body = json.dumps(
        {
            "message": {"tool_calls": [{"function": {"name": "search", "arguments": {"q": "x"}}}]},
            "done": True,
        }
    )
    events = consume(
        OllamaAdapter(client=client(lambda _: httpx.Response(200, text=body))),
        req(({"function": {"name": "search"}},)),
    )
    assert isinstance(events[0], StreamToolCall)
    assert events[-1].response.finish_reason is FinishReason.TOOL_CALL


def test_classifies_missing_model_and_unavailable():
    events = consume(
        OllamaAdapter(client=client(lambda _: httpx.Response(404, text="missing"))), req()
    )
    assert isinstance(events[0], StreamError)
    assert events[0].error.category == "missing_model"

    def unavailable(_):
        raise httpx.ConnectError("offline")

    events = consume(OllamaAdapter(client=client(unavailable)), req())
    assert events[0].error.category == "unavailable"
