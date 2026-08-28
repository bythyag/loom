import asyncio

from loom.adapters import AdapterRequest, StreamComplete, StreamError, StreamText
from loom.contracts import ModelRequest
from loom.mlx import MlxLmAdapter, MlxModelIdentity, MlxUnavailableError


def request() -> AdapterRequest:
    return AdapterRequest(ModelRequest("req", "op", ({"role": "user", "content": "hi"},)), "mlx/test-v1")


def test_mlx_adapter_normalizes_response_and_reuses_loaded_model() -> None:
    loads: list[str] = []
    adapter = MlxLmAdapter(
        MlxModelIdentity("org/model", "abc123", "4bit", "sha256:abc"),
        loader=lambda model: (loads.append(model) or object(), object()),
        generator=lambda *args, **kwargs: "hello",
        clock=iter((0.0, 0.2, 1.0, 1.5)).__next__,
    )

    async def consume() -> list[object]:
        return [event async for event in adapter.stream(request())]

    events = asyncio.run(consume())
    assert loads == ["org/model"]
    assert isinstance(events[0], StreamText)
    assert isinstance(events[-1], StreamComplete)
    assert events[-1].response.timing.model_load_ms == 200


def test_mlx_adapter_returns_classified_error_when_runtime_is_unavailable() -> None:
    def unavailable(_: str) -> tuple[object, object]:
        raise MlxUnavailableError("MLX-LM is not installed")

    adapter = MlxLmAdapter(
        MlxModelIdentity("org/model", "abc"),
        loader=unavailable,
        generator=lambda *_args, **_kwargs: "unused",
    )

    async def consume() -> list[object]:
        return [event async for event in adapter.stream(request())]

    events = asyncio.run(consume())
    assert isinstance(events[0], StreamError)
    assert events[0].error.category == "unavailable"


def test_release_drops_loaded_runtime() -> None:
    adapter = MlxLmAdapter(MlxModelIdentity("org/model", "abc"), loader=lambda _: (object(), object()), generator=lambda *_a, **_k: "ok")
    adapter._ensure_loaded()
    asyncio.run(adapter.release())
    assert adapter._model is None
