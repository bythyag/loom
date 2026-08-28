"""Secret-safe local runtime preflight checks."""

from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from loom.config import LoomConfig


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def run_doctor(config: LoomConfig, *, environ: dict[str, str] | None = None) -> tuple[Check, ...]:
    """Return actionable checks; API-key values are deliberately never emitted."""
    environment = environ or {}
    system = platform.system()
    machine = platform.machine().lower()
    checks = [
        Check("macos", system == "Darwin", f"detected {system} {platform.release()}"),
        Check("apple_silicon", machine in {"arm64", "aarch64"}, f"detected architecture {machine}"),
        Check("python", sys.version_info >= (3, 11), f"detected Python {platform.python_version()}"),
        Check("mlx_lm", importlib.util.find_spec("mlx_lm") is not None, "install the mlx extra if absent"),
        Check("vm_stat", shutil.which("vm_stat") is not None, "required for macOS telemetry"),
        Check("memory_pressure", shutil.which("memory_pressure") is not None, "required for memory gates"),
        Check("result_directory", Path(config.telemetry.output_directory).parent.exists(), config.telemetry.output_directory),
        Check("openrouter_credential", bool(environment.get("OPENROUTER_API_KEY")), "present" if environment.get("OPENROUTER_API_KEY") else "not configured", required=False),
    ]
    return tuple(checks)


def doctor_exit_code(checks: tuple[Check, ...]) -> int:
    return 0 if all(check.ok or not check.required for check in checks) else 1
