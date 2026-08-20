"""Tests for HermesIntegration.

Hermes is special among SkillsIntegration subclasses: it writes skills
to ``~/.hermes/skills/`` (global) rather than the project-local
``.hermes/skills/`` directory.  A project-local marker (empty directory)
is created so extension commands (e.g. git) can detect Hermes.

All tests that touch ``~/.hermes/`` use ``monkeypatch`` to isolate
``Path.home()`` to a temp directory so the test suite is hermetic and
non-destructive to a developer's real Hermes installation.
"""

from pathlib import Path

from specify_cli.integrations import get_integration
from specify_cli.integrations.manifest import IntegrationManifest

from .test_integration_base_skills import SkillsIntegrationTests


def _fake_home(tmp_path: Path) -> Path:
    """Create and return an isolated home directory under *tmp_path*."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return home


class TestHermesIntegration(SkillsIntegrationTests):
    KEY = "hermes"
    FOLDER = ".hermes/"
    COMMANDS_SUBDIR = "skills"
    REGISTRAR_DIR = "~/.hermes/skills"

    # -- Hermes-specific setup: skills go to ~/.hermes/skills/ -------------

    def test_setup_writes_to_global_skills_dir(self, tmp_path, monkeypatch):
        """Skills are written to ~/.hermes/skills/, not project-local."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        i = get_integration(self.KEY)
        m = IntegrationManifest(self.KEY, tmp_path)
        created = i.setup(tmp_path, m)
        skill_files = [f for f in created if "scripts" not in f.parts]

        assert len(skill_files) > 0, "No skill files were created"
        for f in skill_files:
            # Every skill file should be under ~/.hermes/skills/speckit-*/
            expected_prefix = str(home / ".hermes" / "skills")
            assert str(f).startswith(expected_prefix), (
                f"{f} is not under ~/.hermes/skills/"
            )

    def test_profile_home_override_writes_to_profile_skills(
        self, tmp_path, monkeypatch
    ):
        """Hermes profile processes install into their active HERMES_HOME."""
        home = _fake_home(tmp_path)
        profile_home = home / ".hermes" / "profiles" / "qwen"
        profile_home.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: home)
        monkeypatch.setenv("HERMES_HOME", str(profile_home))

        integration = get_integration(self.KEY)
        manifest = IntegrationManifest(self.KEY, tmp_path)
        created = integration.setup(tmp_path, manifest)

        skill_files = [path for path in created if path.name == "SKILL.md"]
        assert skill_files
        assert all(path.is_relative_to(profile_home / "skills") for path in skill_files)
        assert (profile_home / "spec-kit" / "skills-v1.json").is_file()
        assert not list((home / ".hermes" / "skills").glob("speckit-*"))

    def test_profile_home_override_rejects_relative_path(
        self, tmp_path, monkeypatch
    ):
        """A project-relative profile root cannot redirect global writes."""
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        monkeypatch.setenv("HERMES_HOME", "relative-profile")
        integration = get_integration(self.KEY)
        manifest = IntegrationManifest(self.KEY, tmp_path)

        with pytest.raises(ValueError, match="absolute path"):
            integration.setup(tmp_path, manifest)

    def test_profile_home_override_rejects_parent_traversal(
        self, tmp_path, monkeypatch
    ):
        """Lexical containment cannot be bypassed with a `..` component."""
        import pytest

        home = _fake_home(tmp_path)
        escaped = tmp_path / "escaped-hermes"
        monkeypatch.setattr(Path, "home", lambda: home)
        monkeypatch.setenv("HERMES_HOME", str(home / ".." / escaped.name))
        integration = get_integration(self.KEY)

        with pytest.raises(ValueError, match="non-canonical HERMES_HOME"):
            integration.setup(tmp_path, IntegrationManifest(self.KEY, tmp_path))

        assert not escaped.exists()
        assert not (tmp_path / ".hermes").exists()

    def test_profile_home_override_rejects_symlinked_component(
        self, tmp_path, monkeypatch
    ):
        """Descriptor traversal refuses symlinks inside a named profile path."""
        import pytest

        home = _fake_home(tmp_path)
        hermes_home = home / ".hermes"
        attacker = tmp_path / "attacker"
        hermes_home.mkdir()
        attacker.mkdir()
        try:
            (hermes_home / "profiles").symlink_to(attacker, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks are not available in this environment")
        profile_home = hermes_home / "profiles" / "qwen"
        monkeypatch.setattr(Path, "home", lambda: home)
        monkeypatch.setenv("HERMES_HOME", str(profile_home))
        integration = get_integration(self.KEY)
        manifest = IntegrationManifest(self.KEY, tmp_path)

        with pytest.raises(ValueError, match="symlinked or invalid Hermes global directory"):
            integration.setup(tmp_path, manifest)
        assert not list(attacker.rglob("SKILL.md"))

    def test_setup_writes_global_release_manifest(self, tmp_path, monkeypatch):
        """Global skills carry infrastructure owner, version, and SHA-256 evidence."""
        import hashlib
        import json

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)
        manifest = IntegrationManifest(self.KEY, tmp_path)

        created = integration.setup(tmp_path, manifest)

        release_path = home / ".hermes" / "spec-kit" / "skills-v1.json"
        release = json.loads(release_path.read_text(encoding="utf-8"))
        skill_files = sorted(path for path in created if path.name == "SKILL.md")
        assert release["schema_version"] == 1
        assert release["owner"] == "spec-kit-hermes"
        assert release["spec_kit_version"] == "0.16.4+hermes.1"
        assert set(release["skills"]) == {path.parent.name for path in skill_files}
        for path in skill_files:
            entry = release["skills"][path.parent.name]
            assert entry["path"] == f"skills/{path.parent.name}/SKILL.md"
            assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()

    def test_setup_is_idempotent_for_byte_identical_global_release(
        self, tmp_path, monkeypatch
    ):
        """A second project may reuse only the exact managed global release."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)
        first = integration.setup(
            tmp_path,
            IntegrationManifest(self.KEY, tmp_path),
        )
        release_path = home / ".hermes" / "spec-kit" / "skills-v1.json"
        before = {
            path: path.read_bytes()
            for path in [*first, release_path]
        }

        second_project = tmp_path / "second-project"
        second_project.mkdir()
        second = integration.setup(
            second_project,
            IntegrationManifest(self.KEY, second_project),
        )

        assert second == first
        assert all(path.read_bytes() == payload for path, payload in before.items())
        assert (second_project / ".hermes" / "skills").is_dir()

    def test_setup_refuses_modified_release_manifest_without_partial_writes(
        self, tmp_path, monkeypatch
    ):
        """Unknown release metadata cannot authorize otherwise identical skills."""
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)
        integration.setup(tmp_path, IntegrationManifest(self.KEY, tmp_path))
        release_path = home / ".hermes" / "spec-kit" / "skills-v1.json"
        release_path.write_bytes(b'{"owner":"attacker"}\n')
        second_project = tmp_path / "second-project"
        second_project.mkdir()

        with pytest.raises(FileExistsError, match="Refusing to overwrite"):
            integration.setup(
                second_project,
                IntegrationManifest(self.KEY, second_project),
            )

        assert release_path.read_bytes() == b'{"owner":"attacker"}\n'
        assert not (second_project / ".hermes" / "skills").exists()

    def test_setup_refuses_non_regular_skill_file(self, tmp_path, monkeypatch):
        """A directory named SKILL.md cannot be mistaken for a managed file."""
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        collision = home / ".hermes" / "skills" / "speckit-plan" / "SKILL.md"
        collision.mkdir(parents=True)
        integration = get_integration(self.KEY)

        with pytest.raises(FileExistsError, match="non-regular"):
            integration.setup(tmp_path, IntegrationManifest(self.KEY, tmp_path))

        assert collision.is_dir()
        assert not (home / ".hermes" / "spec-kit" / "skills-v1.json").exists()
        assert not (tmp_path / ".hermes" / "skills").exists()

    def test_setup_fails_cleanly_without_secure_descriptor_support(
        self, tmp_path, monkeypatch
    ):
        """Never downgrade global installation to race-prone path operations."""

        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)
        monkeypatch.setattr(
            type(integration),
            "_SECURE_DESCRIPTOR_MISSING",
            ("dir_fd",),
        )

        with pytest.raises(RuntimeError, match="secure descriptor-relative"):
            integration.setup(
                tmp_path,
                IntegrationManifest(self.KEY, tmp_path),
            )

        assert not (home / ".hermes").exists()
        assert not (tmp_path / ".hermes").exists()

    def test_setup_rolls_back_partial_release_manifest_write(
        self, tmp_path, monkeypatch
    ):
        """A partial manifest inode and every new skill are rolled back."""
        import os
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)
        manifest = IntegrationManifest(self.KEY, tmp_path)
        release_path = home / ".hermes" / "spec-kit" / "skills-v1.json"
        original_write_all = integration._write_all

        def partial_release_write(fd, payload):
            if payload.startswith(b"{\n"):
                os.write(fd, payload[:9])
                raise OSError("injected partial release manifest failure")
            original_write_all(fd, payload)

        monkeypatch.setattr(integration, "_write_all", partial_release_write)

        with pytest.raises(OSError, match="partial release manifest failure"):
            integration.setup(tmp_path, manifest)

        skills_root = home / ".hermes" / "skills"
        assert not list(skills_root.glob("speckit-*"))
        assert not release_path.exists()
        assert not (tmp_path / ".hermes" / "skills").exists()

    def test_setup_rolls_back_partial_skill_write(self, tmp_path, monkeypatch):
        """A skill inode is tracked for rollback before its first write."""
        import os
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)
        manifest = IntegrationManifest(self.KEY, tmp_path)
        original_write_all = integration._write_all
        failed = False

        def partial_skill_write(fd, payload):
            nonlocal failed
            if not failed and not payload.startswith(b"{\n"):
                failed = True
                os.write(fd, payload[:11])
                raise OSError("injected partial skill failure")
            original_write_all(fd, payload)

        monkeypatch.setattr(integration, "_write_all", partial_skill_write)

        with pytest.raises(OSError, match="partial skill failure"):
            integration.setup(tmp_path, manifest)

        assert not list((home / ".hermes" / "skills").glob("speckit-*"))
        assert not (home / ".hermes" / "spec-kit" / "skills-v1.json").exists()
        assert not (tmp_path / ".hermes" / "skills").exists()

    def test_setup_rejects_skill_inserted_after_preflight(self, tmp_path, monkeypatch):
        import os
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)
        original_open = os.open
        injected = False

        def raced_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal injected
            if path == "SKILL.md" and flags & os.O_CREAT and not injected:
                injected = True
                attacker_fd = original_open(
                    path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o644,
                    dir_fd=dir_fd,
                )
                os.write(attacker_fd, b"attacker-owned")
                os.close(attacker_fd)
            return original_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(os, "open", raced_open)
        with pytest.raises(FileExistsError, match="raced|pre-existing"):
            integration.setup(tmp_path, IntegrationManifest(self.KEY, tmp_path))

        attacker_files = list((home / ".hermes" / "skills").rglob("SKILL.md"))
        assert len(attacker_files) == 1
        assert attacker_files[0].read_bytes() == b"attacker-owned"
        assert not (home / ".hermes" / "spec-kit" / "skills-v1.json").exists()
        assert not (tmp_path / ".hermes" / "skills").exists()

    def test_setup_rejects_manifest_inserted_after_preflight(
        self, tmp_path, monkeypatch
    ):
        import os
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)
        original_open = os.open
        injected = False

        def raced_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal injected
            if path == "skills-v1.json" and flags & os.O_CREAT and not injected:
                injected = True
                attacker_fd = original_open(
                    path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o644,
                    dir_fd=dir_fd,
                )
                os.write(attacker_fd, b"attacker-manifest")
                os.close(attacker_fd)
            return original_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(os, "open", raced_open)
        with pytest.raises(FileExistsError, match="raced|pre-existing"):
            integration.setup(tmp_path, IntegrationManifest(self.KEY, tmp_path))

        assert not list((home / ".hermes" / "skills").glob("speckit-*"))
        release = home / ".hermes" / "spec-kit" / "skills-v1.json"
        assert release.read_bytes() == b"attacker-manifest"
        assert not (tmp_path / ".hermes" / "skills").exists()

    def test_setup_detects_existing_skill_replaced_during_commit(
        self, tmp_path, monkeypatch
    ):
        import os
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)
        integration.setup(tmp_path, IntegrationManifest(self.KEY, tmp_path))
        missing = home / ".hermes" / "skills" / "speckit-analyze" / "SKILL.md"
        victim = home / ".hermes" / "skills" / "speckit-plan" / "SKILL.md"
        missing.unlink()
        original_open = os.open
        injected = False

        def raced_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal injected
            if path == "SKILL.md" and flags & os.O_CREAT and not injected:
                injected = True
                victim.unlink()
                victim.write_bytes(b"raced replacement")
            return original_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(os, "open", raced_open)
        second = tmp_path / "second"
        second.mkdir()
        with pytest.raises(FileExistsError, match="final readback"):
            integration.setup(second, IntegrationManifest(self.KEY, second))

        assert victim.read_bytes() == b"raced replacement"
        assert not missing.exists(), "Installer-owned recreated skill was not rolled back"
        assert not (second / ".hermes" / "skills").exists()

    def test_setup_detects_skill_directory_replaced_by_symlink(
        self, tmp_path, monkeypatch
    ):
        import os
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)
        integration.setup(tmp_path, IntegrationManifest(self.KEY, tmp_path))
        skill_dir = home / ".hermes" / "skills" / "speckit-analyze"
        (skill_dir / "SKILL.md").unlink()
        renamed = skill_dir.with_name("speckit-analyze-held")
        outside = tmp_path / "outside-symlink-target"
        outside.mkdir()
        original_open = os.open
        injected = False

        def raced_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal injected
            if path == "SKILL.md" and flags & os.O_CREAT and not injected:
                injected = True
                skill_dir.rename(renamed)
                skill_dir.symlink_to(outside, target_is_directory=True)
            return original_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(os, "open", raced_open)
        second = tmp_path / "second"
        second.mkdir()
        with pytest.raises(ValueError, match="directory changed"):
            integration.setup(second, IntegrationManifest(self.KEY, second))

        assert list(outside.iterdir()) == []
        assert not (renamed / "SKILL.md").exists()
        assert not (second / ".hermes" / "skills").exists()

    def test_setup_rejects_symlinked_global_skills_root(
        self, tmp_path, monkeypatch
    ):
        """Project setup cannot redirect global writes through a skills symlink."""
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        hermes_home = home / ".hermes"
        hermes_home.mkdir()
        outside = tmp_path / "outside-skills"
        outside.mkdir()
        (hermes_home / "skills").symlink_to(outside, target_is_directory=True)

        integration = get_integration(self.KEY)
        manifest = IntegrationManifest(self.KEY, tmp_path)
        with pytest.raises(ValueError, match="symlink"):
            integration.setup(tmp_path, manifest)

        assert list(outside.iterdir()) == []
        assert not (hermes_home / "spec-kit" / "skills-v1.json").exists()
        assert not (tmp_path / ".hermes" / "skills").exists()

    def test_setup_rejects_symlinked_global_release_manifest(
        self, tmp_path, monkeypatch
    ):
        """A byte-identical external manifest cannot become trusted through a symlink."""
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)
        first_manifest = IntegrationManifest(self.KEY, tmp_path)
        integration.setup(tmp_path, first_manifest)

        release_path = home / ".hermes" / "spec-kit" / "skills-v1.json"
        outside = tmp_path / "outside-release.json"
        outside.write_bytes(release_path.read_bytes())
        release_path.unlink()
        release_path.symlink_to(outside)
        second_project = tmp_path / "second-project"
        second_project.mkdir()

        with pytest.raises(ValueError, match="symlink"):
            integration.setup(
                second_project,
                IntegrationManifest(self.KEY, second_project),
            )

        assert outside.read_bytes()
        assert release_path.is_symlink()
        assert not (second_project / ".hermes" / "skills").exists()

    def test_setup_refuses_modified_global_skill_without_partial_writes(
        self, tmp_path, monkeypatch
    ):
        """A global collision blocks setup before any other skill is written."""
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        global_skills = home / ".hermes" / "skills"
        existing = global_skills / "speckit-plan" / "SKILL.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("locally modified", encoding="utf-8")

        i = get_integration(self.KEY)
        m = IntegrationManifest(self.KEY, tmp_path)

        with pytest.raises(FileExistsError, match="Refusing to overwrite"):
            i.setup(tmp_path, m)

        assert existing.read_text(encoding="utf-8") == "locally modified"
        assert sorted(p.name for p in global_skills.glob("speckit-*")) == [
            "speckit-plan"
        ]
        assert not (tmp_path / ".hermes" / "skills").exists()

    def test_local_marker_dir_created(self, tmp_path, monkeypatch):
        """Project-local .hermes/skills/ should exist but be empty."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        i = get_integration(self.KEY)
        m = IntegrationManifest(self.KEY, tmp_path)
        i.setup(tmp_path, m)
        marker = tmp_path / ".hermes" / "skills"
        assert marker.is_dir(), "Marker directory was not created"
        # Should be empty (no SKILL.md files)
        children = list(marker.iterdir())
        assert children == [], f"Marker directory should be empty, got: {children}"

    def test_setup_rejects_symlinked_project_marker_without_global_writes(
        self, tmp_path, monkeypatch
    ):
        """A project marker cannot redirect setup outside the project root."""
        import pytest

        home = _fake_home(tmp_path)
        outside = tmp_path / "outside-marker"
        outside.mkdir()
        try:
            (tmp_path / ".hermes").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks are not available in this environment")
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)

        with pytest.raises(ValueError, match="project-local Hermes marker"):
            integration.setup(tmp_path, IntegrationManifest(self.KEY, tmp_path))

        assert list(outside.iterdir()) == []
        assert not (home / ".hermes").exists()

    def test_setup_rejects_non_directory_project_marker_without_global_writes(
        self, tmp_path, monkeypatch
    ):
        """A marker failure is inside the transaction, before global commit."""
        home = _fake_home(tmp_path)
        (tmp_path / ".hermes").write_text("not a directory", encoding="utf-8")
        monkeypatch.setattr(Path, "home", lambda: home)
        integration = get_integration(self.KEY)

        import pytest

        with pytest.raises(ValueError, match="project-local Hermes marker"):
            integration.setup(tmp_path, IntegrationManifest(self.KEY, tmp_path))

        assert (tmp_path / ".hermes").read_text(encoding="utf-8") == "not a directory"
        assert not (home / ".hermes").exists()

    # -- Override shared tests that assume project-local skills ------------

    def test_setup_writes_to_correct_directory(self, tmp_path, monkeypatch):
        """Override: Hermes writes to global, not project-local."""
        self.test_setup_writes_to_global_skills_dir(tmp_path, monkeypatch)

    def test_plan_skill_has_no_context_placeholder(self, tmp_path, monkeypatch):
        """The core plan skill must not carry a context-file placeholder —
        agent context files are owned by the opt-in agent-context extension."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        i = get_integration(self.KEY)
        m = IntegrationManifest(self.KEY, tmp_path)
        i.setup(tmp_path, m)
        # Find the plan skill in global ~/.hermes/skills/
        plan_file = home / ".hermes" / "skills" / "speckit-plan" / "SKILL.md"
        assert plan_file.exists(), f"Plan skill {plan_file} not created globally"
        content = plan_file.read_text(encoding="utf-8")
        assert "__CONTEXT_FILE__" not in content, (
            "Plan skill has unprocessed __CONTEXT_FILE__ placeholder"
        )

    def test_all_files_tracked_in_manifest(self, tmp_path, monkeypatch):
        """Override: Hermes does not track skills in the project manifest
        since they live globally.  Only project-local files (scripts,
        templates, context) are tracked."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        i = get_integration(self.KEY)
        m = IntegrationManifest(self.KEY, tmp_path)
        created = i.setup(tmp_path, m)
        for f in created:
            # Global files (in ~/.hermes/) are not tracked in manifest
            if str(f).startswith(str(home)):
                continue
            rel = f.resolve().relative_to(tmp_path.resolve()).as_posix()
            assert rel in m.files, f"{rel} not tracked in manifest"

    def test_install_uninstall_roundtrip(self, tmp_path, monkeypatch):
        """Project uninstall removes its marker but preserves shared global skills."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        i = get_integration(self.KEY)
        m = IntegrationManifest(self.KEY, tmp_path)
        created = i.install(tmp_path, m)
        assert len(created) > 0
        m.save()
        global_skill_files = [f for f in created if "SKILL.md" in str(f)]
        assert global_skill_files
        assert all(f.exists() for f in global_skill_files)

        removed, skipped = i.teardown(tmp_path, m, force=False)

        assert all(f.exists() for f in global_skill_files), (
            "A project teardown must not remove shared global Hermes skills"
        )
        assert not (tmp_path / ".hermes" / "skills").exists()
        assert not any(path in removed for path in global_skill_files)
        assert skipped == []

    def test_teardown_does_not_follow_swapped_project_marker(
        self, tmp_path, monkeypatch
    ):
        """A swapped `.hermes` symlink cannot redirect marker cleanup outside."""
        import pytest

        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        outside = tmp_path / "outside-teardown"
        outside_skills = outside / "skills"
        outside_skills.mkdir(parents=True)
        try:
            (tmp_path / ".hermes").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks are not available in this environment")

        integration = get_integration(self.KEY)
        manifest = IntegrationManifest(self.KEY, tmp_path)
        removed, skipped = integration.teardown(tmp_path, manifest, force=False)

        assert removed == []
        assert skipped == []
        assert outside_skills.is_dir()
        assert outside.is_dir()
        assert (tmp_path / ".hermes").is_symlink()

    def test_modified_file_survives_uninstall(self, tmp_path, monkeypatch):
        """A modified shared global skill survives project uninstall."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        i = get_integration(self.KEY)
        m = IntegrationManifest(self.KEY, tmp_path)
        created = i.install(tmp_path, m)
        m.save()
        # Pick a global skill file
        skill_files = [f for f in created if "SKILL.md" in str(f)]
        assert len(skill_files) > 0
        modified_file = skill_files[0]
        modified_file.write_text("user modified this", encoding="utf-8")
        removed, skipped = i.uninstall(tmp_path, m)
        assert modified_file.exists()
        assert modified_file.read_text(encoding="utf-8") == "user modified this"
        assert modified_file not in removed
        assert skipped == []

    def test_modified_global_skill_survives_teardown(self, tmp_path, monkeypatch):
        """The force flag cannot grant project teardown global ownership."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        i = get_integration(self.KEY)
        m = IntegrationManifest(self.KEY, tmp_path)
        created = i.install(tmp_path, m)
        m.save()
        # Pick a global skill file
        skill_files = [f for f in created if "SKILL.md" in str(f)]
        assert len(skill_files) > 0
        modified_file = skill_files[0]
        modified_file.write_text("user modified this", encoding="utf-8")
        removed, skipped = i.teardown(tmp_path, m, force=False)
        assert modified_file.exists()
        assert modified_file.read_text(encoding="utf-8") == "user modified this"
        assert modified_file not in removed
        assert skipped == []

    def test_pre_existing_skills_not_removed(self, tmp_path, monkeypatch):
        """Pre-existing non-speckit global skills should survive Hermes uninstall."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        i = get_integration(self.KEY)
        # Create a foreign skill in the global dir first
        global_skills_dir = i._hermes_home_skills_dir()
        foreign_dir = global_skills_dir / "other-tool"
        foreign_dir.mkdir(parents=True, exist_ok=True)
        (foreign_dir / "SKILL.md").write_text("# Foreign skill\n")

        m = IntegrationManifest(self.KEY, tmp_path)
        i.setup(tmp_path, m)

        # Run teardown to verify foreign skill survives uninstall
        i.teardown(tmp_path, m)

        assert (foreign_dir / "SKILL.md").exists(), (
            "Foreign skill was removed by teardown"
        )

    def test_hook_sections_explain_dotted_command_conversion(
        self, tmp_path, monkeypatch
    ):
        """Override: every rendered Hermes skill enforces hardened hook policy."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        i = get_integration(self.KEY)
        m = IntegrationManifest(self.KEY, tmp_path)
        created = i.setup(tmp_path, m)
        skill_files = [path for path in created if path.name == "SKILL.md"]
        assert skill_files
        for skill_file in skill_files:
            content = skill_file.read_text(encoding="utf-8")
            assert "EXECUTE_COMMAND:" not in content
            assert ".specify/extensions.yml" not in content
            assert "do not execute commands from project-local extension" in content
            assert "Extension hooks dispatched or skipped" not in content
            assert "Mandatory Post-Execution Hooks above" not in content
            assert "Branch creation is handled by the `before_specify` hook" not in content

    def test_complete_file_inventory_sh(self, tmp_path, monkeypatch):
        """Override: Hermes init produces no local SKILL.md files,
        only the empty .hermes/skills/ marker."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        from typer.testing import CliRunner
        from specify_cli import app

        project = tmp_path / f"inventory-sh-{self.KEY}"
        project.mkdir()
        old_cwd = Path.cwd()
        import os
        try:
            os.chdir(project)
            result = CliRunner().invoke(app, [
                "init", "--here", "--integration", self.KEY,
                "--script", "sh", "--ignore-agent-tools",
            ], catch_exceptions=False)
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0, f"init failed: {result.output}"
        actual = sorted(
            p.relative_to(project).as_posix()
            for p in project.rglob("*") if p.is_file()
        )
        # Ensure no core .hermes/skills/speckit-*/SKILL.md in project dir
        # (extension-installed skills like agent-context-update may appear)
        hermes_skill_files = [
            f for f in actual
            if f.startswith(".hermes/skills/speckit-")
            and "agent-context" not in f
        ]
        assert hermes_skill_files == [], (
            f"Expected no local core SKILL.md files, found: {hermes_skill_files}"
        )
        # Ensure the marker exists (empty dir won't appear in file listing)
        assert (project / ".hermes" / "skills").is_dir()

    def test_complete_file_inventory_ps(self, tmp_path, monkeypatch):
        """Override: Same as sh variant but for PowerShell script type."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        from typer.testing import CliRunner
        from specify_cli import app

        project = tmp_path / f"inventory-ps-{self.KEY}"
        project.mkdir()
        old_cwd = Path.cwd()
        import os
        try:
            os.chdir(project)
            result = CliRunner().invoke(app, [
                "init", "--here", "--integration", self.KEY,
                "--script", "ps", "--ignore-agent-tools",
            ], catch_exceptions=False)
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0, f"init failed: {result.output}"
        actual = sorted(
            p.relative_to(project).as_posix()
            for p in project.rglob("*") if p.is_file()
        )
        # Ensure no core .hermes/skills/speckit-*/SKILL.md in project dir
        # (extension-installed skills like agent-context-update may appear)
        hermes_skill_files = [
            f for f in actual
            if f.startswith(".hermes/skills/speckit-")
            and "agent-context" not in f
        ]
        assert hermes_skill_files == [], (
            f"Expected no local core SKILL.md files, found: {hermes_skill_files}"
        )
        assert (project / ".hermes" / "skills").is_dir()

    def test_install_uninstall_cleanup(self, tmp_path, monkeypatch):
        """Verify project cleanup preserves global skills and removes its marker."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        i = get_integration(self.KEY)
        m = IntegrationManifest(self.KEY, tmp_path)
        created = i.setup(tmp_path, m)

        # Verify global skills exist
        global_skills = [
            f for f in created
            if "SKILL.md" in str(f)
            and str(f).startswith(str(home / ".hermes"))
        ]
        assert len(global_skills) > 0
        for f in global_skills:
            assert f.exists()

        # Verify local marker exists
        assert (tmp_path / ".hermes" / "skills").is_dir()

        removed, skipped = i.teardown(tmp_path, m, force=False)

        # Shared global skills are outside project teardown ownership.
        for f in global_skills:
            assert f.exists(), f"{f} should survive project teardown"
            assert f not in removed
        assert skipped == []

        # Local marker removed
        assert not (tmp_path / ".hermes" / "skills").exists(), (
            "Local marker should be removed on teardown"
        )


class TestHermesInitFlow:
    """--integration hermes creates expected files."""

    def test_integration_hermes_creates_global_skills(self, tmp_path, monkeypatch):
        """--integration hermes should create global skills and a local marker."""
        home = _fake_home(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)

        from typer.testing import CliRunner
        from specify_cli import app

        runner = CliRunner()
        target = tmp_path / "test-proj"
        result = runner.invoke(app, [
            "init", str(target),
            "--integration", "hermes",
            "--ignore-agent-tools",
            "--script", "sh",
        ])

        assert result.exit_code == 0, f"init --integration hermes failed: {result.output}"
        # Skills should be in global ~/.hermes/skills/
        assert (home / ".hermes" / "skills" / "speckit-plan" / "SKILL.md").exists()
        # Local marker should exist
        assert (target / ".hermes" / "skills").is_dir()
        # No core SKILL.md files in project-local dir
        # (extension-installed skills like agent-context-update may appear)
        local_skills = [
            d for d in (target / ".hermes" / "skills").iterdir()
            if "agent-context" not in d.name
        ]
        assert local_skills == [], f"Local skills dir should be empty, got: {local_skills}"


class TestHermesBuildExecArgs:
    """CLI dispatch argv, including the operator extra-args env hook."""

    def test_build_exec_args_default_shape(self):
        i = get_integration("hermes")
        assert i.build_exec_args("/speckit-plan hi", output_json=True) == [
            "hermes", "chat", "-Q", "--json", "-s", "speckit-plan", "-q", "hi",
        ]

    def test_build_exec_args_honors_extra_args(self, monkeypatch):
        """SPECKIT_INTEGRATION_HERMES_EXTRA_ARGS is injected before the
        canonical -m/--json/-s/-q flags (same env hook as codex/opencode/
        devin; hermes previously skipped _apply_extra_args_env_var entirely).
        """
        monkeypatch.setenv(
            "SPECKIT_INTEGRATION_HERMES_EXTRA_ARGS", "--temperature 0.2"
        )
        i = get_integration("hermes")
        args = i.build_exec_args("/speckit-plan hi", output_json=True)
        assert args == [
            "hermes", "chat", "-Q", "--temperature", "0.2",
            "--json", "-s", "speckit-plan", "-q", "hi",
        ]
        # Injected before the canonical flags so it can't displace them.
        assert args.index("--temperature") < args.index("--json")
        assert args.index("--temperature") < args.index("-s")

    def test_build_exec_args_honors_executable_override(self, monkeypatch):
        monkeypatch.setenv(
            "SPECKIT_INTEGRATION_HERMES_EXECUTABLE", "/custom/hermes"
        )
        i = get_integration("hermes")
        assert i.build_exec_args("/speckit-plan hi")[0] == "/custom/hermes"
