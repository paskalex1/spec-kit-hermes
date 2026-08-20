# Upstream baseline

## Identity

- Upstream repository: https://github.com/github/spec-kit
- Upstream release: `v0.16.4`
- Upstream commit: `d1f50fcbe684a4222059c4ba7f2d7eabcca87402`
- Local branch: `hardened/v0.16.4`
- Local project: `/home/hermes/projects/spec-kit-hermes`
- Upstream remote: `https://github.com/github/spec-kit.git`

## Qualification before hardening

The following suites passed against an isolated v0.16.4 checkout before any fork changes:

- `tests/integrations/test_integration_hermes.py`
- `tests/test_workflows.py`
- `tests/integration/test_bundler_security_paths.py`
- `tests/test_authentication.py`

Result: `1148 passed, 1 skipped, 23 warnings` in `32.44s`.

The warnings came from temporary auth fixtures intentionally created with broad permissions. They do not describe the live Hermes credential files.

A clean baseline run is also being repeated in this local project before the first RED test.

## Known upstream policy conflicts

1. Hermes teardown recursively removes every global `~/.hermes/skills/speckit-*` directory regardless of ownership, hash or modification.
2. Hermes setup writes global skill files directly and has no global ownership manifest.
3. Workflow shell steps execute workflow-authored text through `subprocess.run(..., shell=True)` with the inherited process environment.
4. `specify workflow run` accepts direct local YAML paths without an operator trust gate specific to arbitrary execution.
5. Copilot prompt cleanup uses registry-derived command names without the containment check used by the primary cleanup path.
6. Core command templates can dispatch extension hooks; unreviewed extensions are outside the permitted deployment policy.

## Evidence source

Detailed v0.16.3→v0.16.4 comparison:

`/home/hermes/projects/hermes-infrastructure/spec-kit/audits/SPEC_KIT_V0163_V0164_COMPARISON.md`

## Evidence boundary

Upstream tests prove the behaviors encoded by upstream. They do not prove compliance with the Hermes hardened policy. No Spec Kit version has been installed into the live `~/.hermes/skills` contour as part of this fork bootstrap.
