"""Golden tests for the harness enforcement scripts (scripts/, scripts/audit/).

Each test builds a throwaway git repo simulating a pipeline scenario, runs the
REAL scripts from this repo against it, and asserts on the exit code. The
scripts are the referees of the pipeline - these tests referee the referees.
"""

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"

# standard locations first (deterministic), host PATH appended as fallback so
# environments with tools in non-standard prefixes (nix, asdf, ...) still resolve
BASE_PATH = (
    f"/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:{os.environ.get('PATH', '')}"
)


class HarnessRepo:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = {
            "PATH": BASE_PATH,
            "HOME": str(self.path),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_AUTHOR_NAME": "harness-test",
            "GIT_AUTHOR_EMAIL": "harness@test.local",
            "GIT_COMMITTER_NAME": "harness-test",
            "GIT_COMMITTER_EMAIL": "harness@test.local",
        }
        if extra:
            env.update(extra)
        return env

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.path,
            env=self._env(),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def write(self, rel: str, content: str) -> None:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def commit(
        self,
        message: str,
        files: dict[str, str] | None = None,
        delete: list[str] | None = None,
    ) -> str:
        for rel, content in (files or {}).items():
            self.write(rel, content)
            self.git("add", rel)
        for rel in delete or []:
            self.git("rm", "-q", rel)
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def branch(self, name: str) -> None:
        self.git("switch", "-q", "-c", name)

    def run_script(
        self,
        script: str,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        name, *args = script.split()
        return subprocess.run(
            ["sh", str(SCRIPTS / name), *args],
            cwd=self.path,
            env=self._env(env),
            input=stdin if stdin is not None else "",
            capture_output=True,
            text=True,
            check=False,
        )

    def run_audit(
        self,
        check: str,
        branch: str,
        labels: str = "",
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        audit_env = {"AUDIT_BRANCH": branch, "AUDIT_LABELS": labels}
        if env:
            audit_env.update(env)
        return self.run_script(f"audit/{check}", env=audit_env)


BASE_PYPROJECT = """\
[project]
name = "fixture"
version = "0.1.0"
dependencies = ["fastapi>=0.100"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]
"""

REPO_PROFILE = (PROJECT_ROOT / ".agents/context/repo-profile.sh").read_text()

STAGE7_PASS = """\
# 07 review

## Finder 원출력
- finder A: no blockers
- finder B: no blockers

## 검증하지 못한 것
- 부하 상황의 동시성

## 판정
PASS
"""


@pytest.fixture
def repo(tmp_path: Path) -> HarnessRepo:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    up = HarnessRepo(upstream)
    up.git("init", "-q", "-b", "master")
    up.commit(
        "initial",
        files={
            "pyproject.toml": BASE_PYPROJECT,
            "app/services/user.py": "def existing() -> None: ...\n",
            "tests/test_user.py": "def test_existing() -> None: ...\n",
            ".agents/context/pre-approved-patterns.md": "## 내부 유틸 추가\n승인됨.\n",
            ".agents/context/repo-profile.sh": REPO_PROFILE,
        },
    )
    clone_path = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", str(upstream), str(clone_path)],
        env=up._env(),
        capture_output=True,
        check=True,
    )
    return HarnessRepo(clone_path)


@pytest.fixture
def conformant_feat(repo: HarnessRepo) -> HarnessRepo:
    """feat/x branch that ran the pipeline correctly: artifacts + decision log,
    tests committed WITH the lock (stage 4), impl, lock deleted (stage 7)."""
    repo.branch("feat/x")
    repo.commit(
        "stage 0-3 artifacts",
        files={
            ".agents/context/artifacts/x/01-plan.md": "plan",
            ".agents/context/artifacts/x/02-analysis.md": "analysis",
            ".agents/context/artifacts/x/03-design.md": "design",
            ".agents/context/decisions/x.md": "## 3단계 완료\n- 핵심 결정: 내부 유틸\n",
        },
    )
    repo.commit(
        "stage 4: tests + lock",
        files={
            "tests/test_x.py": "def test_x() -> None: ...\n",
            ".agents/context/locks/x.lock": "feat/x\n",
            ".agents/context/artifacts/x/04-tests.md": "뮤테이션 검증: 1라운드 통과\n",
        },
    )
    repo.commit(
        "stage 5: impl",
        files={"app/services/x.py": "def x() -> None: ...\n"},
    )
    repo.commit(
        "stage 6-7: verify + review, unlock",
        files={
            ".agents/context/artifacts/x/06-verify.md": "lint/type/test green",
            ".agents/context/artifacts/x/07-review.md": STAGE7_PASS,
        },
        delete=[".agents/context/locks/x.lock"],
    )
    return repo
