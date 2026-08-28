import asyncio

import pytest

from loom.adapters import AdapterRequest, StreamComplete, StreamError, StreamText
from loom.contracts import ModelRequest
from loom.mlx import MlxLmAdapter, MlxModelIdentity, MlxUnavailableError


def request() -> AdapterRequest:
    return AdapterRequest(ModelRequest("req", "op", ({"role": "user", "content": "hi"},)), "mlx/test-v1")


def test_mlx_adapter_normalizes_response_and_reuses_loaded_model() -> None:
    loads: list[str] = []
    adapter = MlxLmAdapter(
        MlxModelIdentity("org/model", "a" * 40, "4bit", "sha256:abc"),
        loader=lambda model: (loads.append(model) or object(), object()),
        generator=lambda *args, **kwargs: iter(("hel", "lo")),
        resolver=lambda identity: f"/models/{identity.revision}",
        clock=iter((0.0, 0.2, 1.0, 1.2, 1.5)).__next__,
    )

    async def consume() -> list[object]:
        return [event async for event in adapter.stream(request())]

    events = asyncio.run(consume())
    assert loads == [f"/models/{'a' * 40}"]
    assert isinstance(events[0], StreamText)
    assert isinstance(events[-1], StreamComplete)
    assert events[-1].response.timing.model_load_ms == 200
    assert events[-1].response.timing.time_to_first_token_ms == pytest.approx(200)


def test_mlx_adapter_returns_classified_error_when_runtime_is_unavailable() -> None:
    def unavailable(_: str) -> tuple[object, object]:
        raise MlxUnavailableError("MLX-LM is not installed")

    adapter = MlxLmAdapter(
        MlxModelIdentity("org/model", "a" * 40),
        loader=unavailable,
        generator=lambda *_args, **_kwargs: "unused",
        resolver=lambda _identity: "/models/abc",
    )

    async def consume() -> list[object]:
        return [event async for event in adapter.stream(request())]

    events = asyncio.run(consume())
    assert isinstance(events[0], StreamError)
    assert events[0].error.category == "unavailable"


def test_release_drops_loaded_runtime() -> None:
    adapter = MlxLmAdapter(
        MlxModelIdentity("org/model", "a" * 40),
        loader=lambda _: (object(), object()),
        generator=lambda *_a, **_k: "ok",
        resolver=lambda _identity: "/models/abc",
    )
    adapter._ensure_loaded()
    asyncio.run(adapter.release())
    assert adapter._model is None


def test_mlx_adapter_rejects_tool_requests_until_tool_calls_are_normalized() -> None:
    adapter = MlxLmAdapter(MlxModelIdentity("org/model", "a" * 40))
    request_with_tool = AdapterRequest(
        ModelRequest("req", "op", ({"role": "user", "content": "hi"},), ({"name": "search"},)),
        "mlx/test-v1",
    )

    async def consume() -> list[object]:
        return [event async for event in adapter.stream(request_with_tool)]

    events = asyncio.run(consume())
    assert isinstance(events[0], StreamError)
    assert events[0].error.category == "unsupported_output"


@pytest.mark.parametrize("revision", ["main", "v1.0", "a" * 39])
def test_mlx_identity_rejects_moving_or_non_commit_revisions(revision: str) -> None:
    with pytest.raises(ValueError, match="commit SHA"):
        MlxModelIdentity("org/model", revision)


def test_mlx_adapter_classifies_failure_during_stream_iteration() -> None:
    def broken_stream():
        yield "first"
        raise RuntimeError("device lost")

    adapter = MlxLmAdapter(
        MlxModelIdentity("org/model", "a" * 40),
        loader=lambda _path: (object(), object()),
        generator=lambda *_args, **_kwargs: broken_stream(),
        resolver=lambda _identity: "/models/pinned",
    )

    async def consume() -> list[object]:
        return [event async for event in adapter.stream(request())]

    events = asyncio.run(consume())
    assert isinstance(events[0], StreamText)
    assert isinstance(events[-1], StreamError)
    assert events[-1].error.category == "provider_error"
