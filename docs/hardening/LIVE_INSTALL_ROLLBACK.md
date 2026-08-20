# Hermes live installation and rollback

## Purpose

Deploy one pinned Spec Kit release to every Hermes profile that performs project work, while preserving profile isolation and proving that the shared workflow is actually usable across agents.

Skill installation is not policy enforcement by itself. The installed skills provide the common workflow tools; project-level `AGENTS.md`, the project constitution, explicit stage ownership, scoped task handoffs and acceptance gates remain the authorities that keep agents from drifting.

## Release identity

Install only an exact internal release from a wheel built from its immutable tagged fork commit. Record the commit, tree, tag, wheel path and wheel SHA-256 before touching any Hermes profile.

The published tag `v0.16.4+hermes.1` predates the complete project-worker rollout plan in this document. It is not eligible for LIVE installation. The replacement candidate is `v0.16.4+hermes.2`; qualify it as a new immutable internal release instead of moving or replacing the published tag.

Never install a branch, `main`, `HEAD`, a floating URL or a wheel whose hash differs from the settled release evidence.

## Frozen project-worker roster

The LIVE rollout covered by this plan has the following exact target roster:

| Profile | `HERMES_HOME` | Project role |
| --- | --- | --- |
| `default` | `/home/hermes/.hermes` | orchestrator and primary operator |
| `analyst` | `/home/hermes/.hermes/profiles/analyst` | analysis and clarification |
| `junior` | `/home/hermes/.hermes/profiles/junior` | bounded implementation tasks |
| `ops` | `/home/hermes/.hermes/profiles/ops` | operations and release work |
| `pm` | `/home/hermes/.hermes/profiles/pm` | planning and coordination |
| `qwen` | `/home/hermes/.hermes/profiles/qwen` | Veniamin / coding worker |
| `researcher` | `/home/hermes/.hermes/profiles/researcher` | research and specification support |
| `reviewer` | `/home/hermes/.hermes/profiles/reviewer` | independent analysis and review |
| `writer` | `/home/hermes/.hermes/profiles/writer` | documentary and editorial work |

A rollout is incomplete while any project-worker profile lacks the exact pinned release, even when that profile is currently stopped.

Before deployment, compare this roster with fresh `hermes profile list` output. Every additional profile must be explicitly classified as either:

- a project-worker profile, which must be added to the frozen roster and deployed in the same rollout; or
- excluded, with a recorded reason proving that it cannot receive project work.

Do not discover and mutate profiles dynamically during installation. Freeze and review the exact roster first.

New project-worker profiles must receive the same pinned Spec Kit release and pass the profile qualification gate before they receive project tasks.

## Machine-readable rollout contract

The following block is the executable policy surface used by regression tests. Narrative procedures below may add detail but must not weaken it.

```yaml
schema_version: 1
release:
  target_version: 0.16.4+hermes.2
  target_tag: v0.16.4+hermes.2
  superseded_tags:
    - v0.16.4+hermes.1
  move_or_replace_published_tags: false
  require_new_immutable_tag: true
profile_roster:
  default: /home/hermes/.hermes
  analyst: /home/hermes/.hermes/profiles/analyst
  junior: /home/hermes/.hermes/profiles/junior
  ops: /home/hermes/.hermes/profiles/ops
  pm: /home/hermes/.hermes/profiles/pm
  qwen: /home/hermes/.hermes/profiles/qwen
  researcher: /home/hermes/.hermes/profiles/researcher
  reviewer: /home/hermes/.hermes/profiles/reviewer
  writer: /home/hermes/.hermes/profiles/writer
installation:
  mode: sequential_one_profile_at_a_time
  stop_on_failure: true
  dynamic_profile_mutation: false
  non_target_profile_invariant: byte_identical
interrupted_install:
  reconcile_before_retry: true
  invalid_manifest_expected_source: qualified_wheel_disposable_render
  remove_only_exact_expected_bytes: true
protected_inventory:
  complete_recursive_path_set: true
  lstat_without_following_symlinks: true
  fields:
    - relative_path
    - object_type
    - mode_bits
    - uid
    - gid
    - size
    - sha256
    - symlink_target
  reject_added_or_removed_paths: true
rollback:
  required: true
  profile_order: reverse_installation_order
  verify_manifest_hash_before_delete: true
  unknown_or_modified_object_action: stop
shared_governance:
  documentary_stages:
    - constitution
    - specify
    - clarify
    - plan
    - tasks
    - analyze
  implement_separate: true
  junior_requires_tasks: true
  junior_requires_analyze_pass: true
  junior_post_analyze_smoke: true
```

## Preconditions

1. The corrected rollout plan is committed.
2. A new immutable internal release tag points to that exact clean commit.
3. The full test suite, wheel-contract tests and deterministic double-build pass on that tag.
4. The wheel SHA-256 matches settled release evidence.
5. The frozen target roster matches `hermes profile list`; no project-worker profile is omitted.
6. No target profile contains an unowned or locally modified `speckit-*` skill or conflicting `spec-kit/skills-v1.json`.
7. A pre-install inventory exists for the current CLI installation and every target profile.
8. A rollback backup exists for every pre-existing managed Spec Kit artifact.
9. Protected hashes and service state are recorded for config, memory, providers, OAuth, unrelated skills and each running gateway.
10. No LIVE installation, gateway restart or agent stage invocation begins without explicit LIVE authorization.

## Pre-install inventory and backup

For every target profile, record:

- profile name and absolute `HERMES_HOME`;
- whether `spec-kit/skills-v1.json` exists;
- every `skills/speckit-*/SKILL.md` path and SHA-256;
- a byte-preserving archive of those managed paths when any exist;
- the exact protected roots for config, memory, providers, OAuth and unrelated skills;
- the complete recursive path set beneath every protected root, collected with `lstat` semantics without following symlinks;
- relative path, object type, mode bits, UID and GID for every protected object, plus size and SHA-256 for every regular file and the exact link target for every symlink;
- gateway state when the profile has a running gateway.

Also record the current `specify` executable path, version and installation mechanism, or prove that it is absent.

Do not copy API keys, `.env`, OAuth files, session databases, private memory contents or unrelated skills into release evidence. Only their non-secret identity/hash inventory may be retained for pre/post comparison.

## Install

Install the exact qualified wheel once, never a branch or floating URL:

```bash
uv tool install --force /absolute/path/to/specify_cli-<release>-py3-none-any.whl
specify --version
```

Require the reported version to equal the release evidence before touching a profile.

Install and verify one profile at a time in the frozen roster order. Use a distinct disposable seed project for every profile:

```bash
HERMES_HOME=<absolute-profile-home> \
  specify init /tmp/spec-kit-<profile>-seed \
  --integration hermes --ignore-agent-tools --offline --script sh
```

For each profile:

1. Snapshot all non-target profiles immediately before installation.
2. Run the exact profile-scoped command.
3. Perform the complete per-profile verification gate below.
4. Prove all non-target profiles remain byte-identical.
5. Record a receipt before proceeding.

Do not continue to the next profile after any failed check. Preserve the failure receipt and determine whether to safely resume missing-only or roll back already changed profiles. Never repeat an uncertain profile installation without first reading its manifest and actual skill set.

### Interrupted or partial profile installation

Treat an interrupted command, timeout, missing result or partially written profile as unresolved execution identity. Do not rerun `specify init` and do not advance to another profile until the target profile has been reconciled against both its pre-install inventory and the exact qualified release.

1. If the current manifest is valid, verify every listed path and hash, then use the normal profile rollback procedure.
2. If the current manifest is absent or invalid, render the expected managed skill set from the qualified wheel into a separate disposable `HERMES_HOME`; never reconstruct expected bytes from memory or from the damaged profile.
3. For every expected managed path in the target profile, compare object type, path and SHA-256 with both the pre-install inventory and the disposable expected set.
4. A path that was absent before installation may be removed only when it is a regular file, remains contained in the target profile and is byte-identical to the expected file from the qualified wheel.
5. A path that existed before installation must be restored only from its byte-preserving pre-install backup.
6. If any candidate is modified, unknown, symlinked, non-regular or cannot be attributed uniquely to this release attempt, stop for manual reconciliation; never delete it merely because its name starts with `speckit-`.
7. Remove only now-empty managed directories, then prove the entire target profile matches its pre-install inventory and all non-target profiles remain byte-identical.
8. Record whether the failed attempt changed the shared CLI installation. Restore or remove the CLI only after all changed profiles have been reconciled.

Only after this receipt is settled may the operator resume missing-only or restart the rollout from the frozen roster.

Delete disposable seed projects only after their receipts have been settled. They are not production project state.

## Per-profile verification

For every target profile:

1. Read `spec-kit/skills-v1.json` from that exact `HERMES_HOME`.
2. Require `owner == "spec-kit-hermes"` and `spec_kit_version` equal to the qualified release.
3. Require the manifest path set to equal the actual `skills/speckit-*/SKILL.md` set.
4. Recompute every SHA-256 and require exact agreement with the manifest.
5. Confirm generated skills contain neither `EXECUTE_COMMAND:` nor `.specify/extensions.yml`.
6. Confirm all non-target profiles remain byte-identical outside their separately authorized installation step.
7. Confirm `hermes skills list` for that exact profile shows the pinned Spec Kit skills.
8. Start a fresh profile session and prove that an explicitly selected `speckit-*` skill is loaded from that profile rather than from another profile or stale session state.
9. Require exact structural equality with the pre-install protected inventory: the same complete path set, object types, mode bits, UID/GID, regular-file sizes and hashes, and symlink targets. Any added or removed protected path is a failure even when all surviving file hashes match.

A manifest-only check, directory listing or successful `specify init` is not sufficient profile qualification.

## Shared-governance acceptance

The common workflow is:

`constitution → specify → clarify → plan → tasks → analyze`

`implement` remains a separate explicit action after documentary qualification.

Use one disposable project to prove cross-profile artifact handoff with fresh sessions:

| Stage | Assigned profile | Required proof |
| --- | --- | --- |
| `constitution` | `default` | constitution artifact created and readable |
| `specify` | `researcher` | specification reads constitution and records its constraints |
| `clarify` | `analyst` | clarification reads the current specification and resolves open points |
| `plan` | `pm` | plan reads constitution, specification and clarification results |
| `tasks` | `junior` | tasks are derived from the qualified plan without implementation |
| `analyze` | `reviewer` | cross-artifact report covers constitution, specification, plan and tasks |

After this chain:

- `qwen` must load the pinned skills and read the complete qualified artifact chain without changing it;
- `writer` must load the pinned skills and identify the documentary source of truth without changing it;
- `ops` must load the pinned skills and verify release/evidence boundaries without modifying project artifacts;
- every stage receipt must identify the profile, skill, input artifacts, output artifact and commit/release identity;
- no human copy/paste may be used to transfer artifacts between stages.

The `junior` profile must not receive an implementation task until `tasks` exists, `analyze` has passed, and the handoff names the allowed files, required behavior and acceptance checks. Junior must not receive an open-ended instruction such as “continue the project” without a bounded stage and scope.

After the documentary chain passes, run one bounded post-`analyze` implementation smoke in the disposable project with a fresh `junior` session and the explicit `speckit-implement` skill. The smoke must execute exactly one harmless task already present in `tasks`, change only its declared disposable path, run its stated acceptance check and produce an exact diff receipt. This proves that junior consumes the qualified chain and remains inside scope; it does not authorize implementation in any real project.

Every real project using this contour must keep its own `AGENTS.md`, constitution and current SDD artifacts in the repository. Agent memory and globally installed skills are not substitutes for project-local authority.

## Overall rollout gate

The rollout is accepted only when:

1. every frozen project-worker profile passes the per-profile gate;
2. all manifests report the same release and identical managed-skill hashes;
3. the cross-profile documentary chain passes;
4. all protected pre/post inventories are structurally identical, including path sets, object types, modes, ownership, sizes, hashes and symlink targets;
5. running gateways remain healthy or any separately authorized refresh is verified;
6. no profile is left partially installed;
7. the settled evidence manifest is generated after all receipts stop changing.

If one profile fails, the result is `PARTIAL_SAFE` or `BROKEN`, never a successful rollout.

## Rollback

Rollback is an infrastructure operation, never `specify integration uninstall` from a project.

Roll back one profile at a time in reverse installation order:

1. Read the current profile manifest.
2. Before deleting anything, require every current managed skill byte to match its manifest SHA-256.
3. If any file differs, stop and preserve it for manual review; do not continue to another profile.
4. Remove only exact matching `SKILL.md` files listed by that manifest and their now-empty `speckit-*` directories.
5. Remove only the matching `spec-kit/skills-v1.json` and its now-empty directory.
6. Restore that profile's pre-install archive and previous manifest byte-for-byte, or leave the paths absent when the recorded pre-install state was absent.
7. Recompute hashes and compare with that profile's pre-install inventory.
8. Prove all other profiles remain byte-identical.

After all profiles are restored:

9. Reinstall the previous CLI package, or remove `specify-cli` when no previous installation existed.
10. Start fresh sessions for affected running profiles and confirm unrelated skills, config, gateway, memory, providers, OAuth and project files are unchanged.
11. Generate the settled rollback manifest last.

Stop or restart a gateway only when separately authorized and required to refresh loaded skills. A gateway refresh is not implicit in installation or rollback.

Never use recursive prefix deletion. Never delete a modified, unlisted, symlinked or non-regular object.
