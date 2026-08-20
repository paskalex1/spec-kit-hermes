"""Hermes Agent integration — skills-based agent.

Hermes Agent (https://github.com/NousResearch/hermes-agent) is an open-source
AI agent framework by Nous Research.  It stores skills in
``~/.hermes/skills/`` (user-global) rather than a project-local directory.

Usage::

    specify init my-project --integration hermes
    specify init --here --integration hermes
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

import yaml

from ..._assets import get_speckit_version
from ..base import IntegrationOption, SkillsIntegration, yaml_quote
from ..manifest import IntegrationManifest


class HermesIntegration(SkillsIntegration):
    """Integration for Hermes Agent skills.

    Hermes loads skills from ``~/.hermes/skills/`` (user home directory)
    rather than a project-local path.  Skills are installed directly to
    the global directory — no project-local copies are created since
    Hermes discovers them globally.  A project-local marker directory
    (``.hermes/skills/`` empty) is created so extension commands (e.g.
    git) can detect Hermes as an active integration.  Project uninstall
    removes only project-local artifacts; shared global skills have a
    separate infrastructure lifecycle.
    """

    key = "hermes"
    config = {
        "name": "Hermes Agent",
        "folder": ".hermes/",
        "commands_subdir": "skills",
        "install_url": "https://github.com/NousResearch/hermes-agent",
        "requires_cli": True,
    }
    registrar_config = {
        "dir": "~/.hermes/skills",
        "detect_dir": ".hermes/skills",
        "format": "markdown",
        "args": "$ARGUMENTS",
        "extension": "/SKILL.md",
    }

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _hermes_home_skills_dir() -> Path:
        """Return the active Hermes home's skills directory.

        Hermes sets ``HERMES_HOME`` for named profiles.  Honour that
        operator-process boundary so each profile receives its own managed
        skills and release manifest; fall back to the default ``~/.hermes``
        home when no profile override is active.
        """
        configured_home = os.environ.get("HERMES_HOME")
        if configured_home:
            hermes_home = Path(configured_home).expanduser()
            if not hermes_home.is_absolute():
                raise ValueError("HERMES_HOME must be an absolute path")
        else:
            hermes_home = Path.home() / ".hermes"
        return hermes_home / "skills"

    _DIR_FLAGS = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    _FILE_FLAGS = getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    _SECURE_DESCRIPTOR_MISSING = tuple(
        [
            function.__name__
            for function in (os.open, os.mkdir, os.stat, os.unlink, os.rmdir)
            if function not in os.supports_dir_fd
        ]
        + (
            []
            if os.stat in os.supports_follow_symlinks
            else ["stat(follow_symlinks=False)"]
        )
        + ([] if getattr(os, "O_NOFOLLOW", 0) else ["O_NOFOLLOW"])
        + ([] if getattr(os, "O_DIRECTORY", 0) else ["O_DIRECTORY"])
    )

    @staticmethod
    def _require_secure_descriptor_support() -> None:
        """Fail closed when the host cannot provide race-safe global writes.

        The hardened Hermes integration holds directory descriptors across
        preflight, creation, readback, and rollback.  Falling back to ordinary
        path operations would silently re-open the symlink/junction races this
        fork is intended to close, so unsupported platforms receive one clear
        error before any global directory or file is created.
        """
        if HermesIntegration._SECURE_DESCRIPTOR_MISSING:
            raise RuntimeError(
                "Hardened Hermes global skill installation requires secure "
                "descriptor-relative filesystem operations unavailable on "
                "this platform: "
                + ", ".join(HermesIntegration._SECURE_DESCRIPTOR_MISSING)
            )

    @classmethod
    def _open_directory_at(
        cls,
        parent_fd: int,
        name: str,
        display_path: Path,
        created_dirs: list[tuple[int, str, int, Path]],
        *,
        label: str = "Hermes global directory",
    ) -> int:
        """Open or create one directory component without following symlinks."""
        try:
            return os.open(name, cls._DIR_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            made_directory = False
            try:
                os.mkdir(name, mode=0o755, dir_fd=parent_fd)
                made_directory = True
            except FileExistsError:
                pass
            try:
                fd = os.open(name, cls._DIR_FLAGS, dir_fd=parent_fd)
            except OSError as exc:
                raise ValueError(
                    f"Refusing symlinked or invalid {label}: {display_path}"
                ) from exc
            if made_directory:
                created_dirs.append((parent_fd, name, fd, display_path))
            return fd
        except OSError as exc:
            raise ValueError(
                f"Refusing symlinked or invalid {label}: {display_path}"
            ) from exc

    @staticmethod
    def _read_fd(fd: int) -> bytes:
        os.lseek(fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)

    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write while installing Hermes global skill")
            view = view[written:]
        os.fsync(fd)

    @staticmethod
    def _same_open_object(parent_fd: int, name: str, fd: int) -> bool:
        try:
            path_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            return False
        open_stat = os.fstat(fd)
        return (
            path_stat.st_dev == open_stat.st_dev
            and path_stat.st_ino == open_stat.st_ino
        )

    def post_process_skill_content(self, content: str) -> str:
        """Disable project-controlled extension hooks in rendered Hermes skills."""
        rendered = super().post_process_skill_content(content)
        disabled = (
            "**Extension hooks are disabled in this hardened release.**\n"
            "Core stages do not execute commands from project-local extension "
            "configuration.\n\n"
        )
        for heading in (
            "Pre-Execution Checks",
            "Post-Execution Checks",
            "Mandatory Post-Execution Hooks",
        ):
            pattern = re.compile(
                rf"(?ms)^## {re.escape(heading)}\s*\n.*?(?=^## |\Z)"
            )
            rendered = pattern.sub(f"## {heading}\n\n{disabled}", rendered)
        rendered = re.sub(
            r"(?ms)^### 9\. Check for extension hooks\s*\n.*\Z",
            "### 9. Extension hooks\n\n" + disabled,
            rendered,
        )
        rendered = re.sub(
            r"(?m)^- \[ \] Extension hooks dispatched or skipped according "
            r"to the rules in Mandatory Post-Execution Hooks above\s*\n?",
            "",
            rendered,
        )
        rendered = rendered.replace(
            "**NOTE:** Branch creation is handled by the `before_specify` hook "
            "(git extension). Spec directory and file creation are always "
            "handled by this core command.",
            "**NOTE:** This hardened Hermes skill does not create or switch "
            "branches automatically. The operator must select the intended "
            "branch before running this stage. Spec directory and file creation "
            "remain part of the core command.",
        )
        return rendered

    # -- Options -----------------------------------------------------------

    @classmethod
    def options(cls) -> list[IntegrationOption]:
        return [
            IntegrationOption(
                "--skills",
                is_flag=True,
                default=True,
                help="Install as agent skills (default for Hermes Agent)",
            ),
        ]

    # -- Setup -------------------------------------------------------------

    def setup(
        self,
        project_root: Path,
        manifest: IntegrationManifest,
        parsed_options: dict[str, Any] | None = None,
        **opts: Any,
    ) -> list[Path]:
        """Install command templates as global Hermes skills.

        Writes each skill directly to
        ``~/.hermes/skills/speckit-<name>/SKILL.md`` where Hermes
        discovers them at runtime.  No project-local SKILL.md copies are
        created — the global directory is the single source of truth.
        A project-local marker (``.hermes/skills/`` empty) is created
        so extension commands (e.g. git) can detect Hermes as an active
        integration.
        """
        templates = self.list_command_templates()
        if not templates:
            return []

        self._require_secure_descriptor_support()

        # Safety check: verify manifest project_root matches (standard pattern)
        project_root_resolved = project_root.resolve()
        if manifest.project_root != project_root_resolved:
            raise ValueError(
                f"manifest.project_root ({manifest.project_root}) does not match "
                f"project_root ({project_root_resolved})"
            )

        script_type = opts.get("script_type", "sh")
        arg_placeholder = (
            self.registrar_config.get("args", "$ARGUMENTS")
            if self.registrar_config
            else "$ARGUMENTS"
        )

        global_skills_dir = self._hermes_home_skills_dir()
        hermes_home = global_skills_dir.parent
        release_dir = hermes_home / "spec-kit"

        candidates: list[tuple[Path, bytes]] = []

        for src_file in templates:
            raw = src_file.read_text(encoding="utf-8")

            # Derive the skill name from the template stem
            command_name = src_file.stem  # e.g. "plan"
            skill_name = f"speckit-{command_name.replace('.', '-')}"

            # Parse frontmatter for description. Locate the closing ``---`` on
            # its own line rather than with ``raw.split("---", 2)`` — a bare
            # substring split stops at the first ``---`` *anywhere*, including
            # one inside a value such as ``description: Separate sections
            # with ---``, which truncates the frontmatter and drops later keys.
            # The block between the delimiters is parsed unstripped so trailing
            # newlines in literal (``|``) block scalars survive.
            frontmatter: dict[str, Any] = {}
            if raw.startswith("---"):
                fm_lines = raw.splitlines(keepends=True)
                fm_close = next(
                    (
                        i
                        for i in range(1, len(fm_lines))
                        if fm_lines[i].rstrip() == "---"
                    ),
                    None,
                )
                if fm_close is not None:
                    try:
                        fm = yaml.safe_load("".join(fm_lines[1:fm_close]))
                        if isinstance(fm, dict):
                            frontmatter = fm
                    except yaml.YAMLError:
                        pass

            # Process body through the standard template pipeline
            processed_body = self.process_template(
                raw,
                self.key,
                script_type,
                arg_placeholder,
                invoke_separator=self.invoke_separator,
                project_root=project_root,
            )
            # Strip the processed frontmatter — we rebuild it for skills.
            # Scan for the closing ``---`` on its own line rather than
            # ``split("---", 2)`` so a ``---`` embedded in a value does not
            # truncate the frontmatter and spill it into the body.
            if processed_body.startswith("---"):
                body_lines = processed_body.splitlines(keepends=True)
                close_idx = next(
                    (
                        i
                        for i in range(1, len(body_lines))
                        if body_lines[i].rstrip() == "---"
                    ),
                    None,
                )
                if close_idx is not None:
                    # Keep whatever trails the ``---`` marker on the closing
                    # line so the body stays byte-for-byte identical to
                    # ``split("---", 2)[2]`` for well-formed templates.
                    processed_body = body_lines[close_idx][3:] + "".join(
                        body_lines[close_idx + 1 :]
                    )

            # Select description
            description = frontmatter.get("description", "")
            if not description:
                description = f"Spec Kit: {command_name} workflow"

            # Build SKILL.md with manually formatted frontmatter. yaml_quote
            # escapes newlines and control characters that a plain quoted
            # f-string cannot carry.
            skill_content = (
                f"---\n"
                f"name: {yaml_quote(skill_name)}\n"
                f"description: {yaml_quote(description)}\n"
                f"compatibility: "
                f"{yaml_quote('Requires spec-kit project structure with .specify/ directory')}\n"
                f"metadata:\n"
                f"  author: {yaml_quote('github-spec-kit')}\n"
                f"  source: {yaml_quote('templates/commands/' + src_file.name)}\n"
                f"---\n"
                f"{processed_body}"
            )

            skill_content = self.post_process_skill_content(skill_content)

            # Stage every expected global file in memory.  No target is
            # written until all existing targets pass the collision check.
            skill_dir = global_skills_dir / skill_name
            skill_file = skill_dir / "SKILL.md"
            normalized = skill_content.replace("\r\n", "\n")
            candidates.append((skill_file, normalized.encode("utf-8")))

        release_path = release_dir / "skills-v1.json"
        release_payload = {
            "schema_version": 1,
            "owner": "spec-kit-hermes",
            "spec_kit_version": get_speckit_version(),
            "skills": {
                skill_file.parent.name: {
                    "path": f"skills/{skill_file.parent.name}/SKILL.md",
                    "sha256": hashlib.sha256(expected).hexdigest(),
                }
                for skill_file, expected in sorted(
                    candidates, key=lambda candidate: candidate[0].parent.name
                )
            },
        }
        release_bytes = (
            json.dumps(release_payload, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        created: list[Path] = [skill_file for skill_file, _ in candidates]
        opened_fds: list[int] = []
        created_dirs: list[tuple[int, str, int, Path]] = []
        created_files: list[tuple[int, str, int, Path]] = []
        directory_records: list[tuple[int, str, int, Path]] = []
        file_records: list[tuple[int, str, int, Path, bytes]] = []

        def open_existing_file(
            parent_fd: int, name: str, path: Path, expected: bytes
        ) -> int | None:
            try:
                fd = os.open(name, os.O_RDONLY | self._FILE_FLAGS, dir_fd=parent_fd)
            except FileNotFoundError:
                return None
            except OSError as exc:
                raise ValueError(
                    f"Refusing symlinked Hermes global file: {path}"
                ) from exc
            opened_fds.append(fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise FileExistsError(f"Refusing non-regular Hermes global file {path}")
            if self._read_fd(fd) != expected:
                raise FileExistsError(f"Refusing to overwrite Hermes global file {path}")
            file_records.append((parent_fd, name, fd, path, expected))
            return fd

        def create_file(
            parent_fd: int, name: str, path: Path, expected: bytes
        ) -> int:
            try:
                fd = os.open(
                    name,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | self._FILE_FLAGS,
                    0o644,
                    dir_fd=parent_fd,
                )
            except FileExistsError as exc:
                raise FileExistsError(
                    f"Refusing raced or pre-existing Hermes global file {path}"
                ) from exc
            except OSError as exc:
                raise ValueError(f"Refusing unsafe Hermes global file {path}") from exc
            opened_fds.append(fd)
            # Register immediately after inode creation so partial write/close
            # failures are covered by rollback.
            created_files.append((parent_fd, name, fd, path))
            file_records.append((parent_fd, name, fd, path, expected))
            self._write_all(fd, expected)
            return fd

        try:
            home = Path.home()
            try:
                home_fd = os.open(home, self._DIR_FLAGS)
            except OSError as exc:
                raise ValueError(f"Refusing unsafe Hermes home directory: {home}") from exc
            opened_fds.append(home_fd)

            # Hold the project marker path by descriptor for the whole
            # transaction. This prevents a project-controlled `.hermes`
            # symlink (or a directory swap after preflight) from redirecting
            # marker creation outside the project. Any marker directories
            # created here participate in the same inode-aware rollback as
            # the global files below.
            project_anchor = Path(project_root_resolved.anchor)
            try:
                project_parent_fd = os.open(project_anchor, self._DIR_FLAGS)
            except OSError as exc:
                raise ValueError(
                    f"Refusing unsafe project path anchor: {project_anchor}"
                ) from exc
            opened_fds.append(project_parent_fd)
            project_current = project_anchor
            for project_part in project_root_resolved.parts[1:]:
                project_current = project_current / project_part
                project_fd = self._open_directory_at(
                    project_parent_fd,
                    project_part,
                    project_current,
                    created_dirs,
                    label="project directory",
                )
                opened_fds.append(project_fd)
                directory_records.append(
                    (project_parent_fd, project_part, project_fd, project_current)
                )
                project_parent_fd = project_fd
            project_fd = project_parent_fd
            marker_parent = project_root_resolved / ".hermes"
            marker_parent_fd = self._open_directory_at(
                project_fd,
                ".hermes",
                marker_parent,
                created_dirs,
                label="project-local Hermes marker directory",
            )
            opened_fds.append(marker_parent_fd)
            directory_records.append(
                (project_fd, ".hermes", marker_parent_fd, marker_parent)
            )
            marker_path = marker_parent / "skills"
            marker_fd = self._open_directory_at(
                marker_parent_fd,
                "skills",
                marker_path,
                created_dirs,
                label="project-local Hermes marker directory",
            )
            opened_fds.append(marker_fd)
            directory_records.append(
                (marker_parent_fd, "skills", marker_fd, marker_path)
            )

            if any(part in {".", ".."} for part in hermes_home.parts):
                raise ValueError(
                    f"Refusing non-canonical HERMES_HOME path: {hermes_home}"
                )
            try:
                hermes_parts = hermes_home.relative_to(home).parts
            except ValueError as exc:
                raise ValueError(
                    f"Refusing HERMES_HOME outside the user home: {hermes_home}"
                ) from exc
            if not hermes_parts:
                raise ValueError("Refusing to use the user home itself as HERMES_HOME")

            parent_fd = home_fd
            current_path = home
            for part in hermes_parts:
                current_path = current_path / part
                child_fd = self._open_directory_at(
                    parent_fd, part, current_path, created_dirs
                )
                opened_fds.append(child_fd)
                directory_records.append(
                    (parent_fd, part, child_fd, current_path)
                )
                parent_fd = child_fd
            hermes_fd = parent_fd

            skills_fd = self._open_directory_at(
                hermes_fd, "skills", global_skills_dir, created_dirs
            )
            opened_fds.append(skills_fd)
            directory_records.append((hermes_fd, "skills", skills_fd, global_skills_dir))

            release_fd = self._open_directory_at(
                hermes_fd, "spec-kit", release_dir, created_dirs
            )
            opened_fds.append(release_fd)
            directory_records.append((hermes_fd, "spec-kit", release_fd, release_dir))

            pending_skills: list[tuple[int, Path, bytes]] = []
            for skill_file, expected in candidates:
                skill_name = skill_file.parent.name
                skill_fd = self._open_directory_at(
                    skills_fd, skill_name, skill_file.parent, created_dirs
                )
                opened_fds.append(skill_fd)
                directory_records.append(
                    (skills_fd, skill_name, skill_fd, skill_file.parent)
                )
                existing_fd = open_existing_file(
                    skill_fd, "SKILL.md", skill_file, expected
                )
                if existing_fd is None:
                    pending_skills.append((skill_fd, skill_file, expected))

            release_existing_fd = open_existing_file(
                release_fd, "skills-v1.json", release_path, release_bytes
            )

            # All existing objects passed byte and type checks. Before creating
            # anything, prove every held path still names the same inode.
            for parent_fd, name, fd, path in directory_records:
                if (
                    not self._same_open_object(parent_fd, name, fd)
                    or not stat.S_ISDIR(os.fstat(fd).st_mode)
                ):
                    raise ValueError(
                        f"Hermes global directory changed during setup: {path}"
                    )
            for parent_fd, name, fd, path, expected in file_records:
                if (
                    not self._same_open_object(parent_fd, name, fd)
                    or not stat.S_ISREG(os.fstat(fd).st_mode)
                    or self._read_fd(fd) != expected
                ):
                    raise FileExistsError(
                        f"Hermes global file changed during setup: {path}"
                    )

            for skill_fd, skill_file, expected in pending_skills:
                create_file(skill_fd, "SKILL.md", skill_file, expected)
            if release_existing_fd is None:
                create_file(release_fd, "skills-v1.json", release_path, release_bytes)

            # Final readback uses the held descriptors and verifies that the
            # public paths still resolve to those exact objects.
            for parent_fd, name, fd, path in directory_records:
                if (
                    not self._same_open_object(parent_fd, name, fd)
                    or not stat.S_ISDIR(os.fstat(fd).st_mode)
                ):
                    raise ValueError(
                        f"Hermes global directory changed during setup: {path}"
                    )
            for parent_fd, name, fd, path, expected in file_records:
                if (
                    not self._same_open_object(parent_fd, name, fd)
                    or not stat.S_ISREG(os.fstat(fd).st_mode)
                    or self._read_fd(fd) != expected
                ):
                    raise FileExistsError(
                        f"Hermes global file failed final readback: {path}"
                    )
        except Exception as exc:
            rollback_errors: list[str] = []
            for parent_fd, name, fd, path in reversed(created_files):
                try:
                    if self._same_open_object(parent_fd, name, fd):
                        os.unlink(name, dir_fd=parent_fd)
                except OSError as rollback_exc:
                    rollback_errors.append(f"{path}: {rollback_exc}")
            for parent_fd, name, fd, path in reversed(created_dirs):
                try:
                    if self._same_open_object(parent_fd, name, fd):
                        os.rmdir(name, dir_fd=parent_fd)
                except OSError as rollback_exc:
                    rollback_errors.append(f"{path}: {rollback_exc}")
            if rollback_errors:
                exc.add_note(
                    "Hermes global rollback was incomplete: "
                    + "; ".join(rollback_errors)
                )
            raise
        finally:
            for fd in reversed(opened_fds):
                try:
                    os.close(fd)
                except OSError:
                    pass

        return created

    # -- Uninstall ---------------------------------------------------------

    @classmethod
    def _remove_project_marker_no_follow(cls, project_root: Path) -> None:
        """Remove an empty project marker without following replaced paths."""
        if (
            cls._SECURE_DESCRIPTOR_MISSING
            or os.listdir not in os.supports_fd
        ):
            return

        opened: list[int] = []
        try:
            project_fd = os.open(project_root, cls._DIR_FLAGS)
            opened.append(project_fd)
            try:
                hermes_fd = os.open(".hermes", cls._DIR_FLAGS, dir_fd=project_fd)
            except OSError:
                return
            opened.append(hermes_fd)
            try:
                skills_fd = os.open("skills", cls._DIR_FLAGS, dir_fd=hermes_fd)
            except OSError:
                return
            opened.append(skills_fd)

            if os.listdir(skills_fd):
                return
            if not cls._same_open_object(hermes_fd, "skills", skills_fd):
                return
            try:
                os.rmdir("skills", dir_fd=hermes_fd)
            except OSError:
                return

            if os.listdir(hermes_fd):
                return
            if not cls._same_open_object(project_fd, ".hermes", hermes_fd):
                return
            try:
                os.rmdir(".hermes", dir_fd=project_fd)
            except OSError:
                return
        except OSError:
            return
        finally:
            for fd in reversed(opened):
                try:
                    os.close(fd)
                except OSError:
                    pass

    def teardown(
        self,
        project_root: Path,
        manifest: IntegrationManifest,
        *,
        force: bool = False,
    ) -> tuple[list[Path], list[Path]]:
        """Uninstall only project-local Hermes integration files.

        Removes the project-local marker directory (if empty), delegates to
        ``manifest.uninstall()`` for project-local tracked files, and leaves
        shared global skills untouched.  Their lifecycle is an explicit
        infrastructure operation, not a project operation.
        """

        # Delegate to manifest for project-local tracked files (scripts,
        # templates, context entries tracked in the manifest).
        removed, skipped = manifest.uninstall(project_root, force=force)

        self._remove_project_marker_no_follow(project_root)

        return removed, skipped

    # -- CLI dispatch ------------------------------------------------------

    def build_exec_args(
        self,
        prompt: str,
        *,
        model: str | None = None,
        output_json: bool = True,
    ) -> list[str] | None:
        """Build Hermes CLI invocation for programmatic dispatch.

        Uses ``hermes chat -Q -q`` for one-shot queries in quiet mode,
        mapping slash-command invocations to the appropriate skill-based
        dispatch.
        """
        args = [self._resolve_executable(), "chat", "-Q"]

        # Operator-supplied SPECKIT_INTEGRATION_HERMES_EXTRA_ARGS go here —
        # after the base command but before Spec Kit's canonical -m/--json/-s/-q
        # flags — so they can't displace or clobber them (mirrors opencode).
        self._apply_extra_args_env_var(args)

        if model:
            args.extend(["-m", model])
        if output_json:
            args.append("--json")

        # If prompt starts with a slash command, pass it directly
        # so Hermes can dispatch to the appropriate skill.
        if prompt.startswith("/"):
            command, _, remainder = prompt[1:].partition(" ")
            if command:
                args.extend(["-s", command])
                if remainder:
                    args.extend(["-q", remainder])
            else:
                args.extend(["-q", prompt])
        else:
            args.extend(["-q", prompt])

        return args
