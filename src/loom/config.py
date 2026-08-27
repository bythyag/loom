"""Strict, secret-free configuration for Loom runs."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

CONFIG_SCHEMA_VERSION = "1"
TRACE_SCHEMA_VERSION = "1"


class ConfigError(ValueError):
    """Raised when configuration is unknown, invalid, or unsafe."""


def _strict_keys(data: Mapping[str, Any], allowed: set[str], section: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ConfigError(f"unknown {section} option(s): {', '.join(sorted(unknown))}")


def _positive(value: float, name: str) -> None:
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero")


@dataclass(frozen=True, slots=True)
class Endpoints:
    ollama: str = "http://localhost:11434"
    openrouter: str = "https://openrouter.ai/api/v1"

    def validate(self) -> None:
        if not self.ollama.startswith("http://localhost:") and not self.ollama.startswith(
            "http://127.0.0.1:"
        ):
            raise ConfigError("endpoints.ollama must be a loopback HTTP URL")
        if not self.openrouter.startswith("https://"):
            raise ConfigError("endpoints.openrouter must use HTTPS")


@dataclass(frozen=True, slots=True)
class Models:
    ollama: str = ""
    mlx: str = ""
    openrouter: str = ""


@dataclass(frozen=True, slots=True)
class Routing:
    local_max_difficulty: float = 0.45
    cloud_min_quality: float = 0.90
    max_memory_pressure: float = 0.80
    allow_cloud_escalation: bool = True

    def validate(self) -> None:
        for name in ("local_max_difficulty", "cloud_min_quality", "max_memory_pressure"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ConfigError(f"routing.{name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Limits:
    request_timeout_seconds: float = 120.0
    tool_timeout_seconds: float = 60.0
    retries: int = 2
    max_steps: int = 20
    max_output_bytes: int = 1_000_000
    max_context_tokens: int = 32_000
    max_memory_bytes: int = 6_000_000_000

    def validate(self) -> None:
        for name in (
            "request_timeout_seconds",
            "tool_timeout_seconds",
            "max_steps",
            "max_output_bytes",
            "max_context_tokens",
            "max_memory_bytes",
        ):
            _positive(getattr(self, name), f"limits.{name}")
        if self.retries < 0:
            raise ConfigError("limits.retries must be non-negative")


@dataclass(frozen=True, slots=True)
class Tools:
    allowed: tuple[str, ...] = ("list_files", "search_text", "read_file")
    test_commands: tuple[tuple[str, ...], ...] = ()

    def validate(self) -> None:
        if any(not item or not item.strip() for item in self.allowed):
            raise ConfigError("tools.allowed cannot contain empty tool names")
        if any(not command or any(not arg for arg in command) for command in self.test_commands):
            raise ConfigError("tools.test_commands must contain non-empty argument arrays")


@dataclass(frozen=True, slots=True)
class Telemetry:
    enabled: bool = True
    include_prompts: bool = False
    output_directory: str = "results"


@dataclass(frozen=True, slots=True)
class Budget:
    official_usd: float = 10.0
    warning_usd: float = 8.0
    stop_nonessential_usd: float = 9.0

    def validate(self) -> None:
        _positive(self.official_usd, "budget.official_usd")
        if not 0 <= self.warning_usd <= self.stop_nonessential_usd <= self.official_usd:
            raise ConfigError(
                "budget thresholds must satisfy warning <= stop_nonessential <= official"
            )


@dataclass(frozen=True, slots=True)
class LoomConfig:
    schema_version: str = CONFIG_SCHEMA_VERSION
    trace_schema_version: str = TRACE_SCHEMA_VERSION
    endpoints: Endpoints = field(default_factory=Endpoints)
    models: Models = field(default_factory=Models)
    routing: Routing = field(default_factory=Routing)
    limits: Limits = field(default_factory=Limits)
    tools: Tools = field(default_factory=Tools)
    telemetry: Telemetry = field(default_factory=Telemetry)
    budget: Budget = field(default_factory=Budget)

    def validate(self) -> LoomConfig:
        if self.schema_version != CONFIG_SCHEMA_VERSION:
            raise ConfigError(f"unsupported configuration schema {self.schema_version!r}")
        if self.trace_schema_version != TRACE_SCHEMA_VERSION:
            raise ConfigError(f"unsupported trace schema {self.trace_schema_version!r}")
        self.endpoints.validate()
        self.routing.validate()
        self.limits.validate()
        self.tools.validate()
        self.budget.validate()
        return self

    def sanitized(self) -> dict[str, Any]:
        """Return the resolved, manifest-safe configuration (never credentials)."""
        return asdict(self)


_SECTIONS: dict[str, tuple[type[Any], set[str]]] = {
    "endpoints": (Endpoints, {"ollama", "openrouter"}),
    "models": (Models, {"ollama", "mlx", "openrouter"}),
    "routing": (
        Routing,
        {
            "local_max_difficulty",
            "cloud_min_quality",
            "max_memory_pressure",
            "allow_cloud_escalation",
        },
    ),
    "limits": (
        Limits,
        {
            "request_timeout_seconds", "tool_timeout_seconds", "retries", "max_steps",
            "max_output_bytes", "max_context_tokens", "max_memory_bytes",
        },
    ),
    "tools": (Tools, {"allowed", "test_commands"}),
    "telemetry": (Telemetry, {"enabled", "include_prompts", "output_directory"}),
    "budget": (Budget, {"official_usd", "warning_usd", "stop_nonessential_usd"}),
}


def from_mapping(data: Mapping[str, Any]) -> LoomConfig:
    allowed = {"schema_version", "trace_schema_version", *_SECTIONS}
    _strict_keys(data, allowed, "top-level")
    values: dict[str, Any] = {}
    for name, (model, keys) in _SECTIONS.items():
        raw = data.get(name, {})
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{name} must be a table")
        _strict_keys(raw, keys, name)
        normalized = dict(raw)
        if name == "tools":
            if "allowed" in normalized:
                normalized["allowed"] = tuple(normalized["allowed"])
            if "test_commands" in normalized:
                normalized["test_commands"] = tuple(tuple(x) for x in normalized["test_commands"])
        try:
            values[name] = model(**normalized)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"invalid {name} configuration: {exc}") from exc
    values["schema_version"] = str(data.get("schema_version", CONFIG_SCHEMA_VERSION))
    values["trace_schema_version"] = str(data.get("trace_schema_version", TRACE_SCHEMA_VERSION))
    return LoomConfig(**values).validate()


def load_config(
    path: str | Path | None = None,
    *,
    overrides: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[LoomConfig, dict[str, str]]:
    """Load TOML, apply explicit CLI-style overrides, and return env-only secrets."""
    data: dict[str, Any] = {}
    if path is not None:
        with Path(path).open("rb") as stream:
            data = tomllib.load(stream)
    config = from_mapping(data)
    for dotted, value in (overrides or {}).items():
        try:
            section, key = dotted.split(".", 1)
            model, keys = _SECTIONS[section]
        except (ValueError, KeyError) as exc:
            raise ConfigError(f"unknown override {dotted!r}") from exc
        if key not in keys:
            raise ConfigError(f"unknown override {dotted!r}")
        current = getattr(config, section)
        updated = replace(current, **{key: value})
        if not isinstance(updated, model):  # defensive: replace preserves type
            raise ConfigError(f"invalid override {dotted!r}")
        config = replace(config, **{section: updated}).validate()
    source = os.environ if environ is None else environ
    secrets = {}
    if value := source.get("OPENROUTER_API_KEY"):
        secrets["openrouter_api_key"] = value
    return config, secrets
