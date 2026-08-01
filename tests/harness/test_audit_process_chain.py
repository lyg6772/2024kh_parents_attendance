import re
import subprocess

import pytest

from .conftest import REPO_PROFILE, STAGE7_PASS, HarnessRepo

CHECK = "10-process-chain.sh"

ROUTER_ENDPOINT = (
    "from fastapi import APIRouter\n"
    "router = APIRouter()\n"
    "@router.post('/things')\n"
    "async def create_thing() -> dict[str, str]: ...\n"
)

STAGE7_PASS_GATED = STAGE7_PASS + "\n## 2차 verifier\n1차 판정 동의, 기각 finding 재검토 완료\n"


def test_conformant_feature_passes(conformant_feat: HarnessRepo) -> None:
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_repo_profile_fails_closed(conformant_feat: HarnessRepo) -> None:
    """Without the repo profile, gate re-derivation would silently match nothing
    (safety core = no-op in a transplanted repo). Must be a hard red, not a skip."""
    conformant_feat.commit("profile removed", delete=[".agents/context/repo-profile.sh"])
    result = conformant_feat.run_audit(CHECK, branch="feat/x", labels="audit-exempt")
    assert result.returncode == 1
    assert "repo-profile.sh missing" in result.stdout


def test_conformant_feature_with_finder_files_passes(conformant_feat: HarnessRepo) -> None:
    """Finder raw-output files (07-finder-<lens>.md, agent-review.md context
    economy) live next to 07-review.md and must NOT be held to the verdict format."""
    conformant_feat.commit(
        "finder raw outputs",
        files={
            ".agents/context/artifacts/x/07-finder-correctness.md": "- no blockers\n",
            ".agents/context/artifacts/x/07-finder-security.md": "- no blockers\n",
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr


def test_finder_files_without_review_verdict_fail(conformant_feat: HarnessRepo) -> None:
    conformant_feat.git("rm", "-q", ".agents/context/artifacts/x/07-review.md")
    conformant_feat.commit(
        "finders only, verdict artifact deleted",
        files={".agents/context/artifacts/x/07-finder-correctness.md": "- no blockers\n"},
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "not a review verdict" in result.stdout


def test_missing_artifacts_fail(repo: HarnessRepo) -> None:
    repo.branch("feat/x")
    repo.commit("code without pipeline", files={"app/services/x.py": "def x() -> None: ...\n"})
    result = repo.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "artifact missing" in result.stdout
    assert "decision log missing" in result.stdout


def test_missing_artifacts_with_audit_exempt_label_warns(repo: HarnessRepo) -> None:
    repo.branch("feat/x")
    repo.commit("code without pipeline", files={"app/services/x.py": "def x() -> None: ...\n"})
    result = repo.run_audit(CHECK, branch="feat/x", labels="audit-exempt")
    assert result.returncode == 0
    assert "WARN(exempt)" in result.stdout


def test_verdict_template_stub_fails(conformant_feat: HarnessRepo) -> None:
    conformant_feat.commit(
        "stub verdict",
        files={
            ".agents/context/artifacts/x/07-review.md": (
                "## Finder 원출력\nfinder output\n\n"
                "## 검증하지 못한 것\n- 없음\n\n"
                "## 판정\nPASS / REFACTOR / ESCALATE\n"
            )
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "template stub" in result.stdout


def test_verdict_refactor_is_unresolved(conformant_feat: HarnessRepo) -> None:
    conformant_feat.commit(
        "refactor verdict",
        files={
            ".agents/context/artifacts/x/07-review.md": STAGE7_PASS.replace(
                "## 판정\nPASS", "## 판정\nREFACTOR"
            )
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "unresolved" in result.stdout


def test_empty_finder_section_fails(conformant_feat: HarnessRepo) -> None:
    conformant_feat.commit(
        "finder evidence removed",
        files={
            ".agents/context/artifacts/x/07-review.md": (
                "## Finder 원출력\n\n## 검증하지 못한 것\n- 없음\n\n## 판정\nPASS\n"
            )
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "Finder" in result.stdout


def test_missing_mutation_record_fails(conformant_feat: HarnessRepo) -> None:
    conformant_feat.commit(
        "stage 4 artifact without mutation check",
        files={".agents/context/artifacts/x/04-tests.md": "테스트 목록만 있음\n"},
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "뮤테이션 검증" in result.stdout


def test_amendment_cap_exceeded_fails(conformant_feat: HarnessRepo) -> None:
    conformant_feat.commit(
        "third design amendment",
        files={
            ".agents/context/artifacts/x/03-design.md": (
                "design\n## 변경 내역\n1\n## 변경 내역\n2\n## 변경 내역\n3\n"
            )
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "amendments" in result.stdout


def test_gate_diff_on_chore_branch_fails_hard(repo: HarnessRepo) -> None:
    repo.branch("chore/sneaky")
    repo.commit(
        "new endpoint on chore branch", files={"app/api/v1/endpoints/thing.py": ROUTER_ENDPOINT}
    )
    result = repo.run_audit(CHECK, branch="chore/sneaky")
    assert result.returncode == 1
    assert "FAIL(hard" in result.stdout


def test_gate_diff_on_chore_branch_ignores_audit_exempt(repo: HarnessRepo) -> None:
    repo.branch("chore/sneaky")
    repo.commit(
        "new endpoint on chore branch", files={"app/api/v1/endpoints/thing.py": ROUTER_ENDPOINT}
    )
    result = repo.run_audit(CHECK, branch="chore/sneaky", labels="audit-exempt")
    assert result.returncode == 1


def test_gate_without_human_decision_fails_hard(conformant_feat: HarnessRepo) -> None:
    conformant_feat.commit(
        "new endpoint, gate never approved",
        files={
            "app/api/v1/endpoints/thing.py": ROUTER_ENDPOINT,
            ".agents/context/artifacts/x/07-review.md": STAGE7_PASS_GATED,
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "사람 결정" in result.stdout


def test_gate_with_human_decision_passes(conformant_feat: HarnessRepo) -> None:
    conformant_feat.commit(
        "new endpoint with approval",
        files={
            "app/api/v1/endpoints/thing.py": ROUTER_ENDPOINT,
            ".agents/context/artifacts/x/07-review.md": STAGE7_PASS_GATED,
            ".agents/context/decisions/x.md": (
                "## 3단계 완료\n- 핵심 결정: API 추가\n- 🧑 사람 결정: 승인 (2026-07-16)\n"
            ),
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr


def test_gate_target_pass_without_second_verifier_fails(
    conformant_feat: HarnessRepo,
) -> None:
    conformant_feat.commit(
        "gated endpoint, only first verifier",
        files={
            "app/api/v1/endpoints/thing.py": ROUTER_ENDPOINT,
            ".agents/context/decisions/x.md": ("## 3단계 완료\n- 🧑 사람 결정: 승인\n"),
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "2차 verifier" in result.stdout


def test_registered_preapproved_pattern_passes(conformant_feat: HarnessRepo) -> None:
    conformant_feat.commit(
        "deps change under registered pattern",
        files={
            "pyproject.toml": 'x = "y"\n',
            ".agents/context/artifacts/x/07-review.md": STAGE7_PASS_GATED,
            ".agents/context/decisions/x.md": (
                "## 3단계 완료\n- 사전 승인 패턴 적용: 내부 유틸 추가\n"
            ),
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr


def test_unregistered_preapproved_pattern_fails_hard(
    conformant_feat: HarnessRepo,
) -> None:
    conformant_feat.commit(
        "deps change with fake pattern claim",
        files={
            "pyproject.toml": 'x = "y"\n',
            ".agents/context/decisions/x.md": (
                "## 3단계 완료\n- 사전 승인 패턴 적용: 존재하지 않는 패턴\n"
            ),
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "unregistered pattern" in result.stdout


def test_high_risk_path_rejects_preapproved_pattern(
    conformant_feat: HarnessRepo,
) -> None:
    conformant_feat.commit(
        "security change under pattern claim",
        files={
            "app/core/security.py": "SALT_ROUNDS = 12\n",
            ".agents/context/decisions/x.md": (
                "## 3단계 완료\n- 사전 승인 패턴 적용: 내부 유틸 추가\n"
            ),
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "high-risk" in result.stdout


def test_feat_branch_editing_enforcement_surface_fails_hard(
    conformant_feat: HarnessRepo,
) -> None:
    """A feature PR that rewrites the gate-detection knobs could neuter the audit
    in the same PR that exploits it - hard red without a human decision record."""
    # neuter the API gate: no decorator name can match after this.
    neutered = REPO_PROFILE.replace("(router|app)", "(nevermatches)")
    # a no-op replace commits a byte-identical file, so the diff the check looks
    # for never exists and the test proves nothing. The previous form targeted a
    # literal `@router` that the profile stopped containing when API_GATE_RE was
    # generalized (2026-07-26) - and nothing said so. Assert the mutation landed.
    assert neutered != REPO_PROFILE, "profile mutation was a no-op"
    conformant_feat.commit(
        "gate regex neutered",
        files={".agents/context/repo-profile.sh": neutered},
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1
    assert "enforcement surface" in result.stdout


def test_feat_branch_editing_enforcement_with_human_decision_passes(
    conformant_feat: HarnessRepo,
) -> None:
    conformant_feat.commit(
        "profile tweak with approval",
        files={
            ".agents/context/repo-profile.sh": REPO_PROFILE + "# tuned\n",
            ".agents/context/decisions/x.md": (
                "## 3단계 완료\n- 핵심 결정: 프로필 조정\n- 🧑 사람 결정: 승인\n"
            ),
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr


def test_refactor_shared_code_without_artifacts_warns_shadow(repo: HarnessRepo) -> None:
    """Shadow device (team-policy 하네스 개선 루프 #2): warns but does not fail
    until hit data justifies promotion to a blocking violation."""
    repo.branch("refactor/base-cleanup")
    repo.commit("shared code refactor", files={"app/core/util.py": "X = 1\n"})
    result = repo.run_audit(CHECK, branch="refactor/base-cleanup")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WARN(shadow)" in result.stdout


def test_refactor_touching_tests_warns_shadow(repo: HarnessRepo) -> None:
    """Boundary rule: refactoring keeps existing tests green UNEDITED - a
    refactor branch editing tests/ gets a shadow warning (not yet a red)."""
    repo.branch("refactor/split-module")
    repo.commit(
        "refactor that edits a test",
        files={"tests/test_user.py": "def test_existing() -> None: ...  # moved\n"},
    )
    result = repo.run_audit(CHECK, branch="refactor/split-module")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "UNEDITED" in result.stdout


def test_refactor_local_change_has_no_shadow_warning(repo: HarnessRepo) -> None:
    repo.branch("refactor/rename-helper")
    repo.commit("local refactor", files={"app/services/x.py": "def x() -> None: ...\n"})
    result = repo.run_audit(CHECK, branch="refactor/rename-helper")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WARN(shadow)" not in result.stdout


def test_fix_branch_without_escape_path_fails(repo: HarnessRepo) -> None:
    repo.branch("fix/y")
    repo.commit(
        "bugfix with artifacts but no escape analysis",
        files={
            "app/services/user.py": "def existing() -> None: ...  # fixed\n",
            ".agents/context/artifacts/y/06-verify.md": "green",
            ".agents/context/artifacts/y/07-review.md": STAGE7_PASS,
            ".agents/context/decisions/y.md": "## 완료\n- 핵심 결정: 버그 수정\n",
        },
    )
    result = repo.run_audit(CHECK, branch="fix/y")
    assert result.returncode == 1
    assert "유출 경로" in result.stdout


def test_fix_branch_with_escape_path_passes(repo: HarnessRepo) -> None:
    repo.branch("fix/y")
    repo.commit(
        "bugfix with escape analysis",
        files={
            "app/services/user.py": "def existing() -> None: ...  # fixed\n",
            ".agents/context/artifacts/y/06-verify.md": "green",
            ".agents/context/artifacts/y/07-review.md": STAGE7_PASS,
            ".agents/context/decisions/y.md": (
                "## 완료\n- 핵심 결정: 버그 수정\n- 유출 경로: pipeline 외 기원 (수동 커밋)\n"
            ),
        },
    )
    result = repo.run_audit(CHECK, branch="fix/y")
    assert result.returncode == 0, result.stdout + result.stderr


# --- token presence is not a record (2026-07-26 first-port class) ------------
# Both checks used to be a bare `grep -q`: writing the required words satisfied
# them while the section stayed empty. Same defect class as 20-test-lock.sh's
# `override 사용` grep - the words are cheap, the content is the control.

def test_stage4_mutation_heading_without_body_fails(conformant_feat: HarnessRepo) -> None:
    conformant_feat.commit(
        "stage 4 artifact carries the phrase but no record",
        files={".agents/context/artifacts/x/04-tests.md": "## 뮤테이션 검증\n\n## 다음\n"},
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "뮤테이션 검증" in result.stdout


def test_stage4_mutation_record_with_body_passes(conformant_feat: HarnessRepo) -> None:
    conformant_feat.commit(
        "stage 4 artifact records the outcome",
        files={
            ".agents/context/artifacts/x/04-tests.md":
                "## 뮤테이션 검증\nN/A - 신규 프로덕션 코드 없음, 게이트 발화로 대체\n"
        },
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 0, result.stdout + result.stderr


def test_stage7_limits_section_without_body_fails(conformant_feat: HarnessRepo) -> None:
    empty_limits = STAGE7_PASS.replace(
        "## 검증하지 못한 것\n- 부하 상황의 동시성", "## 검증하지 못한 것\n"
    )
    assert empty_limits != STAGE7_PASS, "fixture changed - the limits section was not emptied"
    conformant_feat.commit(
        "stage 7 artifact with an empty limits section",
        files={".agents/context/artifacts/x/07-review.md": empty_limits},
    )
    result = conformant_feat.run_audit(CHECK, branch="feat/x")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "검증하지 못한 것" in result.stdout


# API_GATE_RE must catch every router-decorator shape without tripping on
# ordinary test decorators. `@router\.` used to match any attribute (so
# api_route/head/options were covered); a verb list alone would have lost them,
# and an unanchored name would make `@mock.patch(` fire the design gate.
@pytest.mark.parametrize(
    "line,expected",
    [
        ('@router.post("/x")', True),
        ('@api_router.get("/y")', True),
        ('@agent_router.post("/z")', True),
        ('@app.get("/")', True),
        ('@router.api_route("/b")', True),
        ('@router.head("/c")', True),
        # the old `@router\\.` matched ANY attribute - these must not be lost
        ('@app.websocket_route("/w")', True),
        ('@router.route("/r")', True),
        ('@router.options("/o")', True),
        ('@mock.patch("mod.fn")', False),
        ('@pytest.mark.parametrize("a", [1])', False),
        ('    x = router.get_thing()', False),
    ],
)
def test_api_gate_regex_matches_routers_only(line: str, expected: bool) -> None:
    m = re.search(r'^API_GATE_RE="(.*)"$', REPO_PROFILE, re.M)
    assert m, "API_GATE_RE not found in the repo profile"
    # run the REAL regex through grep -E, the way the audit does
    rc = subprocess.run(
        ["grep", "-qE", m.group(1)], input="+" + line + "\n", text=True
    ).returncode
    assert (rc == 0) is expected, f"{line!r} -> rc={rc}"


# --- bootstrap PR (the one that installs the harness) ------------------------
# Self-detected from the diff (adds .agents/workflow.md), not from a branch
# prefix - a prefix would be an opt-in bypass. Before this, the install PR was
# unpassable under every prefix: chore/* hard-failed on the deps+high-risk gate,
# feat/* on the missing lock marker, and audit-exempt waives neither.

def _bootstrap(repo: HarnessRepo, branch: str) -> None:
    repo.branch(branch)
    repo.commit(
        "install the harness",
        files={
            ".agents/workflow.md": "pipeline constitution\n",
            ".agents/context/repo-profile.sh": REPO_PROFILE,
            "pyproject.toml": '[project]\nname = "fixture"\ndependencies = ["ruff"]\n',
            "app/core/security.py": "def verify() -> None: ...\n",   # high-risk path
        },
    )


def test_bootstrap_pr_passes_on_a_chore_branch(repo: HarnessRepo) -> None:
    _bootstrap(repo, "chore/moru-init")
    result = repo.run_audit(CHECK, branch="chore/moru-init")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "bootstrap" in result.stdout


def test_bootstrap_pr_passes_on_a_feat_branch(repo: HarnessRepo) -> None:
    _bootstrap(repo, "feat/moru-init")
    result = repo.run_audit(CHECK, branch="feat/moru-init")
    assert result.returncode == 0, result.stdout + result.stderr


def test_bootstrap_waiver_needs_the_workflow_file(repo: HarnessRepo) -> None:
    """Only ADDING .agents/workflow.md earns the waiver - a chore branch that just
    touches deps and a high-risk path must still hard-fail."""
    repo.branch("chore/sneaky")
    repo.commit(
        "deps + high-risk change with no harness install",
        files={
            "pyproject.toml": '[project]\nname = "fixture"\ndependencies = ["ruff"]\n',
            "app/core/security.py": "def verify() -> None: ...\n",
        },
    )
    result = repo.run_audit(CHECK, branch="chore/sneaky")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "bootstrap" not in result.stdout
