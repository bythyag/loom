"""Human-readable local entry points for Loom."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from loom.config import ConfigError, load_config
from loom.doctor import doctor_exit_code, run_doctor

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main() -> None:
    """Loom's local runtime commands."""


@app.command()
def doctor(
    config: Annotated[Path | None, typer.Option(exists=True, readable=True)] = None,
) -> None:
    """Check the local runtime without exposing credentials."""
    try:
        resolved, _secrets = load_config(config)
    except (ConfigError, OSError) as exc:
        typer.echo(f"error: invalid configuration: {exc}", err=True)
        raise typer.Exit(2) from exc
    checks = run_doctor(resolved)
    for check in checks:
        marker = "ok" if check.ok else ("warn" if not check.required else "fail")
        typer.echo(f"{marker:4} {check.name}: {check.detail}")
    raise typer.Exit(doctor_exit_code(checks))


if __name__ == "__main__":
    app()
