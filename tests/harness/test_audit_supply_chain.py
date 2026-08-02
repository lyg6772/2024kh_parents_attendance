import shutil
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from .conftest import BASE_PATH, BASE_PYPROJECT, HarnessRepo

CHECK = "40-supply-chain.sh"

# upload_time must stay relative to the wall clock the script judges against -
# a hardcoded "young" date silently ages past the 90-day window and flips the test.
YOUNG_UPLOAD = (datetime.now(UTC) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")

FAKE_CURL = f"""\
#!/bin/sh
code=200
case "$*" in
  *nonexistent*) code=404 ;;
esac
case "$*" in
  *" -w "*|*"-w %{{http_code}}"*)
    printf '%s' "$code"
    exit 0
    ;;
esac
case "$*" in
  *youngpkg*) printf '{{"releases":{{"1.0":[{{"upload_time":"{YOUNG_UPLOAD}"}}]}}}}' ;;
  *) printf '{{"releases":{{"1.0":[{{"upload_time":"2015-01-01T00:00:00"}}]}}}}' ;;
esac
"""


@pytest.fixture
def fake_curl_path(tmp_path: Path) -> str:
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(FAKE_CURL)
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
    # fake bin first (shadows curl), venv python next, then the shared base -
    # host PATH included so a non-standard jq found by shutil.which stays reachable
    py_dir = Path(sys.executable).parent
    return f"{bin_dir}:{py_dir}:{BASE_PATH}"


def _add_dep(repo: HarnessRepo, dep_line: str, extra_toml: str = "") -> None:
    repo.branch("feat/x")
    new_pyproject = (
        BASE_PYPROJECT.replace(
            'dependencies = ["fastapi>=0.100"]',
            f'dependencies = ["fastapi>=0.100", "{dep_line}"]',
        )
        + extra_toml
    )
    repo.commit("add dependency", files={"pyproject.toml": new_pyproject})


def test_no_pyproject_change_passes(repo: HarnessRepo, fake_curl_path: str) -> None:
    repo.branch("feat/x")
    repo.commit("code only", files={"app/services/x.py": "def x() -> None: ...\n"})
    result = repo.run_audit(CHECK, branch="feat/x", env={"PATH": fake_curl_path})
    assert result.returncode == 0, result.stdout + result.stderr


def test_hallucinated_package_fails_hard(repo: HarnessRepo, fake_curl_path: str) -> None:
    _add_dep(repo, "nonexistent-pkg-zzz>=1.0")
    result = repo.run_audit(CHECK, branch="feat/x", env={"PATH": fake_curl_path})
    assert result.returncode == 1
    assert "does NOT exist" in result.stdout


def test_existing_old_package_passes(repo: HarnessRepo, fake_curl_path: str) -> None:
    _add_dep(repo, "realpkg>=1.0")
    result = repo.run_audit(CHECK, branch="feat/x", env={"PATH": fake_curl_path})
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("jq") is None, reason="age check requires jq")
def test_young_package_flags_typosquat_risk(repo: HarnessRepo, fake_curl_path: str) -> None:
    _add_dep(repo, "youngpkg>=1.0")
    result = repo.run_audit(CHECK, branch="feat/x", env={"PATH": fake_curl_path})
    assert result.returncode == 1
    assert "younger than 90 days" in result.stdout


def test_url_sourced_dependency_fails_hard(repo: HarnessRepo, fake_curl_path: str) -> None:
    _add_dep(repo, "somepkg @ git+https://github.com/evil/somepkg")
    result = repo.run_audit(CHECK, branch="feat/x", env={"PATH": fake_curl_path})
    assert result.returncode == 1
    assert "URL/git" in result.stdout


def test_uv_sources_redirect_fails_hard(repo: HarnessRepo, fake_curl_path: str) -> None:
    _add_dep(
        repo,
        "realpkg>=1.0",
        extra_toml='\n[tool.uv.sources]\nrealpkg = { git = "https://github.com/evil/realpkg" }\n',
    )
    result = repo.run_audit(CHECK, branch="feat/x", env={"PATH": fake_curl_path})
    assert result.returncode == 1
    assert "URL/git" in result.stdout


def test_nonpipeline_branch_skips(repo: HarnessRepo, fake_curl_path: str) -> None:
    repo.branch("chore/z")
    repo.commit("docs", files={"docs/note.md": "note\n"})
    result = repo.run_audit(CHECK, branch="chore/z", env={"PATH": fake_curl_path})
    assert result.returncode == 0


def test_bootstrap_does_not_waive_supply_chain(repo: HarnessRepo, fake_curl_path: str) -> None:
    """R4-3: a hallucinated dependency added by the install PR must still fail."""
    repo.branch("feat/moru-init")   # nonpipeline branches skip this check anyway
    _add_dep(repo, "nonexistent-pkg-zzz>=1.0")
    repo.commit("install the harness", files={".agents/workflow.md": "pipeline\n"})
    result = repo.run_audit(CHECK, branch="feat/moru-init", env={"PATH": fake_curl_path})
    assert result.returncode == 1, result.stdout + result.stderr
