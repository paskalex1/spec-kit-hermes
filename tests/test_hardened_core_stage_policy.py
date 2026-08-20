"""Hardened policy checks for the core documentary SDD stages."""

from pathlib import Path

import yaml


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "commands"
SPECKIT_WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "speckit" / "workflow.yml"
README = Path(__file__).resolve().parents[1] / "README.md"
CORE_STAGE_TEMPLATES = (
    "constitution.md",
    "specify.md",
    "clarify.md",
    "plan.md",
    "tasks.md",
    "analyze.md",
)


def test_required_core_stage_templates_remain_present():
    assert all((TEMPLATES_DIR / name).is_file() for name in CORE_STAGE_TEMPLATES)


def test_readme_get_started_preserves_canonical_documentary_chain():
    readme = README.read_text(encoding="utf-8")
    get_started = readme.split("## ⚡ Get Started", 1)[1].split(
        "## 📽️ Video Overview", 1
    )[0]
    commands = [
        "/speckit.constitution",
        "/speckit.specify",
        "/speckit.clarify",
        "/speckit.plan",
        "/speckit.tasks",
        "/speckit.analyze",
        "/speckit.implement",
    ]
    positions = [get_started.index(command) for command in commands]
    assert positions == sorted(positions)


def test_readme_classifies_canonical_stages_as_core_commands():
    readme = README.read_text(encoding="utf-8")
    core = readme.split("### Core Commands", 1)[1].split("### Optional Commands", 1)[0]
    optional = readme.split("### Optional Commands", 1)[1].split(
        "## 🔧 Specify CLI Reference", 1
    )[0]
    for command in ("/speckit.clarify", "/speckit.analyze"):
        assert command in core
        assert command not in optional


def test_bundled_workflow_is_exact_canonical_documentary_chain():
    payload = yaml.safe_load(SPECKIT_WORKFLOW.read_text(encoding="utf-8"))
    steps = payload["steps"]
    expected = [
        "constitution",
        "specify",
        "clarify",
        "plan",
        "tasks",
        "analyze",
    ]

    assert [step["id"] for step in steps] == expected
    assert [step["command"] for step in steps] == [
        f"speckit.{stage}" for stage in expected
    ]
    assert all(step.get("integration") == "{{ inputs.integration }}" for step in steps)
    assert all("type" not in step for step in steps)
    assert all(step["id"] != "implement" for step in steps)


def test_canonical_workflow_dispatches_strictly_in_order(tmp_path, monkeypatch):
    from specify_cli.workflows import STEP_REGISTRY
    from specify_cli.workflows.base import StepResult, StepStatus
    from specify_cli.workflows.engine import RunStatus, WorkflowEngine

    calls = []

    def record(config, _context):
        calls.append(config["command"])
        return StepResult(status=StepStatus.COMPLETED, output={})

    monkeypatch.setattr(STEP_REGISTRY["command"], "execute", record)
    engine = WorkflowEngine(tmp_path)
    definition = engine.load_workflow(SPECKIT_WORKFLOW)
    assert engine.validate(definition) == []
    state = engine.execute(
        definition,
        {"spec": "Build a safe test", "constitution": "", "integration": "auto"},
        run_id="canonical-order",
    )

    assert state.status is RunStatus.COMPLETED
    assert calls == [
        "speckit.constitution",
        "speckit.specify",
        "speckit.clarify",
        "speckit.plan",
        "speckit.tasks",
        "speckit.analyze",
    ]


def test_canonical_workflow_stops_after_failed_stage(tmp_path, monkeypatch):
    from specify_cli.workflows import STEP_REGISTRY
    from specify_cli.workflows.base import StepResult, StepStatus
    from specify_cli.workflows.engine import RunStatus, WorkflowEngine

    calls = []

    def fail_plan(config, _context):
        calls.append(config["command"])
        status = (
            StepStatus.FAILED
            if config["command"] == "speckit.plan"
            else StepStatus.COMPLETED
        )
        return StepResult(status=status, output={}, error="planned failure")

    monkeypatch.setattr(STEP_REGISTRY["command"], "execute", fail_plan)
    engine = WorkflowEngine(tmp_path)
    definition = engine.load_workflow(SPECKIT_WORKFLOW)
    state = engine.execute(
        definition,
        {"spec": "Build a safe test", "constitution": "", "integration": "auto"},
        run_id="canonical-stop",
    )

    assert state.status is RunStatus.FAILED
    assert calls == [
        "speckit.constitution",
        "speckit.specify",
        "speckit.clarify",
        "speckit.plan",
    ]


def test_canonical_command_steps_resolve_inputs_and_integration(tmp_path, monkeypatch):
    from specify_cli.workflows import STEP_REGISTRY
    from specify_cli.workflows.engine import RunStatus, WorkflowEngine

    calls = []

    def dispatch(command, integration, model, args, _context):
        calls.append((command, integration, model, args))
        return {"exit_code": 0, "stdout": "ok", "stderr": ""}

    monkeypatch.setattr(STEP_REGISTRY["command"], "_try_dispatch", dispatch)
    engine = WorkflowEngine(tmp_path)
    definition = engine.load_workflow(SPECKIT_WORKFLOW)
    state = engine.execute(
        definition,
        {
            "spec": "Resolved specification",
            "constitution": "Resolved constitution",
            "integration": "hermes",
        },
        run_id="canonical-resolved-inputs",
    )

    assert state.status is RunStatus.COMPLETED
    assert [call[0] for call in calls] == [
        "speckit.constitution",
        "speckit.specify",
        "speckit.clarify",
        "speckit.plan",
        "speckit.tasks",
        "speckit.analyze",
    ]
    assert all(call[1] == "hermes" for call in calls)
    assert calls[0][3] == "Resolved constitution"
    assert calls[1][3] == "Resolved specification"
    assert all(call[3] == "" for call in calls[2:])


def test_canonical_failed_stage_resumes_from_that_stage(tmp_path, monkeypatch):
    from specify_cli.workflows import STEP_REGISTRY
    from specify_cli.workflows.engine import RunStatus, WorkflowEngine

    first_calls = []

    def fail_plan(command, _integration, _model, _args, _context):
        first_calls.append(command)
        if command == "speckit.plan":
            return {"exit_code": 1, "stdout": "", "stderr": "planned failure"}
        return {"exit_code": 0, "stdout": "ok", "stderr": ""}

    command_step = STEP_REGISTRY["command"]
    monkeypatch.setattr(command_step, "_try_dispatch", fail_plan)
    engine = WorkflowEngine(tmp_path)
    definition = engine.load_workflow(SPECKIT_WORKFLOW)
    failed = engine.execute(
        definition,
        {"spec": "Resume test", "constitution": "", "integration": "hermes"},
        run_id="canonical-resume",
    )

    assert failed.status is RunStatus.FAILED
    assert first_calls[-1] == "speckit.plan"
    assert "speckit.tasks" not in first_calls

    resumed_calls = []

    def succeed(command, _integration, _model, _args, _context):
        resumed_calls.append(command)
        return {"exit_code": 0, "stdout": "ok", "stderr": ""}

    monkeypatch.setattr(command_step, "_try_dispatch", succeed)
    resumed = engine.resume("canonical-resume")

    assert resumed.status is RunStatus.COMPLETED
    assert resumed_calls == [
        "speckit.plan",
        "speckit.tasks",
        "speckit.analyze",
    ]
