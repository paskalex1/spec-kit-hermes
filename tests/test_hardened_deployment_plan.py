import re
from pathlib import Path

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


def test_live_rollout_covers_every_project_worker_profile():
    plan = PLAN.read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \|", plan, re.MULTILINE)
    roster_rows = rows[: len(PROJECT_WORKER_PROFILES)]

    assert dict(roster_rows) == PROJECT_WORKER_PROFILES
    assert len(roster_rows) == len(PROJECT_WORKER_PROFILES)
    assert len({home for _, home in roster_rows}) == len(PROJECT_WORKER_PROFILES)

    assert "A rollout is incomplete while any project-worker profile" in plan
    assert "New project-worker profiles" in plan


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
