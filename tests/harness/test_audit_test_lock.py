import pytest

from .conftest import STAGE7_PASS, HarnessRepo

CHECK = "20-test-lock.sh"


def test_conformant_feature_passes(conformant_feat: HarnessRepo) -> None:
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr


def test_active_lock_at_pr_time_fails(repo: HarnessRepo) -> None:
    repo.branch("feat/x")
    repo.commit(
        "stage 4: tests + lock, never unlocked",
        files={
            "tests/test_x.py": "def test_x() -> None: ...\n",
            ".agents/context/locks/x.lock": "feat/x\n",
        },
    )
    result = repo.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "still present" in result.stdout


def test_tests_edited_in_lock_window_without_override_fails(
    conformant_feat: HarnessRepo,
) -> None:
    conformant_feat.commit(
        "weaken test after review",
        files={"tests/test_x.py": "def test_x() -> None: pass  # weakened\n"},
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "without an 'override" in result.stdout


def test_tests_edited_with_override_record_passes(conformant_feat: HarnessRepo) -> None:
    conformant_feat.commit(
        "human-approved test fix",
        files={
            "tests/test_x.py": "def test_x() -> None: ...  # approved fix\n",
            ".agents/context/decisions/x.md": "## 4단계 수정\n- override 사용: 사람 승인, 잘못된 assertion 수정\n",
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr


# The kernel asks EVERY decision log to carry an 'override 사용:' line, so it is
# normally filled with a placeholder. Grepping for the token alone made the
# safety-core lock-window check pass on any conformant log — tests could be
# weakened inside the LOCK window with nothing to stop it.
@pytest.mark.parametrize(
    "placeholder_log",
    [
        "## override 사용\n없음.\n",
        "## override 사용\n- 없음\n",
        "## override 사용\n* none\n",
        "## override 사용\n+ N/A\n",
        # heading form is NOT a record: a lookahead here accepted whatever line
        # came next, so an unrelated bullet licensed weakening a locked test
        "## override 사용\n2026-07-26 사람 승인\n",
        "## override 사용\n\n- 다음 단계: 배포\n",
        "- override 사용: 없음\n",
        "- override 사용: none\n",
        "- override 사용: N/A\n",
        "- override 사용: -\n",
        "- override 사용:\n",
    ],
)
def test_placeholder_override_line_is_not_a_record(
    conformant_feat: HarnessRepo, placeholder_log: str
) -> None:
    conformant_feat.commit(
        "weaken a locked test, log carries only the placeholder override line",
        files={
            "tests/test_x.py": "def test_x() -> None: pass  # weakened\n",
            ".agents/context/decisions/x.md": placeholder_log,
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "without an 'override" in result.stdout


def test_colon_form_override_record_passes(conformant_feat: HarnessRepo) -> None:
    """The specified form is `override 사용: <무엇을, 왜>` on one line
    (QUICKSTART, team-policy). Only that counts — see the placeholder cases."""
    conformant_feat.commit(
        "human-approved test fix",
        files={
            "tests/test_x.py": "def test_x() -> None: ...  # approved fix\n",
            ".agents/context/decisions/x.md": (
                "## 4단계 수정\n- override 사용: 2026-07-26 사람 승인 — 잘못된 assertion 수정\n"
            ),
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr


def test_feat_branch_that_never_locked_fails(repo: HarnessRepo) -> None:
    repo.branch("feat/x")
    repo.commit(
        "tests without any lock",
        files={"tests/test_x.py": "def test_x() -> None: ...\n"},
    )
    result = repo.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "never locked" in result.stdout


def test_feat_branch_that_never_locked_ignores_audit_exempt(repo: HarnessRepo) -> None:
    """Never-locking is the cheapest way to have no lock window at all - it is
    safety core, so the audit-exempt label must not downgrade it to a warning."""
    repo.branch("feat/x")
    repo.commit(
        "tests without any lock",
        files={"tests/test_x.py": "def test_x() -> None: ...\n"},
    )
    result = repo.run_audit(CHECK, branch="feat/x", labels="audit-exempt")
    assert result.returncode == 1
    assert "FAIL(hard" in result.stdout


def test_fix_branch_touching_tests_without_lock_fails(repo: HarnessRepo) -> None:
    repo.branch("fix/y")
    repo.commit(
        "repro test without lock",
        files={"tests/test_y_repro.py": "def test_repro() -> None: ...\n"},
    )
    result = repo.run_audit(CHECK, branch="fix/y")
    assert result.returncode == 1
    assert "never committed a test-LOCK" in result.stdout


def test_pr_merge_commit_checkout_does_not_false_fail(
    conformant_feat: HarnessRepo,
) -> None:
    """CI checks out refs/pull/N/merge. The lock is added then deleted on the
    feature side, so the merge commit is TREESAME to master for the lock path -
    without --full-history the lock's history is pruned and a conformant
    feature false-fails as 'never locked'. Regression guard for that fix."""
    repo = conformant_feat
    repo.git("checkout", "-q", "--detach", "master")
    repo.git("merge", "-q", "--no-ff", "-m", "simulated PR merge", "feat/x")
    result = repo.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "never locked" not in result.stdout


def test_upstream_merge_bringing_tests_changes_passes(
    conformant_feat: HarnessRepo,
) -> None:
    repo = conformant_feat
    upstream = HarnessRepo(repo.path.parent / "upstream")
    upstream.commit(
        "unrelated test change on master",
        files={"tests/test_user.py": "def test_existing() -> None: ...  # v2\n"},
    )
    repo.git("fetch", "-q", "origin")
    repo.git("merge", "-q", "--no-edit", "origin/master")
    result = repo.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr


def test_nonpipeline_branch_skips(repo: HarnessRepo) -> None:
    repo.branch("chore/z")
    repo.commit("docs only", files={"docs/note.md": "note\n"})
    result = repo.run_audit(CHECK, branch="chore/z")
    assert result.returncode == 0


def test_stage7_pass_artifact_fixture_is_wellformed() -> None:
    assert "판정" in STAGE7_PASS
    assert "검증하지 못한 것" in STAGE7_PASS


def test_bootstrap_pr_is_not_asked_for_a_lock_marker(repo: HarnessRepo) -> None:
    """A harness-install PR has no feature, so no stage-4 tests and nothing to
    lock; demanding the marker made it unpassable on feat/*."""
    repo.branch("feat/moru-init")
    repo.commit(
        "install the harness",
        files={
            ".agents/workflow.md": "pipeline constitution\n",
            "tests/test_x.py": "def test_x() -> None: ...\n",
        },
    )
    result = repo.run_audit(CHECK, branch="feat/moru-init")
    assert result.returncode == 0, result.stdout + result.stderr
