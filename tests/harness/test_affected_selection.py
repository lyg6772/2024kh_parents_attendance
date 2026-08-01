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


def _goldens(repo: "HarnessRepo") -> None:
    """The golden suite exists in this repo. The fixture has no tests/harness/ by
    default, which is exactly the "repo skipped the goldens at install" shape."""
    repo.write("tests/harness/test_dummy.py", "def test_dummy() -> None: ...\n")


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


def test_enforcement_script_change_runs_the_goldens(repo: "HarnessRepo") -> None:
    """A `scripts/*.sh` change must run the golden tests.

    They are the only referee of the enforcement scripts, and no code index maps
    shell to them. SRC_EXT_RE is a per-stack knob (default `\\.py$`), so before the
    fix a scripts-only change fell out at "no source changes - nothing to test" and
    ran ZERO tests, in exactly the diff that edits the gates.
    """
    _index(repo)
    _goldens(repo)
    repo.write("scripts/audit/99-new-check.sh", "#!/bin/sh\nexit 0\n")
    result = repo.run_script("test_affected.sh", env=_stub_path(repo, with_codegraph=True))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "harness source changed" in result.stderr
    assert "PYTEST_ARGS:-q tests/harness" in result.stdout


def test_harness_src_re_empty_opts_out(repo: "HarnessRepo") -> None:
    """A repo that did not take the golden tests must be able to turn the door off -
    and an unmatched regex is the old silent fail-open, which is why the knob is in
    the profile where a human reviews it rather than hardcoded in the script."""
    _index(repo)
    _goldens(repo)
    repo.write("scripts/audit/99-new-check.sh", "#!/bin/sh\nexit 0\n")
    env = _stub_path(repo, with_codegraph=True)
    env["HARNESS_SRC_RE"] = ""
    result = repo.run_script("test_affected.sh", env=env)
    assert result.returncode == 0
    assert "harness source changed" not in result.stderr
    # the exact goldens invocation, not the substring: _goldens() left an
    # uncommitted tests/harness/test_dummy.py, which the normal selection picks up
    # as a changed test file - that is the selector working, not the door firing.
    assert "PYTEST_ARGS:-q tests/harness\n" not in result.stdout


def test_goldens_run_even_when_the_index_also_selects_tests(repo: "HarnessRepo") -> None:
    """The door is BEFORE the source filter on purpose. If it sat inside the
    full-suite fallback, a stub/real index that answered for the .sh change would
    route to an affected list and skip the goldens - the same hole, one layer in."""
    _index(repo)
    _goldens(repo)
    repo.write("scripts/audit/99-new-check.sh", "#!/bin/sh\nexit 0\n")
    repo.write("app/services/user.py", "def existing() -> None: ...\ndef added(): ...\n")
    result = repo.run_script("test_affected.sh", env=_stub_path(repo, with_codegraph=True))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PYTEST_ARGS:-q tests/harness\n" in result.stdout   # goldens ran, on their own
    assert "tests/test_user.py" in result.stdout                # and the selection still happened


def test_goldens_run_even_without_an_index(repo: "HarnessRepo") -> None:
    """The door must sit ABOVE the index check.

    `full("no code index")` execs, so while the door lived below it an index-less
    repo — most ported repos — never reached it and a gate edit ran zero goldens.
    """
    _goldens(repo)
    repo.write("scripts/audit/99-new-check.sh", "#!/bin/sh\nexit 0\n")
    result = repo.run_script("test_affected.sh", env=_stub_path(repo, with_codegraph=False))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PYTEST_ARGS:-q tests/harness" in result.stdout
    assert "no code index" in result.stderr


def test_goldens_skipped_when_the_repo_has_no_harness_dir(repo: "HarnessRepo") -> None:
    """A repo that skipped tests/harness at install (no pytest) must not be
    hard-blocked. The profile opt-out is documented, but a default that needs
    reading to survive is the wrong default - the door checks the directory."""
    _index(repo)   # note: _goldens() deliberately NOT called - no tests/harness/
    repo.write("scripts/audit/99-new-check.sh", "#!/bin/sh\nexit 0\n")
    result = repo.run_script("test_affected.sh", env=_stub_path(repo, with_codegraph=True))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests/harness" not in result.stdout
