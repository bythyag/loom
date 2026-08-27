from pathlib import Path

import pytest

from loom.config import ConfigError, from_mapping, load_config


def test_defaults_are_valid_and_sanitized() -> None:
    config, secrets = load_config(environ={"OPENROUTER_API_KEY": "secret"})
    assert config.schema_version == "1"
    assert config.trace_schema_version == "1"
    assert config.sanitized()["budget"]["official_usd"] == 10.0
    assert "secret" not in repr(config.sanitized())
    assert secrets == {"openrouter_api_key": "secret"}


def test_toml_and_cli_overrides_precedence(tmp_path: Path) -> None:
    path = tmp_path / "loom.toml"
    path.write_text('[limits]\nmax_steps = 12\n[models]\nollama = "qwen"\n')
    config, _ = load_config(path, overrides={"limits.max_steps": 7}, environ={})
    assert config.limits.max_steps == 7
    assert config.models.ollama == "qwen"


@pytest.mark.parametrize(
    "data",
    [
        {"surprise": True},
        {"limits": {"shell": True}},
        {"limits": {"max_steps": 0}},
        {"routing": {"max_memory_pressure": 1.1}},
        {"budget": {"warning_usd": 9, "stop_nonessential_usd": 8}},
        {"endpoints": {"ollama": "http://example.com:11434"}},
        {"endpoints": {"openrouter": "http://openrouter.ai/api/v1"}},
        {"schema_version": "999"},
    ],
)
def test_rejects_unknown_or_unsafe_values(data: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        from_mapping(data)


def test_config_cannot_contain_secret() -> None:
    with pytest.raises(ConfigError, match="unknown"):
        from_mapping({"openrouter_api_key": "must-not-live-here"})
