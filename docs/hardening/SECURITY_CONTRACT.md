# Hermes hardened security contract

## Goal

Preserve Spec Kit's core Spec-Driven Development semantics while preventing an individual project, workflow, extension or teardown operation from gaining unreviewed control over the shared Hermes user contour.

## Core behavior that must remain

1. Hermes discovers the pinned core Spec Kit skills.
2. The supported sequence remains:
   `constitution → specify → clarify → plan → tasks → analyze`.
3. Every stage reads the authoritative artifacts produced by earlier stages.
4. Constitution remains a live source of project rules for downstream stages.
5. Expected project templates and bundled helper scripts remain reproducible from the pinned release.
6. Errors remain visible and stop dependent stages.
7. No human copy/paste is required to hand artifacts from one core stage to the next.

## Required hardening

### Global Hermes skills

The hardened global installer requires descriptor-relative no-follow filesystem
operations (`dir_fd`, `O_NOFOLLOW`, and `O_DIRECTORY`). Platforms that cannot
provide this race-safe primitive fail closed before creating any global or
project-local artifact; the installer does not downgrade to ordinary path
writes. This limits the hardened Hermes global-install feature to supporting
hosts while leaving the rest of the upstream CLI's platform support unchanged.

`HermesIntegration.setup()` returns the managed skill files, matching the
upstream skills-integration API. The separately owned global release manifest
is deliberately not represented as a project-created result; its existence and
hashes are verified directly by the infrastructure lifecycle tests.

- A project teardown must never remove global Spec Kit skills.
- Setup must refuse to overwrite an unknown or locally modified global skill.
- Global skills must have explicit installation ownership, version and SHA-256 evidence before any managed upgrade or rollback.
- Global lifecycle is an infrastructure operation, not a project operation.

### Workflow execution

- Arbitrary workflow shell execution is denied by default.
- A project YAML file cannot enable shell execution by itself.
- If an explicit compatibility escape hatch is retained, only the operator process environment may enable it and the run must remain visibly marked unsafe.
- Core documentary SDD stages must not depend on arbitrary shell execution.

### Extensions and hooks

- Community extensions, presets, bundles and workflows are not installed automatically.
- Unreviewed extension hooks are default-deny.
- A mandatory hook declared by project files cannot override the operator security policy.
- Reviewed extensions require separate pinned source and integrity evidence.

### Paths and deletion

- Every deletion path derived from project or registry data must prove containment in its owned root.
- Path traversal, absolute paths, separator injection and symlink escapes must fail closed.
- Unknown or unowned files survive cleanup.
- Shared global Hermes skills are infrastructure-owned: locally modified global skills survive project teardown and block managed overwrite or upgrade until explicitly reconciled at infrastructure level.
- Project-local command artifacts recorded as owned by an installed preset or extension are generated files, not user documents. They are removed with that preset or extension even after local edits, so uninstall does not leave stale commands that reference removed components.
- User-authored commands must use a separate, unregistered name or path; users must not place durable custom work inside a generated preset/extension-owned artifact.

### Version governance

- Releases are installed only from explicit internal tags.
- No branch, `main`, `HEAD` or floating latest install is permitted.
- No project may upgrade or remove the shared Hermes integration.
- Upstream upgrades require diff audit, RED/GREEN security regression, upstream regression and disposable Hermes qualification.

## Hardened v0.16.4 implementation

- Upstream command templates remain byte-compatible for non-Hermes integrations.
- Hermes rendering replaces hook-only pre/post sections and the two terminal `### 9. Check for extension hooks` blocks with a non-executable disabled notice. Generated Hermes skills must contain neither `EXECUTE_COMMAND:` nor `.specify/extensions.yml`.
- The installer honours Hermes' absolute `HERMES_HOME` profile boundary. Default and named profiles therefore receive separate managed skill sets and separate release manifests; relative profile homes fail closed.
- Unsafe compatibility boundaries require exact operator-process opt-ins:
  - `SPECKIT_ALLOW_UNSAFE_LOCAL_WORKFLOW=1` for direct local YAML execution;
  - `SPECKIT_ALLOW_UNSAFE_SHELL=1` for shell steps;
  - `SPECKIT_ALLOW_UNSAFE_CUSTOM_STEPS=1` for project Python step imports.
- Direct local YAML execution and resume require the same exact local-workflow opt-in; persisted runs cannot bypass the gate.
- Local YAML, shell and custom Python opt-ins emit an explicit `UNSAFE COMPATIBILITY MODE` warning. Project files cannot set these gates before execution.
- Enabled shell steps inherit only a minimal execution environment allowlist plus `SPECKIT_WORKFLOW_DIR`; arbitrary host credentials and the operator opt-in variables are not forwarded to the child shell.
- Global Hermes skills are accompanied by `~/.hermes/spec-kit/skills-v1.json`, recording infrastructure owner, Spec Kit version, relative path and SHA-256 for every managed skill.
- Global installation uses held directory/file descriptors, no-follow opens, exclusive file creation, inode-identity checks, final byte readback and `fsync`. Unknown, modified, conflicting, raced, non-regular or symlinked skill/manifest paths fail closed.
- A failed skill or release-manifest write rolls back every inode created by that attempt, including partially written files, but never deletes a raced replacement it does not own.
- Project teardown never removes global Hermes skills or their release manifest.
- Project-local registered command files remain owned by their preset or extension for their entire lifecycle and are removed with that owner; this preserves complete uninstall semantics without adding a second command-hash registry.
- The bundled automatic workflow is exactly `constitution → specify → clarify → plan → tasks → analyze`; implementation remains a separate explicit action.

## Initial non-goals

- Rewriting Spec Kit from scratch.
- Building a general shell sandbox.
- Installing or supporting community extensions in the first hardened release.
- Automatically onboarding existing production projects.
- Triggering implementation automatically after analyze.
- Installing the fork into live Hermes before source and disposable qualification pass.

## Proof gates

1. RED tests fail on unmodified upstream v0.16.4 for the expected unsafe behavior.
2. Minimal implementation makes each test GREEN.
3. Existing upstream tests remain green or any deliberate compatibility change is explicitly documented and covered.
4. Static review finds no alternate bypass for each fixed boundary.
5. Disposable initialization creates only the documented files.
6. Hermes invokes core stages as actual skills and artifacts flow across stages.
7. Global rollback restores the pre-install manifest.
8. Gateway, config, memory, providers, OAuth and existing skills remain intact.
