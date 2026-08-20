# Hermes live installation and rollback

## Release identity

Install only the exact internal release `0.16.4+hermes.1` from a wheel built from the tagged fork commit. Record the commit, tag and wheel SHA-256 before touching either Hermes profile.

Target profiles:

- default: `/home/hermes/.hermes`
- qwen: `/home/hermes/.hermes/profiles/qwen`

The profiles are independent. Each must contain its own `skills/speckit-*` directories and `spec-kit/skills-v1.json` manifest.

## Preconditions

1. The worktree is frozen and clean at the internal tag.
2. The full test suite and wheel contract tests pass on that commit.
3. Neither profile contains an unowned or modified `speckit-*` skill.
4. A pre-install inventory and backup exist for both profiles and the current CLI installation.
5. The wheel SHA-256 matches the recorded release evidence.

## Backup

For each profile, record:

- whether `spec-kit/skills-v1.json` exists;
- every `skills/speckit-*/SKILL.md` path and SHA-256;
- a byte-preserving archive of those paths when any exist.

Do not copy API keys, `.env`, OAuth files, session databases or unrelated skills into the release evidence.

## Install

Install the exact local wheel, never a branch or floating URL:

```bash
uv tool install --force /absolute/path/to/specify_cli-0.16.4+hermes.1-py3-none-any.whl
specify --version
```

Seed the default profile from a disposable project:

```bash
HERMES_HOME=/home/hermes/.hermes \
  specify init /tmp/spec-kit-default-seed \
  --integration hermes --ignore-agent-tools
```

Seed the qwen profile independently:

```bash
HERMES_HOME=/home/hermes/.hermes/profiles/qwen \
  specify init /tmp/spec-kit-qwen-seed \
  --integration hermes --ignore-agent-tools
```

Delete the disposable seed projects after verification. They are not production project state.

## Verification

For each profile:

1. Read `spec-kit/skills-v1.json`.
2. Require `owner == "spec-kit-hermes"` and `spec_kit_version == "0.16.4+hermes.1"`.
3. Require the manifest skill set to equal the actual `skills/speckit-*/SKILL.md` set.
4. Recompute every SHA-256 and compare it to the manifest.
5. Confirm no file was created in the other profile by this install.
6. Confirm generated skills contain neither `EXECUTE_COMMAND:` nor `.specify/extensions.yml`.
7. Confirm `hermes skills list` and `hermes -p qwen skills list` show the Spec Kit skills.
8. Start fresh agent sessions and exercise the core documentary stages in a disposable project.

## Rollback

Rollback is an infrastructure operation, never `specify integration uninstall` from a project.

1. Stop or restart affected gateways only when required to refresh loaded skills.
2. Read the current profile manifest.
3. Before deleting anything, require every current managed skill byte to match its manifest SHA-256. If any file differs, stop and preserve it for manual review.
4. Remove only the exact matching `SKILL.md` files listed by that manifest and their now-empty `speckit-*` directories.
5. Remove only the matching `spec-kit/skills-v1.json` and its now-empty directory.
6. Restore the pre-install archive and previous manifest byte-for-byte, or leave the paths absent when the recorded pre-install state was absent.
7. Recompute hashes and compare with the pre-install inventory.
8. Reinstall the previous CLI package, or remove `specify-cli` when no previous installation existed.
9. Start fresh sessions and confirm unrelated skills, config, gateway, memory, OAuth and project files are unchanged.

Never use recursive prefix deletion. Never delete a modified, unlisted, symlinked or non-regular object.
