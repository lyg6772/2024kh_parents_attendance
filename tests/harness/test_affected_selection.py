"""Golden tests for scripts/test_affected.sh — the inner-loop test selector.

The script must be an accelerator, never a weaker gate: every uncertain path
falls back to the full suite. Stub `pytest`/`codegraph` binaries capture what
would run. The index tool is a pluggable seam (INDEX_MARKER / INDEX_SYNC_CMD /
AFFECTED_TESTS_CMD) with codegraph defaults.
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .conftest import HarnessRepo

from .conftest import BASE_PATH

PYTEST_STUB = '#!/bin/sh\necho "PYTEST_ARGS:$*"\n'
CODEGRAPH_STUB = """#!/bin/sh
case "$1" in
  sync) exit 0 ;;
  affected) cat >/dev/null; printf 'tests/test_user.py\\n' ;;
esac
"""


def _stub_path(repo: "HarnessRepo", with_codegraph: bool) -> dict[str, str]:
    stub_dir = repo.path / "stubs"
    stub_dir.mkdir(exist_ok=True)
    binaries = {"pytest": PYTEST_STUB}
    if with_codegraph:
        binaries["codegraph"] = CODEGRAPH_STUB
    for name, content in binaries.items():
        target = stub_dir / name
        target.write_text(content)
        target.chmod(0o755)
    return {"PATH": f"{stub_dir}:{BASE_PATH}"}


def _index(repo: "HarnessRepo") -> None:
    marker = repo.path / ".codegraph" / "codegraph.db"
    marker.parent.mkdir(exist_ok=True)
    marker.write_text("db")


def test_without_index_falls_back_to_full_suite(repo: "HarnessRepo") -> None:
    repo.write("app/services/user.py", "def existing() -> None: ...\ndef added(): ...\n")
    result = repo.run_script("test_affected.sh", env=_stub_path(repo, with_codegraph=False))
    assert result.returncode == 0
    assert "PYTEST_ARGS:-q --ignore=tests/harness" in result.stdout
    assert "no code index" in result.stderr


def test_marker_dir_without_db_still_falls_back(repo: "HarnessRepo") -> None:
    (repo.path / ".codegraph").mkdir()
    repo.write("app/services/user.py", "def existing() -> None: ...\ndef added(): ...\n")
    result = repo.run_script("test_affected.sh", env=_stub_path(repo, with_codegraph=True))
    assert result.returncode == 0
    assert "PYTEST_ARGS:-q --ignore=tests/harness" in result.stdout
    assert "no code index" in result.stderr


def test_global_effect_file_escalates_to_full_suite(repo: "HarnessRepo") -> None:
    _index(repo)
    repo.write("tests/conftest.py", "import pytest\n")
    result = repo.run_script("test_affected.sh", env=_stub_path(repo, with_codegraph=True))
    assert result.returncode == 0
    assert "PYTEST_ARGS:-q --ignore=tests/harness" in result.stdout
    assert "global-effect" in result.stderr


def test_lockfile_change_escalates_to_full_suite(repo: "HarnessRepo") -> None:
    _index(repo)
    repo.write("uv.lock", "version = 1\n")
    result = repo.run_script("test_affected.sh", env=_stub_path(repo, with_codegraph=True))
    assert result.returncode == 0
    assert "PYTEST_ARGS:-q --ignore=tests/harness" in result.stdout
    assert "global-effect" in result.stderr


def test_source_change_runs_only_affected_tests(repo: "HarnessRepo") -> None:
    _index(repo)
    repo.write("app/services/user.py", "def existing() -> None: ...\ndef added(): ...\n")
    result = repo.run_script("test_affected.sh", env=_stub_path(repo, with_codegraph=True))
    assert result.returncode == 0
    assert "PYTEST_ARGS:-q tests/test_user.py" in result.stdout


def test_empty_index_result_falls_back_to_full_suite(repo: "HarnessRepo") -> None:
    _index(repo)
    stub_env = _stub_path(repo, with_codegraph=True)
    empty_affected = '#!/bin/sh\ncase "$1" in sync) exit 0 ;; affected) cat >/dev/null ;; esac\n'
    codegraph = Path(repo.path / "stubs" / "codegraph")
    codegraph.write_text(empty_affected)
    codegraph.chmod(0o755)
    repo.write("app/services/user.py", "def existing() -> None: ...\ndef added(): ...\n")
    result = repo.run_script("test_affected.sh", env=stub_env)
    assert result.returncode == 0
    assert "PYTEST_ARGS:-q --ignore=tests/harness" in result.stdout
    assert "no affected tests" in result.stderr


def test_no_python_change_runs_nothing(repo: "HarnessRepo") -> None:
    _index(repo)
    repo.write("docs/note.md", "note\n")
    result = repo.run_script("test_affected.sh", env=_stub_path(repo, with_codegraph=True))
    assert result.returncode == 0
    assert "PYTEST_ARGS" not in result.stdout
    assert "no source changes" in result.stderr


def test_no_diff_base_escalates_to_full_suite(repo: "HarnessRepo") -> None:
    _index(repo)
    stub_env = _stub_path(repo, with_codegraph=True)
    repo.git("remote", "remove", "origin")
    repo.branch("feat/committed")
    repo.commit("committed change", files={"app/services/user.py": "def changed(): ...\n"})
    result = repo.run_script("test_affected.sh", env=stub_env)
    assert result.returncode == 0
    assert "PYTEST_ARGS:-q --ignore=tests/harness" in result.stdout
    assert "cannot resolve default branch" in result.stderr


def test_shared_test_helper_escalates_to_full_suite(repo: "HarnessRepo") -> None:
    _index(repo)
    repo.write("tests/helper.py", "SHARED = 1\n")
    result = repo.run_script("test_affected.sh", env=_stub_path(repo, with_codegraph=True))
    assert result.returncode == 0
    assert "PYTEST_ARGS:-q --ignore=tests/harness" in result.stdout
    assert "non-test .py under tests/" in result.stderr


def test_deleted_source_escalates_to_full_suite(repo: "HarnessRepo") -> None:
    _index(repo)
    repo.git("rm", "-q", "app/services/user.py")
    result = repo.run_script("test_affected.sh", env=_stub_path(repo, with_codegraph=True))
    assert result.returncode == 0
    assert "PYTEST_ARGS:-q --ignore=tests/harness" in result.stdout
    assert "source file deleted" in result.stderr


def test_custom_index_tool_via_env_seam(repo: "HarnessRepo") -> None:
    repo.write("graph-index/summary.json", "{}")
    repo.write("app/services/user.py", "def existing() -> None: ...\ndef added(): ...\n")
    env = _stub_path(repo, with_codegraph=False)
    env.update(
        {
            "INDEX_MARKER": "graph-index/summary.json",
            "INDEX_SYNC_CMD": "true",
            "AFFECTED_TESTS_CMD": "cat >/dev/null; printf 'tests/test_user.py\\n'",
        }
    )
    result = repo.run_script("test_affected.sh", env=env)
    assert result.returncode == 0
    assert "PYTEST_ARGS:-q tests/test_user.py" in result.stdout
