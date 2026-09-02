from typer.testing import CliRunner

from loom.cli import app


def test_doctor_command_never_prints_secret(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "do-not-print")
    result = CliRunner().invoke(app, ["doctor"])
    assert "openrouter_credential: present" in result.output
    assert "do-not-print" not in result.output
    assert result.exit_code in {0, 1}


def test_doctor_rejects_invalid_configuration(tmp_path) -> None:
    config = tmp_path / "invalid.toml"
    config.write_text("[routing]\nlocal_max_difficulty = 2\n")
    result = CliRunner().invoke(app, ["doctor", "--config", str(config)])
    assert result.exit_code == 2
    assert "invalid configuration" in result.output


def test_doctor_rejects_malformed_toml(tmp_path) -> None:
    config = tmp_path / "invalid.toml"
    config.write_text("[routing\n")
    result = CliRunner().invoke(app, ["doctor", "--config", str(config)])
    assert result.exit_code == 2
    assert "invalid configuration" in result.output


def test_agent_creates_run_and_prints_identity(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    result = CliRunner().invoke(
        app, ["agent", "--repo", str(repo), "--task", "inspect", "--output-root", str(tmp_path / "runs")]
    )
    assert result.exit_code == 0
    assert "run_id: agent-" in result.output
    assert "output_directory:" in result.output
    assert len(list((tmp_path / "runs").iterdir())) == 1


def test_benchmark_validates_suite_and_repeat(tmp_path) -> None:
    result = CliRunner().invoke(app, ["benchmark", "--suite", "future"])
    assert result.exit_code == 2
    result = CliRunner().invoke(app, ["benchmark", "--repeat", "0"])
    assert result.exit_code == 2


def test_report_prints_existing_run(tmp_path) -> None:
    run = tmp_path / "run-1"
    run.mkdir()
    result = CliRunner().invoke(app, ["report", str(run)])
    assert result.exit_code == 0
    assert "run_id: run-1" in result.output
