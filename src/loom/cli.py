"""Human-readable local entry points for Loom."""

from __future__ import annotations

import tomllib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import typer

from loom.config import ConfigError, load_config
from loom.doctor import doctor_exit_code, run_doctor

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _new_run(output_root: Path, kind: str) -> tuple[str, Path]:
    run_id = f"{kind}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    output = output_root / run_id
    output.mkdir(parents=True, exist_ok=False)
    return run_id, output


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
    except (ConfigError, OSError, tomllib.TOMLDecodeError) as exc:
        typer.echo(f"error: invalid configuration: {exc}", err=True)
        raise typer.Exit(2) from exc
    checks = run_doctor(resolved)
    for check in checks:
        marker = "ok" if check.ok else ("warn" if not check.required else "fail")
        typer.echo(f"{marker:4} {check.name}: {check.detail}")
    raise typer.Exit(doctor_exit_code(checks))


@app.command("agent")
def agent_command(
    repo: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
    task: Annotated[str, typer.Option(help="Task text; may be sent to the selected model.")],
    mode: Annotated[Literal["cloud", "ollama", "mlx", "loom"], typer.Option()] = "loom",
    output_root: Annotated[Path, typer.Option(help="Creates a run directory here.")] = Path(
        "results"
    ),
) -> None:
    """Create a bounded agent run (models may run and repository files may change)."""
    if not task.strip():
        raise typer.BadParameter("task must not be empty", param_hint="--task")
    run_id, output = _new_run(output_root, "agent")
    typer.echo(f"run_id: {run_id}")
    typer.echo(f"output_directory: {output}")
    typer.echo(f"prepared {mode} agent run for {repo.resolve()}")


@app.command("benchmark")
def benchmark_command(
    suite: Annotated[str, typer.Option()] = "v0.1",
    mode: Annotated[Literal["cloud", "ollama", "mlx", "loom"], typer.Option()] = "loom",
    repeat: Annotated[int, typer.Option(min=1)] = 1,
    output_root: Annotated[Path, typer.Option(help="Creates benchmark artifacts here.")] = Path(
        "results"
    ),
) -> None:
    """Create a benchmark run (may invoke models and incur cloud charges)."""
    if suite != "v0.1":
        raise typer.BadParameter("only suite v0.1 is supported", param_hint="--suite")
    run_id, output = _new_run(output_root, "benchmark")
    typer.echo(f"run_id: {run_id}")
    typer.echo(f"output_directory: {output}")
    typer.echo(f"prepared {mode} benchmark with {repeat} repetition(s)")


@app.command("report")
def report_command(
    run_directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
) -> None:
    """Inspect an existing run directory; does not invoke models or modify repositories."""
    typer.echo(f"run_id: {run_directory.name}")
    typer.echo(f"output_directory: {run_directory.resolve()}")


if __name__ == "__main__":
    app()
