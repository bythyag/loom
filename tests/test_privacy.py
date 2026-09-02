from loom.privacy import OMITTED, REDACTED, include_content, sanitize


def test_arbitrary_repository_content_is_omitted_by_default():
    result = sanitize({"prompt": "private question", "tool": {"file_content": "private code"}})
    assert result == {"prompt": OMITTED, "tool": {"file_content": OMITTED}}


def test_explicit_opt_in_and_official_fixtures_retain_content():
    assert sanitize({"prompt": "fixture"}, official_frozen_fixture=True)["prompt"] == "fixture"
    assert sanitize({"content": "repo"}, explicit_content_opt_in=True)["content"] == "repo"
    assert include_content(official_frozen_fixture=True)


def test_redacts_secret_fields_and_embedded_credentials():
    result = sanitize(
        {
            "api_key": "secret",
            "headers": {"Authorization": "Bearer abc.def"},
            "message": "key sk-or-v1-abcdefghijklmnop",
        }
    )
    assert result["api_key"] == REDACTED
    assert result["headers"]["Authorization"] == REDACTED
    assert REDACTED in result["message"]
    assert "abcdefghijklmnop" not in result["message"]


def test_sanitizes_user_specific_absolute_paths():
    result = sanitize(
        {"path": "/Users/alice/private/repo/file.py", "log": "at /home/bob/project/x.py"},
        home="/Users/alice",
    )
    assert result["path"] == "$HOME/private/repo/file.py"
    assert result["log"] == "at $HOME/project/x.py"


def test_recurses_without_mutating_input():
    source = {"events": [{"token": "one"}, {"message": "safe"}]}
    result = sanitize(source)
    assert result["events"][0]["token"] == REDACTED
    assert source["events"][0]["token"] == "one"
