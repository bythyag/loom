"""Secret-safe local runtime preflight checks."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import httpx

from loom.config import LoomConfig


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


HttpGet = Callable[[str], object]


def _default_get(url: str) -> object:
    return httpx.get(url, timeout=1.0)


def run_doctor(
    config: LoomConfig,
    *,
    environ: dict[str, str] | None = None,
    http_get: HttpGet = _default_get,
) -> tuple[Check, ...]:
    """Return actionable checks; API-key values are deliberately never emitted."""
    environment = os.environ if environ is None else environ
    system = platform.system()
    machine = platform.machine().lower()
    disk = shutil.disk_usage(".")
    try:
        physical_memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        physical_memory = 0
    configured_mlx = config.models.mlx
    try:
        response = http_get(f"{config.endpoints.ollama}/api/version")
        ollama_ok = bool(getattr(response, "is_success", False))
        ollama_detail = "reachable" if ollama_ok else "returned non-success status"
    except (httpx.HTTPError, OSError, RuntimeError) as exc:
        ollama_ok = False
        ollama_detail = f"unreachable: {exc}"
    def package_version(name: str) -> str:
        try:
            return version(name)
        except PackageNotFoundError:
            return "not installed"
    checks = [
        Check("macos", system == "Darwin", f"detected {system} {platform.release()}"),
        Check("apple_silicon", machine in {"arm64", "aarch64"}, f"detected architecture {machine}"),
        Check("python", sys.version_info >= (3, 11), f"detected Python {platform.python_version()}"),
        Check("loom_version", package_version("loom-agent-runtime") != "not installed", package_version("loom-agent-runtime")),
        Check("processor", bool(platform.processor()), platform.processor() or "not reported"),
        Check("physical_memory", physical_memory > 0, f"{physical_memory} bytes reported"),
        Check("mlx_lm", importlib.util.find_spec("mlx_lm") is not None, "install the mlx extra if absent"),
        Check("mlx_lm_version", importlib.util.find_spec("mlx_lm") is not None, package_version("mlx-lm")),
        Check("mlx_model", bool(configured_mlx), configured_mlx or "no MLX model configured", required=False),
        Check("ollama", ollama_ok, ollama_detail, required=False),
        Check("powermetrics", shutil.which("powermetrics") is not None, "optional; never invoked without privilege", required=False),
        Check("vm_stat", shutil.which("vm_stat") is not None, "required for macOS telemetry"),
        Check("memory_pressure", shutil.which("memory_pressure") is not None, "required for memory gates"),
        Check("free_disk", disk.free > 0, f"{disk.free} bytes free"),
        Check("result_directory", Path(config.telemetry.output_directory).parent.exists(), config.telemetry.output_directory),
        Check("sysctl", shutil.which("sysctl") is not None, "required for hardware identity"),
        Check("openrouter_credential", bool(environment.get("OPENROUTER_API_KEY")), "present" if environment.get("OPENROUTER_API_KEY") else "not configured", required=False),
    ]
    return tuple(checks)


def doctor_exit_code(checks: tuple[Check, ...]) -> int:
    return 0 if all(check.ok or not check.required for check in checks) else 1
