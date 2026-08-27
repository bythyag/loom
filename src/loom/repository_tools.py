"""Bounded, path-safe tools for repository agent runs.

All caller supplied paths are repository-relative.  Commands are immutable argv
arrays selected from configuration; shell parsing is never involved.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class RepositoryToolError(ValueError):
    """A repository operation was invalid or unsafe."""


@dataclass(frozen=True, slots=True)
class TextResult:
    text: str
    truncated: bool
    matched_items: int
    returned_bytes: int


@dataclass(frozen=True, slots=True)
class CommandResult:
    argv: tuple[str, ...]
    exit_status: int
    output: str
    timed_out: bool
    truncated: bool
    duration_seconds: float
    output_artifact: Path


@dataclass(frozen=True, slots=True)
class PatchPreview:
    patch: str
    paths: tuple[str, ...]


def disposable_copy(source: str | Path, destination_parent: str | Path) -> Path:
    """Create a fresh fixture copy, excluding VCS and prior run artifacts."""
    source_path = Path(source).resolve(strict=True)
    if not source_path.is_dir():
        raise RepositoryToolError("fixture source must be a directory")
    parent = Path(destination_parent).resolve(strict=True)
    destination = Path(tempfile.mkdtemp(prefix="loom-fixture-", dir=parent)) / "repo"
    shutil.copytree(
        source_path,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git", ".loom-artifacts"),
    )
    return destination


class RepositoryTools:
    """Perform bounded operations inside one canonical repository root."""

    def __init__(
        self,
        root: str | Path,
        *,
        test_commands: Iterable[Iterable[str]] = (),
        max_results: int = 200,
        max_bytes: int = 1_000_000,
        timeout_seconds: float = 60.0,
        artifacts_directory: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise RepositoryToolError("repository root must be a directory")
        if max_results <= 0 or max_bytes <= 0 or timeout_seconds <= 0:
            raise RepositoryToolError("limits must be greater than zero")
        self.max_results = max_results
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds
        self.test_commands = tuple(tuple(command) for command in test_commands)
        if any(not command or any(not isinstance(arg, str) or not arg for arg in command)
               for command in self.test_commands):
            raise RepositoryToolError("test allowlist must contain non-empty argv arrays")
        artifact_path = artifacts_directory or self.root / ".loom-artifacts"
        self.artifacts = Path(artifact_path).resolve()
        self.artifacts.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, relative: str | Path, *, must_exist: bool = True) -> Path:
        raw = os.fspath(relative)
        candidate_path = Path(raw)
        if not raw or candidate_path.is_absolute():
            raise RepositoryToolError("path must be non-empty and repository-relative")
        parts = PurePosixPath(raw.replace(os.sep, "/")).parts
        if ".." in parts:
            raise RepositoryToolError("path traversal is not allowed")
        candidate = self.root.joinpath(*parts)
        try:
            resolved = candidate.resolve(strict=must_exist)
        except (FileNotFoundError, RuntimeError) as exc:
            raise RepositoryToolError(f"invalid repository path: {raw}") from exc
        if not resolved.is_relative_to(self.root):
            raise RepositoryToolError("path resolves outside the repository")
        # Existing parent symlinks are resolved above. This explicit walk makes
        # dangling and escaping symlinks fail even for not-yet-created leaves.
        current = self.root
        for part in parts:
            current = current / part
            if current.is_symlink():
                try:
                    target = current.resolve(strict=True)
                except (FileNotFoundError, RuntimeError) as exc:
                    raise RepositoryToolError("dangling symlink is not allowed") from exc
                if not target.is_relative_to(self.root):
                    raise RepositoryToolError("symlink resolves outside the repository")
        return resolved

    def list_files(self, relative: str | Path = ".") -> TextResult:
        base = self.resolve_path(relative)
        if not base.is_dir():
            raise RepositoryToolError("list path must be a directory")
        entries: list[str] = []
        truncated = False
        for directory, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames[:] = [name for name in dirnames if name not in {".git", ".loom-artifacts"}]
            dirnames.sort()
            filenames.sort()
            for name in filenames:
                path = Path(directory, name)
                self.resolve_path(path.relative_to(self.root))
                entries.append(path.relative_to(self.root).as_posix())
                if len(entries) >= self.max_results:
                    truncated = True
                    break
            if truncated:
                break
        return self._bounded_lines(entries, truncated=truncated)

    def search_text(self, query: str, relative: str | Path = ".") -> TextResult:
        if not query:
            raise RepositoryToolError("search query must not be empty")
        base = self.resolve_path(relative)
        paths = [base] if base.is_file() else self._walk_files(base)
        matches: list[str] = []
        truncated = False
        for path in paths:
            safe_path = self.resolve_path(path.relative_to(self.root))
            if not safe_path.is_file():
                continue
            try:
                with safe_path.open("r", encoding="utf-8") as stream:
                    for number, line in enumerate(stream, 1):
                        if query in line:
                            matches.append(
                                f"{safe_path.relative_to(self.root).as_posix()}:{number}:{line.rstrip()}"
                            )
                            if len(matches) >= self.max_results:
                                truncated = True
                                break
            except UnicodeDecodeError:
                continue
            if truncated:
                break
        return self._bounded_lines(matches, truncated=truncated)

    def read_file(
        self, relative: str | Path, *, start_line: int = 1, max_lines: int | None = None
    ) -> TextResult:
        if start_line <= 0 or (max_lines is not None and max_lines <= 0):
            raise RepositoryToolError("line limits must be greater than zero")
        path = self.resolve_path(relative)
        if not path.is_file():
            raise RepositoryToolError("read path must be a file")
        line_limit = min(max_lines or self.max_results, self.max_results)
        selected: list[str] = []
        more = False
        try:
            with path.open("r", encoding="utf-8") as stream:
                for number, line in enumerate(stream, 1):
                    if number < start_line:
                        continue
                    if len(selected) == line_limit:
                        more = True
                        break
                    selected.append(line.rstrip("\n"))
        except UnicodeDecodeError as exc:
            raise RepositoryToolError("file is not valid UTF-8 text") from exc
        return self._bounded_lines(selected, truncated=more)

    def preview_patch(self, patch: str) -> PatchPreview:
        if not patch or len(patch.encode()) > self.max_bytes:
            raise RepositoryToolError("patch is empty or exceeds the byte limit")
        paths: list[str] = []
        for line in patch.splitlines():
            if line.startswith(("--- ", "+++ ")):
                token = line[4:].split("\t", 1)[0]
                if token == "/dev/null":
                    continue
                if not token.startswith(("a/", "b/")):
                    raise RepositoryToolError("patch paths must use a/ and b/ prefixes")
                relative = token[2:]
                self.resolve_path(relative, must_exist=False)
                paths.append(relative)
        if not paths:
            raise RepositoryToolError("patch contains no file paths")
        check = subprocess.run(
            ["git", "apply", "--check", "--", "-"],
            cwd=self.root,
            input=patch,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if check.returncode:
            raise RepositoryToolError(f"patch does not apply: {check.stderr.strip()}")
        return PatchPreview(patch=patch, paths=tuple(dict.fromkeys(paths)))

    def apply_patch(self, preview: PatchPreview) -> Path:
        # Re-preview at apply time to prevent stale or constructed previews.
        verified = self.preview_patch(preview.patch)
        if verified.paths != preview.paths:
            raise RepositoryToolError("patch preview does not match patch content")
        applied = subprocess.run(
            ["git", "apply", "--", "-"], cwd=self.root, input=preview.patch,
            text=True, capture_output=True, timeout=self.timeout_seconds, check=False,
        )
        if applied.returncode:
            raise RepositoryToolError(f"patch failed: {applied.stderr.strip()}")
        # The validated input is the exact diff applied, including newly-created
        # files (which plain ``git diff`` omits while they are untracked).
        artifact = self._artifact("final.diff", verified.patch.encode())
        return artifact

    def run_test(self, argv: Iterable[str]) -> CommandResult:
        command = tuple(argv)
        if command not in self.test_commands:
            raise RepositoryToolError("test command is not an exact allowlisted argv array")
        started = time.monotonic()
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(
                command, cwd=self.root, stdin=subprocess.DEVNULL, stdout=output,
                stderr=subprocess.STDOUT, start_new_session=True,
            )
            timed_out = False
            try:
                process.wait(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=min(1.0, self.timeout_seconds))
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            size = output.tell()
            output.seek(0)
            captured = output.read(self.max_bytes)
        artifact = self._artifact("test-output.txt", captured)
        return CommandResult(
            argv=command, exit_status=process.returncode, output=captured.decode("utf-8", "replace"),
            timed_out=timed_out, truncated=size > self.max_bytes,
            duration_seconds=time.monotonic() - started, output_artifact=artifact,
        )

    def _bounded_lines(self, lines: list[str], *, truncated: bool) -> TextResult:
        encoded = "\n".join(lines).encode()
        if len(encoded) > self.max_bytes:
            encoded = encoded[: self.max_bytes]
            truncated = True
        text = encoded.decode("utf-8", "ignore")
        return TextResult(text, truncated, len(lines), len(text.encode()))

    @staticmethod
    def _walk_files(base: Path) -> Iterable[Path]:
        for directory, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames[:] = [name for name in dirnames if name not in {".git", ".loom-artifacts"}]
            dirnames.sort()
            for name in sorted(filenames):
                yield Path(directory, name)

    def _artifact(self, name: str, content: bytes) -> Path:
        path = self.artifacts / name
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
        return path
