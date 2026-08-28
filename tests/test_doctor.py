from loom.config import LoomConfig
from loom.doctor import Check, doctor_exit_code, run_doctor


def test_doctor_does_not_expose_openrouter_secret() -> None:
    checks = run_doctor(LoomConfig(), environ={"OPENROUTER_API_KEY": "never-print-me"})
    credential = next(check for check in checks if check.name == "openrouter_credential")
    assert credential.ok
    assert credential.detail == "present"
    assert "never-print-me" not in repr(checks)


def test_exit_code_ignores_optional_failures_only() -> None:
    assert doctor_exit_code((Check("required", True, "ok"), Check("optional", False, "off", False))) == 0
    assert doctor_exit_code((Check("required", False, "missing"),)) == 1


def test_doctor_reads_the_real_environment_by_default(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "present-but-secret")
    checks = run_doctor(LoomConfig())
    assert next(check for check in checks if check.name == "openrouter_credential").detail == "present"
