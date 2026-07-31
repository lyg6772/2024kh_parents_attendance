import json

from .conftest import HarnessRepo

GUARD = "test_lock_guard.sh"
CHECK = "test_lock_check.sh"


def _locked_repo(repo: HarnessRepo, lock_line: str = "feat/x") -> HarnessRepo:
    repo.branch("feat/x")
    repo.commit("lock", files={".agents/context/locks/x.lock": f"{lock_line}\n"})
    return repo


def _edit_json(file_path: str) -> str:
    return json.dumps({"tool_input": {"file_path": file_path}})


def _bash_json(command: str) -> str:
    return json.dumps({"tool_input": {"command": command}})


def _run_guard(repo: HarnessRepo, stdin: str) -> int:
    result = repo.run_script(GUARD, env={"CLAUDE_PROJECT_DIR": str(repo.path)}, stdin=stdin)
    return result.returncode


def test_guard_blocks_tests_edit_while_locked(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    assert _run_guard(repo, _edit_json(f"{repo.path}/tests/test_x.py")) == 2


def test_guard_blocks_relative_tests_path(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    assert _run_guard(repo, _edit_json("tests/test_x.py")) == 2


def test_guard_allows_app_edit_while_locked(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    assert _run_guard(repo, _edit_json(f"{repo.path}/app/services/x.py")) == 0


def test_guard_allows_tests_edit_without_lock(repo: HarnessRepo) -> None:
    repo.branch("feat/x")
    assert _run_guard(repo, _edit_json(f"{repo.path}/tests/test_x.py")) == 0


def test_guard_ignores_other_branch_lock(repo: HarnessRepo) -> None:
    _locked_repo(repo, lock_line="feat/other")
    assert _run_guard(repo, _edit_json(f"{repo.path}/tests/test_x.py")) == 0


def test_guard_matches_lock_by_feature_short_name(repo: HarnessRepo) -> None:
    _locked_repo(repo, lock_line="x")
    assert _run_guard(repo, _edit_json(f"{repo.path}/tests/test_x.py")) == 2


def test_guard_fails_closed_on_detached_head_with_lock(repo: HarnessRepo) -> None:
    _locked_repo(repo, lock_line="feat/other")
    repo.git("checkout", "-q", "--detach")
    assert _run_guard(repo, _edit_json(f"{repo.path}/tests/test_x.py")) == 2


def test_guard_respects_human_override_marker(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    repo.write(".agents/context/locks/x.lock.override", "")
    assert _run_guard(repo, _edit_json(f"{repo.path}/tests/test_x.py")) == 0


def test_guard_blocks_bash_redirect_into_tests(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    assert _run_guard(repo, _bash_json("echo broken > tests/test_x.py")) == 2


def test_guard_blocks_sed_inplace_on_tests(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    assert _run_guard(repo, _bash_json("sed -i '' 's/assert/pass #/' tests/test_x.py")) == 2


def test_guard_allows_readonly_bash_on_tests(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    assert _run_guard(repo, _bash_json("pytest tests/ -q")) == 0
    assert _run_guard(repo, _bash_json("cat tests/test_x.py")) == 0


def test_check_blocks_commit_while_locked(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    result = repo.run_script(CHECK)
    assert result.returncode == 1
    assert "LOCKED" in result.stdout


def test_check_allows_commit_with_override_env(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    result = repo.run_script(CHECK, env={"TEST_LOCK_OVERRIDE": "1"})
    assert result.returncode == 0


def test_check_allows_commit_without_lock(repo: HarnessRepo) -> None:
    repo.branch("feat/x")
    result = repo.run_script(CHECK)
    assert result.returncode == 0


def test_check_matches_lock_by_feature_short_name(repo: HarnessRepo) -> None:
    _locked_repo(repo, lock_line="x")
    result = repo.run_script(CHECK)
    assert result.returncode == 1


def test_check_fails_closed_on_detached_head_with_lock(repo: HarnessRepo) -> None:
    _locked_repo(repo, lock_line="feat/other")
    repo.git("checkout", "-q", "--detach")
    result = repo.run_script(CHECK)
    assert result.returncode == 1
    assert "detached HEAD" in result.stdout


def test_unlock_tests_refuses_without_tty(repo: HarnessRepo) -> None:
    """The sanctioned override path is human-anchored: no controlling terminal
    (= agent shell) must mean refusal, and no .override marker is created."""
    _locked_repo(repo)
    result = repo.run_script("unlock_tests.sh x")
    assert result.returncode == 1
    assert "refusing" in result.stdout
    assert not (repo.path / ".agents/context/locks/x.lock.override").exists()


def test_unlock_tests_requires_existing_lock(repo: HarnessRepo) -> None:
    repo.branch("feat/x")
    result = repo.run_script("unlock_tests.sh nonexistent")
    assert result.returncode == 1
    assert "no lock marker" in result.stdout


# --- staged-file scoping -------------------------------------------------
# The check governs the TEST contract. Blocking commits that stage no test file
# broke the pipeline's own stage-5 commits (raw-hook installs have no
# `files: ^tests/` scoping) and every rebase/cherry-pick/bisect commit on a
# detached HEAD — both of which train people into habitual TEST_LOCK_OVERRIDE.


def _stage(repo: HarnessRepo, path: str, body: str) -> None:
    (repo.path / path).parent.mkdir(parents=True, exist_ok=True)
    (repo.path / path).write_text(body)
    repo.git("add", path)


def test_check_allows_non_test_commit_while_locked(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    _stage(repo, "app/services/impl.py", "def impl() -> None: ...\n")
    result = repo.run_script(CHECK)
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_blocks_staged_test_edit_while_locked(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    _stage(repo, "tests/test_x.py", "def test_x() -> None: pass  # weakened\n")
    result = repo.run_script(CHECK)
    assert result.returncode == 1
    assert "LOCKED" in result.stdout


def test_check_allows_non_test_commit_on_detached_head(repo: HarnessRepo) -> None:
    _locked_repo(repo, lock_line="feat/other")
    repo.git("checkout", "-q", "--detach")
    _stage(repo, "app/services/impl.py", "def impl() -> None: ...\n")
    result = repo.run_script(CHECK)
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_still_blocks_staged_test_edit_on_detached_head(repo: HarnessRepo) -> None:
    _locked_repo(repo, lock_line="feat/other")
    repo.git("checkout", "-q", "--detach")
    _stage(repo, "tests/test_x.py", "def test_x() -> None: pass\n")
    result = repo.run_script(CHECK)
    assert result.returncode == 1
    assert "detached HEAD" in result.stdout


# TESTS_DIR feeds the staged-file scoping above via a LITERAL quoted prefix
# (`case "$_f" in "$_tests_dir"/*`). Only normalization can break it: a trailing
# slash or a leading ./ must not make it match nothing and exit 0 - that would be
# a lock guard failing OPEN.
def test_check_scoping_survives_trailing_slash_in_tests_dir(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    repo.write(".agents/context/repo-profile.sh", 'TESTS_DIR="tests/"\n')
    _stage(repo, "tests/test_x.py", "def test_x() -> None: pass\n")
    result = repo.run_script(CHECK)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "LOCKED" in result.stdout


# `git mv tests/test_x.py elsewhere.py` stages only the DESTINATION when rename
# detection is on (the default), so the tests/ prefix vanishes and the lock is
# bypassed - a locked test could be moved out of the guarded tree unnoticed.
def test_check_blocks_moving_a_locked_test_out_of_tests_dir(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    repo.commit(
        "add the test that will be moved",
        files={"tests/test_x.py": "def test_x() -> None:\n    assert 1\n    assert 2\n"},
    )
    repo.git("mv", "tests/test_x.py", "elsewhere.py")
    result = repo.run_script(CHECK)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "LOCKED" in result.stdout


def test_check_falls_back_when_profile_kills_the_subshell(repo: HarnessRepo) -> None:
    """TESTS_DIR is read in a subshell that inherits `set -u`; a profile with an
    unbound reference kills it, and an empty value would disable the guard."""
    _locked_repo(repo)
    repo.write(".agents/context/repo-profile.sh", 'TESTS_DIR="$UNBOUND_THING"\n')
    _stage(repo, "tests/test_x.py", "def test_x() -> None: pass\n")
    result = repo.run_script(CHECK)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "LOCKED" in result.stdout


def test_check_survives_a_profile_that_prints(repo: HarnessRepo) -> None:
    """The profile is sourced in a subshell whose OUTPUT is captured; anything it
    prints would otherwise be concatenated into TESTS_DIR and match nothing."""
    _locked_repo(repo)
    repo.write(".agents/context/repo-profile.sh", 'echo loading\nTESTS_DIR="tests"\n')
    _stage(repo, "tests/test_x.py", "def test_x() -> None: pass\n")
    result = repo.run_script(CHECK)
    assert result.returncode == 1, result.stdout + result.stderr


def test_check_normalizes_dot_slash_in_tests_dir(repo: HarnessRepo) -> None:
    _locked_repo(repo)
    repo.write(".agents/context/repo-profile.sh", 'TESTS_DIR="./tests"\n')
    _stage(repo, "tests/test_x.py", "def test_x() -> None: pass\n")
    result = repo.run_script(CHECK)
    assert result.returncode == 1, result.stdout + result.stderr
