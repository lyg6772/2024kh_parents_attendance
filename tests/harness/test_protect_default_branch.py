"""Golden tests for scripts/protect_default_branch.sh — the local stand-in for
branch protection: a real push to the default branch must be refused unless a
human confirms on /dev/tty (which an agent shell never has)."""

from .conftest import HarnessRepo

GUARD = "protect_default_branch.sh"


def test_refuses_default_branch_push_without_tty(repo: HarnessRepo) -> None:
    result = repo.run_script(GUARD, env={"PRE_COMMIT_REMOTE_BRANCH": "refs/heads/master"})
    assert result.returncode == 1
    assert "refusing" in result.stdout


def test_allows_feature_branch_push(repo: HarnessRepo) -> None:
    result = repo.run_script(GUARD, env={"PRE_COMMIT_REMOTE_BRANCH": "refs/heads/feat/x"})
    assert result.returncode == 0


def test_skips_when_not_a_real_push(repo: HarnessRepo) -> None:
    """PRE_COMMIT_REMOTE_BRANCH unset = manual `pre-commit run` — nothing pushed."""
    result = repo.run_script(GUARD)
    assert result.returncode == 0


def test_skips_in_ci(repo: HarnessRepo) -> None:
    result = repo.run_script(
        GUARD, env={"PRE_COMMIT_REMOTE_BRANCH": "refs/heads/master", "CI": "1"}
    )
    assert result.returncode == 0


def test_skips_in_github_actions(repo: HarnessRepo) -> None:
    result = repo.run_script(
        GUARD, env={"PRE_COMMIT_REMOTE_BRANCH": "refs/heads/master", "GITHUB_ACTIONS": "true"}
    )
    assert result.returncode == 0


def test_fails_closed_when_default_branch_unresolvable(repo: HarnessRepo) -> None:
    repo.git("remote", "remove", "origin")
    result = repo.run_script(GUARD, env={"PRE_COMMIT_REMOTE_BRANCH": "refs/heads/master"})
    assert result.returncode == 1
    assert "failing closed" in result.stdout
