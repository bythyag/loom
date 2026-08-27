from loom.settings import SecretSettings


def test_openrouter_key_comes_from_environment(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "environment-secret")

    assert SecretSettings().openrouter_api_key == "environment-secret"


def test_openrouter_key_can_come_from_local_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=local-secret\n")

    assert SecretSettings().openrouter_api_key == "local-secret"


def test_environment_takes_precedence_over_local_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "environment-secret")
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=local-secret\n")

    assert SecretSettings().openrouter_api_key == "environment-secret"
