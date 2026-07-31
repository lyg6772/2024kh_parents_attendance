from .conftest import HarnessRepo

CHECK = "30-migration.sh"

DESTRUCTIVE_MIGRATION = """\
revision = "b2"
down_revision = "a1"

def upgrade():
    op.drop_column("users", "legacy_flag")

def downgrade():
    op.add_column("users", sa.Column("legacy_flag", sa.Boolean()))
"""

SAFE_MIGRATION = """\
revision = "b2"
down_revision = "a1"

def upgrade():
    op.add_column("users", sa.Column("nickname", sa.String()))

def downgrade():
    op.drop_column("users", "nickname")
"""

DESTRUCTIVE_HELPER_AFTER_DOWNGRADE = """\
revision = "b2"
down_revision = "a1"

def upgrade():
    _cleanup()

def downgrade():
    op.add_column("users", sa.Column("legacy_flag", sa.Boolean()))

def _cleanup():
    op.execute("DELETE FROM users WHERE legacy_flag IS NULL")
"""

BASE_MIGRATION = (
    'revision = "a1"\ndown_revision = None\n\ndef upgrade(): ...\n\ndef downgrade(): ...\n'
)


def _feat_with_migration(repo: HarnessRepo, migration: str, dlog: str) -> HarnessRepo:
    repo.branch("feat/x")
    repo.commit(
        "schema change",
        files={
            "migrations/versions/a1_base.py": BASE_MIGRATION,
            "migrations/versions/b2_change.py": migration,
            ".agents/context/decisions/x.md": dlog,
        },
    )
    return repo


def test_safe_migration_passes(repo: HarnessRepo) -> None:
    _feat_with_migration(repo, SAFE_MIGRATION, "## 3단계 완료\n- 🧑 사람 결정: 승인\n")
    result = repo.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr


def test_destructive_upgrade_without_acknowledgment_fails(repo: HarnessRepo) -> None:
    _feat_with_migration(repo, DESTRUCTIVE_MIGRATION, "## 3단계 완료\n- 🧑 사람 결정: 승인\n")
    result = repo.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "destructive" in result.stdout


def test_destructive_upgrade_with_acknowledgment_passes(repo: HarnessRepo) -> None:
    _feat_with_migration(
        repo,
        DESTRUCTIVE_MIGRATION,
        "## 3단계 완료\n- 파괴적 변경: users.legacy_flag 컬럼 삭제, 백필 불가\n",
    )
    result = repo.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr


def test_destructive_helper_defined_after_downgrade_is_caught(repo: HarnessRepo) -> None:
    """Regression: the old /upgrade/,/downgrade/ awk range missed destructive
    helpers defined below downgrade() but called from upgrade()."""
    _feat_with_migration(repo, DESTRUCTIVE_HELPER_AFTER_DOWNGRADE, "## 로그\n")
    result = repo.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "destructive" in result.stdout


def test_diverged_alembic_heads_fail_hard(repo: HarnessRepo) -> None:
    repo.branch("feat/x")
    repo.commit(
        "two migrations from the same parent",
        files={
            "migrations/versions/a1_base.py": BASE_MIGRATION,
            "migrations/versions/b2_left.py": 'revision = "b2"\ndown_revision = "a1"\n\ndef upgrade(): ...\n\ndef downgrade(): ...\n',
            "migrations/versions/c3_right.py": 'revision = "c3"\ndown_revision = "a1"\n\ndef upgrade(): ...\n\ndef downgrade(): ...\n',
            ".agents/context/decisions/x.md": "## 로그\n",
        },
    )
    result = repo.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "heads" in result.stdout


def test_nonpipeline_branch_skips(repo: HarnessRepo) -> None:
    repo.branch("chore/z")
    repo.commit("docs", files={"docs/note.md": "note\n"})
    result = repo.run_audit(CHECK, branch="chore/z")
    assert result.returncode == 0


def test_bootstrap_does_not_waive_destructive_migration(repo: HarnessRepo) -> None:
    """R4-3: the bootstrap waiver covers 'did a pipeline run' evidence ONLY.
    A destructive migration in the same PR must still hard-fail - otherwise the
    install PR becomes a hole big enough to drive anything through."""
    # feat/, not chore/: nonpipeline branches skip this check entirely for reasons
    # unrelated to bootstrap, so chore/ would prove nothing here.
    repo.branch("feat/moru-init")
    repo.commit(
        "install the harness AND drop a column",
        files={
            ".agents/workflow.md": "pipeline constitution\n",
            "migrations/versions/0001_drop.py": DESTRUCTIVE_MIGRATION,
        },
    )
    result = repo.run_audit(CHECK, branch="feat/moru-init")
    assert result.returncode == 1, result.stdout + result.stderr
