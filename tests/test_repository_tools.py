from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from loom.repository_tools import (
    PatchPreview,
    RepositoryToolError,
    RepositoryTools,
    disposable_copy,
)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.txt").write_text("alpha\nneedle one\nomega\n")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_text("needle two\nlast\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-qm", "base"],
        cwd=root,
        check=True,
    )
    return root


def test_list_search_and_read_are_bounded(repository: Path) -> None:
    tools = RepositoryTools(repository, max_results=2, max_bytes=30)

    listing = tools.list_files()
    assert listing.text.splitlines() == ["a.txt", "sub/b.txt"]
    assert listing.truncated

    search = tools.search_text("needle")
    assert "a.txt:2:needle one" in search.text
    assert search.returned_bytes <= 30
    assert search.truncated

    read = tools.read_file("a.txt", start_line=2, max_lines=1)
    assert read.text == "needle one"
    assert read.truncated


def test_invalid_line_and_search_limits_are_rejected(repository: Path) -> None:
    tools = RepositoryTools(repository)
    with pytest.raises(RepositoryToolError, match="query"):
        tools.search_text("")
    with pytest.raises(RepositoryToolError, match="line limits"):
        tools.read_file("a.txt", start_line=0)


@pytest.mark.parametrize("path", ["/etc/passwd", "../outside", "sub/../../outside", ""])
def test_absolute_and_traversing_paths_are_rejected(repository: Path, path: str) -> None:
    tools = RepositoryTools(repository)
    with pytest.raises(RepositoryToolError):
        tools.resolve_path(path, must_exist=False)


def test_escaping_and_dangling_symlinks_are_rejected(repository: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    (repository / "escape").symlink_to(outside)
    (repository / "dangling").symlink_to(tmp_path / "missing")
    tools = RepositoryTools(repository)
    with pytest.raises(RepositoryToolError, match="outside"):
        tools.read_file("escape")
    with pytest.raises(RepositoryToolError, match="invalid|dangling"):
        tools.read_file("dangling")


def test_internal_symlink_is_allowed(repository: Path) -> None:
    (repository / "alias").symlink_to(repository / "a.txt")
    assert RepositoryTools(repository).read_file("alias").text.startswith("alpha")


def test_patch_requires_preview_then_applies_and_preserves_diff(repository: Path) -> None:
    tools = RepositoryTools(repository)
    patch = """--- a/a.txt
+++ b/a.txt
@@ -1,3 +1,3 @@
 alpha
-needle one
+changed
 omega
"""
    preview = tools.preview_patch(patch)
    assert preview.paths == ("a.txt",)
    artifact = tools.apply_patch(preview)
    assert (repository / "a.txt").read_text() == "alpha\nchanged\nomega\n"
    assert "changed" in artifact.read_text()


def test_patch_rejects_unsafe_paths_and_tampered_preview(repository: Path) -> None:
    tools = RepositoryTools(repository)
    unsafe = "--- a/../outside\n+++ b/../outside\n@@ -0,0 +1 @@\n+x\n"
    with pytest.raises(RepositoryToolError):
        tools.preview_patch(unsafe)
    valid = (
        "--- a/a.txt\n+++ b/a.txt\n@@ -1,3 +1,3 @@\n-alpha\n+beta\n"
        " needle one\n omega\n"
    )
    with pytest.raises(RepositoryToolError, match="does not match"):
        tools.apply_patch(PatchPreview(valid, ("wrong.txt",)))


def test_only_exact_allowlisted_argv_is_executed(repository: Path) -> None:
    command = (sys.executable, "-c", "print('safe')")
    tools = RepositoryTools(repository, test_commands=[command])
    assert tools.run_test(command).output == "safe\n"
    for rejected in (
        (sys.executable, "-c", "print('different')"),
        ("sh", "-c", "echo unsafe"),
        (*command, "; echo injected"),
    ):
        with pytest.raises(RepositoryToolError, match="exact allowlisted"):
            tools.run_test(rejected)


def test_test_output_is_bounded_and_preserved(repository: Path) -> None:
    command = (sys.executable, "-c", "print('x' * 200)")
    tools = RepositoryTools(repository, test_commands=[command], max_bytes=25)
    result = tools.run_test(command)
    assert result.truncated
    assert len(result.output.encode()) == 25
    assert result.output_artifact.read_bytes() == result.output.encode()


@pytest.mark.skipif(os.name != "posix", reason="process groups require POSIX")
def test_timeout_kills_child_process_group(repository: Path) -> None:
    marker = repository / "child-survived"
    code = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',\"import time,pathlib;time.sleep(1);"
        f"pathlib.Path({str(marker)!r}).write_text('bad')\"]); time.sleep(10)"
    )
    command = (sys.executable, "-c", code)
    tools = RepositoryTools(repository, test_commands=[command], timeout_seconds=0.1)
    result = tools.run_test(command)
    assert result.timed_out
    assert result.exit_status != 0
    time.sleep(1.1)
    assert not marker.exists()


def test_disposable_copy_is_fresh_and_preserves_source(repository: Path, tmp_path: Path) -> None:
    destination = disposable_copy(repository, tmp_path)
    (destination / "a.txt").write_text("edited")
    assert (repository / "a.txt").read_text().startswith("alpha")
    assert not (destination / ".git").exists()
    assert destination.parent.parent == tmp_path
