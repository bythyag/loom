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
