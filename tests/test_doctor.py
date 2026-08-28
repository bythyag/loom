from loom.config import LoomConfig, Models
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


def test_doctor_records_ollama_reachability_without_raising() -> None:
    class Response:
        is_success = True

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def get(url):
        return Response({"version": "0.9"} if url.endswith("version") else {"models": [{"name": "qwen:1.5b"}]})

    checks = run_doctor(LoomConfig(), environ={}, http_get=get)
    assert next(check for check in checks if check.name == "ollama").ok
    assert "version 0.9" in next(check for check in checks if check.name == "ollama").detail


def test_doctor_requires_configured_ollama_model_to_be_installed() -> None:
    class Response:
        is_success = True

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    calls = 0

    def get(_url):
        nonlocal calls
        calls += 1
        return Response({"version": "0.9"} if calls == 1 else {"models": []})

    checks = run_doctor(LoomConfig(models=Models(ollama="missing:1")), environ={}, http_get=get)
    model = next(check for check in checks if check.name == "ollama_model")
    assert not model.ok
    assert model.required


def test_doctor_does_not_accept_a_model_when_ollama_version_check_fails() -> None:
    class Response:
        is_success = False

        def json(self):
            return {"models": [{"name": "present:1"}]}

    checks = run_doctor(
        LoomConfig(models=Models(ollama="present:1")), environ={}, http_get=lambda _url: Response()
    )
    model = next(check for check in checks if check.name == "ollama_model")
    assert not model.ok
