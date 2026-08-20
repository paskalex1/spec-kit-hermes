import re
from pathlib import Path

import pytest

PLAN = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "hardening"
    / "LIVE_INSTALL_ROLLBACK.md"
)
PROJECT_WORKER_PROFILES = {
    "default": "/home/hermes/.hermes",
    "analyst": "/home/hermes/.hermes/profiles/analyst",
    "junior": "/home/hermes/.hermes/profiles/junior",
    "ops": "/home/hermes/.hermes/profiles/ops",
    "pm": "/home/hermes/.hermes/profiles/pm",
    "qwen": "/home/hermes/.hermes/profiles/qwen",
    "researcher": "/home/hermes/.hermes/profiles/researcher",
    "reviewer": "/home/hermes/.hermes/profiles/reviewer",
    "writer": "/home/hermes/.hermes/profiles/writer",
}
REQUIRED_HEADINGS = (
    "Purpose",
    "Release identity",
    "Frozen project-worker roster",
    "Preconditions",
    "Pre-install inventory and backup",
    "Install",
    "Per-profile verification",
    "Shared-governance acceptance",
    "Overall rollout gate",
    "Rollback",
)


def _section(plan: str, heading: str) -> str:
    marker = f"## {heading}\n"
    assert plan.count(marker) == 1
    body = plan.split(marker, 1)[1]
    return body.split("\n## ", 1)[0]


def _validate_structure(plan: str) -> None:
    headings = tuple(re.findall(r"^## (.+)$", plan, re.MULTILINE))
    assert headings == REQUIRED_HEADINGS

    release = _section(plan, "Release identity")
    assert "`v0.16.4+hermes.1`" in release
    assert "not eligible for LIVE installation" in release
    assert "new immutable internal release" in release
    assert "instead of moving or replacing the published tag" in release

    rollback = _section(plan, "Rollback")
    assert "Roll back one profile at a time in reverse installation order" in rollback
    assert "If any file differs, stop" in rollback
    assert "Prove all other profiles remain byte-identical" in rollback
    assert "Generate the settled rollback manifest last" in rollback


def _validate_roster(plan: str) -> None:
    roster = _section(plan, "Frozen project-worker roster")
    rows = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \|", roster, re.MULTILINE)

    assert dict(rows) == PROJECT_WORKER_PROFILES
    assert len(rows) == len(PROJECT_WORKER_PROFILES)
    assert len({home for _, home in rows}) == len(PROJECT_WORKER_PROFILES)
    assert "A rollout is incomplete while any project-worker profile" in roster
    assert "New project-worker profiles" in roster
    assert "Do not discover and mutate profiles dynamically" in roster


def _validate_protected_inventory(plan: str) -> None:
    inventory = _section(plan, "Pre-install inventory and backup")
    verification = _section(plan, "Per-profile verification")
    overall = _section(plan, "Overall rollout gate")

    assert "complete recursive path set" in inventory
    assert "object type" in inventory
    assert "mode bits" in inventory
    assert "UID and GID" in inventory
    assert "SHA-256 for every regular file" in inventory
    assert "without following symlinks" in inventory
    assert "exact structural equality" in verification
    assert "added or removed protected path" in verification
    assert "all protected pre/post inventories are structurally identical" in overall


def test_live_rollout_plan_structure_and_immutable_release_policy():
    _validate_structure(PLAN.read_text(encoding="utf-8"))


def test_live_rollout_covers_exact_project_worker_roster():
    _validate_roster(PLAN.read_text(encoding="utf-8"))


def test_live_rollout_keeps_profile_installation_isolated_and_fail_fast():
    plan = PLAN.read_text(encoding="utf-8")

    assert "Install and verify one profile at a time" in plan
    assert "Do not continue to the next profile after any failed check" in plan
    assert "all non-target profiles remain byte-identical" in plan
    assert "Interrupted or partial profile installation" in plan
    assert "absent or invalid" in plan
    assert "byte-identical to the expected file from the qualified wheel" in plan


def test_live_rollout_proves_shared_governance_not_only_skill_presence():
    plan = PLAN.read_text(encoding="utf-8")

    assert "Skill installation is not policy enforcement by itself" in plan
    assert "constitution → specify → clarify → plan → tasks → analyze" in plan
    assert "The `junior` profile must not receive an implementation task" in plan
    assert "`analyze` has passed" in plan
    assert "bounded post-`analyze` implementation smoke" in plan


def test_live_rollout_records_structural_protected_invariants():
    _validate_protected_inventory(PLAN.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("mutation", "validator"),
    [
        (
            lambda plan: plan.replace(
                "| `writer` | `/home/hermes/.hermes/profiles/writer` |",
                "| `writer` | `/home/hermes/.hermes/profiles/writer` |\n"
                "| `rogue` | `/home/hermes/.hermes/profiles/rogue` |",
            ),
            _validate_roster,
        ),
        (
            lambda plan: plan.replace("## Rollback\n", "## Removed rollback\n"),
            _validate_structure,
        ),
        (
            lambda plan: plan.replace(
                "not eligible for LIVE installation",
                "eligible for LIVE installation",
            ),
            _validate_structure,
        ),
        (
            lambda plan: plan.replace("complete recursive path set", "selected paths"),
            _validate_protected_inventory,
        ),
    ],
)
def test_contract_tests_reject_materially_weakened_plan(mutation, validator):
    plan = PLAN.read_text(encoding="utf-8")

    with pytest.raises(AssertionError):
        validator(mutation(plan))
