"""Migration removes higher-priority overrides and preserves each OS user home."""

import ctypes
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import configure_agent_environment as settings
import private_backup
from validate_harness import validate_project_environment


class AgentEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        self.codex = self.root / "windows/.codex"
        self.claude = self.root / "windows/.claude"
        self.codex.mkdir(parents=True)
        self.claude.mkdir(parents=True)
        self.venv = self.project / ".venv"
        for relative in ("Scripts/python.exe", "bin/python"):
            path = self.venv / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        self.write(
            self.project / ".codex/config.toml",
            '[shell_environment_policy.set]\nUV_PROJECT_ENVIRONMENT = "H:/old/.venv"\nPORTABLE = "yes"\n',
        )
        self.write(
            self.project / ".claude/settings.local.json",
            json.dumps(
                {"env": {"UV_PROJECT_ENVIRONMENT": "/old/linux/.venv", "PORTABLE": "yes"}, "language": "ja"}
            ),
        )
        self.write(
            self.codex / "config.toml",
            '# personal preferences\nmodel = "personal"\n[shell_environment_policy.set]\nEXISTING = "keep"\n',
        )
        self.write(
            self.claude / "settings.json",
            json.dumps(
                {
                    "model": "personal",
                    "env": {"EXISTING": "keep"},
                    "permissions": {"allow": ["Bash(git *)"]},
                }
            ),
        )
        self.write(self.codex / "auth.json", "private fixture")
        self.write(self.codex / "history.jsonl", "history fixture")

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def configure(self, **kwargs):
        return settings.configure(
            self.project, self.venv, kwargs.get("codex", self.codex), kwargs.get("claude", self.claude)
        )

    def test_user_preferences_preserved_and_project_overrides_removed(self):
        self.assertTrue(validate_project_environment(self.project))
        original = Path.read_bytes
        reads = []

        def read(path):
            reads.append(path.name)
            return original(path)

        with patch.object(Path, "read_bytes", read):
            self.configure()
        config = tomllib.loads((self.codex / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["model"], "personal")
        self.assertEqual(config["shell_environment_policy"]["set"]["EXISTING"], "keep")
        self.assertEqual(
            config["shell_environment_policy"]["set"]["UV_PROJECT_ENVIRONMENT"],
            self.venv.resolve().as_posix(),
        )
        project = tomllib.loads((self.project / ".codex/config.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["shell_environment_policy"]["set"], {"PORTABLE": "yes"})
        local = json.loads((self.project / ".claude/settings.local.json").read_text(encoding="utf-8"))
        self.assertEqual(local, {"language": "ja", "env": {"PORTABLE": "yes"}})
        claude = json.loads((self.claude / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(claude["model"], "personal")
        self.assertEqual(claude["env"]["EXISTING"], "keep")
        self.assertEqual(claude["permissions"]["allow"], ["Bash(git *)"])
        self.assertNotIn("auth.json", reads)
        self.assertNotIn("history.jsonl", reads)
        self.assertEqual(validate_project_environment(self.project), [])

    def test_other_os_setup_and_repeat_install_do_not_overwrite_windows_home(self):
        self.configure()
        before = {
            path: path.read_bytes() for path in (self.codex / "config.toml", self.claude / "settings.json")
        }
        self.configure(codex=self.root / "linux/.codex", claude=self.root / "linux/.claude")
        self.configure()
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertTrue(any((self.codex / "lorairo-config-backups").iterdir()))
        self.assertTrue(any((self.claude / "lorairo-config-backups").iterdir()))

    def test_other_machine_paths_and_permissions_are_removed_from_project(self):
        own = self.root.as_posix() + "/tools/model"
        foreign = "/home/vscode/tools/model" if os.name == "nt" else "H:/tools/model"
        local = {
            "env": {"MODEL_DIR": own, "FOREIGN_DIR": foreign, "DOC_URL": "https://example.test/docs"},
            "permissions": {"allow": [f"Bash({own} *)", f"Bash({foreign} *)", "Bash(git *)"]},
        }
        self.write(self.project / ".claude/settings.local.json", json.dumps(local))
        self.configure()
        project = json.loads((self.project / ".claude/settings.local.json").read_text())
        self.assertEqual(project["env"], {"DOC_URL": "https://example.test/docs"})
        self.assertEqual(project["permissions"]["allow"], ["Bash(git *)"])
        user = json.loads((self.claude / "settings.json").read_text())
        self.assertEqual(user["env"]["MODEL_DIR"], own)
        self.assertNotIn("FOREIGN_DIR", user["env"])
        self.assertIn(f"Bash({own} *)", user["permissions"]["allow"])
        self.assertNotIn(f"Bash({foreign} *)", user["permissions"]["allow"])
        backups = list((self.claude / "lorairo-config-backups").glob("*-settings.local.json"))
        self.assertEqual(json.loads(backups[0].read_text()), local)

    def test_codex_additional_machine_environment_is_moved(self):
        own = self.root.as_posix() + "/cache"
        project = "[shell_environment_policy.set]\nCACHE_DIR=" + json.dumps(own) + "\n"
        self.write(self.project / ".codex/config.toml", project)
        self.configure()
        self.assertNotIn("CACHE_DIR", (self.project / ".codex/config.toml").read_text())
        user = tomllib.loads((self.codex / "config.toml").read_text())
        self.assertEqual(user["shell_environment_policy"]["set"]["CACHE_DIR"], own)

    def test_explicit_migration_preserves_active_sandbox_and_inheritance_preferences(self):
        self.write(
            self.project / ".codex/config.toml",
            'sandbox_mode="workspace-write"\n[shell_environment_policy]\ninherit="all"\n',
        )
        settings.configure(self.project, self.venv, self.codex, self.claude, migrate_codex_preferences=True)
        user = tomllib.loads((self.codex / "config.toml").read_text())
        self.assertEqual(user["sandbox_mode"], "workspace-write")
        self.assertEqual(user["shell_environment_policy"]["inherit"], "all")
        self.assertEqual(user["model"], "personal")

    def test_saved_legacy_config_migrates_after_tracked_file_replaced_it(self):
        # pull で追跡ファイルに置き換わった後でも、退避した旧設定から移行できる
        self.write(self.project / ".codex/config.toml", "# portable policy\n")
        saved = self.codex.parent / "saved-codex-config.toml"
        self.write(saved, 'sandbox_mode="danger-full-access"\n[shell_environment_policy]\ninherit="all"\n')
        settings.configure(self.project, self.venv, self.codex, self.claude, legacy_codex_config=saved)
        user = tomllib.loads((self.codex / "config.toml").read_text())
        self.assertEqual(user["sandbox_mode"], "danger-full-access")
        self.assertEqual(user["shell_environment_policy"]["inherit"], "all")

    def test_legacy_config_inside_checkout_is_rejected(self):
        inside = self.project / "saved.toml"
        self.write(inside, 'sandbox_mode="workspace-write"\n')
        with self.assertRaisesRegex(ValueError, "outside the shared"):
            settings.configure(self.project, self.venv, self.codex, self.claude, legacy_codex_config=inside)

    def test_shared_project_cannot_be_used_as_agent_home(self):
        with self.assertRaisesRegex(ValueError, "outside the shared"):
            self.configure(codex=self.project / ".codex")

    def test_invalid_project_fails_before_changing_user_config(self):
        before = (self.codex / "config.toml").read_bytes()
        self.write(self.project / ".codex/config.toml", "broken = [")
        with self.assertRaises(ValueError):
            self.configure()
        self.assertEqual((self.codex / "config.toml").read_bytes(), before)

    def test_shared_venv_interpreter_is_required(self):
        for path in self.venv.rglob("python*"):
            path.unlink()
        with self.assertRaisesRegex(ValueError, "interpreter is missing"):
            self.configure()

    def test_empty_project_environment_table_is_removed(self):
        cleaned = settings.rewrite_codex_environment(
            '[shell_environment_policy.set]\nUV_PROJECT_ENVIRONMENT="old"\n[features]\nexisting = true\n',
            {},
            project=True,
        )
        self.assertNotIn("shell_environment_policy.set", cleaned)
        self.assertTrue(tomllib.loads(cleaned)["features"]["existing"])

    def assert_private_file(self, path):
        if os.name == "nt":
            security = private_backup._windows_security()
            handle = security.kernel.CreateFileW(str(path), 0x00020000, 7, None, 3, 0x80, None)
            self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
            try:
                security.verify_handle(handle, directory=False)
            finally:
                security.kernel.CloseHandle(handle)
        else:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_settings_and_backups_are_private_before_first_write(self):
        created = []
        original_open = settings.open_private_file

        def open_verified(path):
            stream = original_open(path)
            private_backup.validate_private_directory(path.parent)
            self.assertEqual(stream.tell(), 0)
            if os.name == "nt":
                import msvcrt

                private_backup._windows_security().verify_handle(
                    msvcrt.get_osfhandle(stream.fileno()), directory=False
                )
            else:
                self.assertEqual(stat.S_IMODE(os.fstat(stream.fileno()).st_mode), 0o600)
            created.append(path)
            return stream

        with patch.object(settings, "open_private_file", side_effect=open_verified):
            self.configure()
            new = self.codex / "new-settings.json"
            settings.write_preserving_backup(
                new, '{"fixture":"opaque"}', self.codex / "lorairo-config-backups"
            )
        self.assertGreaterEqual(len(created), 9)
        for path in (self.codex / "config.toml", self.claude / "settings.json", new):
            self.assert_private_file(path)
        for home in (self.codex, self.claude):
            for backup in (home / "lorairo-config-backups").iterdir():
                self.assert_private_file(backup)
        self.assertFalse(list(self.project.rglob(".lorairo-settings-*")))

    def test_legacy_broad_root_is_preserved_and_private_sibling_reused(self):
        root = self.codex / "lorairo-config-backups"
        root.mkdir()
        if os.name != "nt":
            root.chmod(0o755)
        legacy = root / "original.toml"
        legacy.write_bytes(b"legacy fixture")
        before = (legacy.read_bytes(), legacy.stat().st_mtime_ns, root.stat().st_mode)
        destination = self.codex / "config.toml"
        original = destination.read_bytes()
        settings.write_preserving_backup(destination, 'model = "new"\n', root)
        private = root.with_name(root.name + "-private")
        private_backup.validate_private_directory(private)
        backups = {path: path.read_bytes() for path in private.iterdir()}
        self.assertEqual(list(backups.values()), [original])
        settings.write_preserving_backup(destination, 'model = "new"\n', root)
        self.assertEqual(len(list(private.iterdir())), 1)
        settings.write_preserving_backup(destination, 'model = "newer"\n', root)
        self.assertEqual(len(list(private.iterdir())), 2)
        for path, data in backups.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(before, (legacy.read_bytes(), legacy.stat().st_mtime_ns, root.stat().st_mode))

    def test_existing_backup_collision_preserves_both_files(self):
        destination = self.codex / "config.toml"
        original = destination.read_bytes()
        root = self.codex / "lorairo-config-backups"
        settings.create_private_directory(root)
        identifier = hashlib.sha256(str(destination.resolve()).encode()).hexdigest()[:16]
        digest = hashlib.sha256(original).hexdigest()[:16]
        backup = root / f"{identifier}-{digest}-fixed-{destination.name}"
        backup.write_bytes(b"unfinished prior backup")
        with patch.object(settings.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed")):
            with self.assertRaises(FileExistsError):
                settings.write_preserving_backup(destination, "new", root)
        self.assertEqual(destination.read_bytes(), original)
        self.assertEqual(backup.read_bytes(), b"unfinished prior backup")

    def test_root_links_and_non_directory_backups_are_refused(self):
        destination = self.codex / "config.toml"
        original = destination.read_bytes()
        root = self.codex / "lorairo-config-backups"
        root.write_bytes(b"consumer-owned file")
        with self.assertRaises(PermissionError):
            settings.write_preserving_backup(destination, "new", root)
        self.assertEqual(root.read_bytes(), b"consumer-owned file")
        root.unlink()
        with patch.object(settings, "filesystem_link", side_effect=lambda path: path == root):
            with self.assertRaises(PermissionError):
                settings.write_preserving_backup(destination, "new", root)
        self.assertEqual(destination.read_bytes(), original)

    def test_existing_staging_collision_is_never_cleaned(self):
        path = self.codex / "new.json"
        stage = path.parent / ".lorairo-settings-fixed"
        stage.mkdir()
        consumer = stage / "notes"
        consumer.write_bytes(b"unsaved work")
        with patch.object(settings.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed")):
            with self.assertRaises(FileExistsError):
                settings.write_preserving_backup(path, "new", self.codex / "lorairo-config-backups")
        self.assertEqual(consumer.read_bytes(), b"unsaved work")
        self.assertFalse(path.exists())

    def test_existing_replacement_collision_is_never_cleaned(self):
        path = self.codex / "new.json"
        original_open = settings.open_private_file
        preserved = []

        def colliding(output):
            output.write_bytes(b"consumer-owned collision")
            preserved.append(output)
            return original_open(output)

        with patch.object(settings, "open_private_file", side_effect=colliding):
            with self.assertRaises(FileExistsError):
                settings.write_preserving_backup(path, "new", self.codex / "lorairo-config-backups")
        self.assertFalse(path.exists())
        self.assertEqual(preserved[0].read_bytes(), b"consumer-owned collision")

    def test_unsafe_private_fallback_preserves_all_existing_files(self):
        root = self.codex / "lorairo-config-backups"
        fallback = root.with_name(root.name + "-private")
        for directory in (root, fallback):
            directory.mkdir()
            if os.name != "nt":
                directory.chmod(0o755)
        consumer = fallback / "pending"
        consumer.write_bytes(b"existing fallback work")
        path = self.codex / "config.toml"
        before = path.read_bytes()
        with self.assertRaises(PermissionError):
            settings.write_preserving_backup(path, "new", root)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(consumer.read_bytes(), b"existing fallback work")
        self.assertEqual(list(root.iterdir()), [])

    def test_failed_replacement_preserves_original_and_backup_and_removes_stage(self):
        path = self.codex / "config.toml"
        original = path.read_bytes()
        backup_root = self.codex / "lorairo-config-backups"
        with patch.object(settings.os, "replace", side_effect=OSError("fixture replace failure")):
            with self.assertRaisesRegex(OSError, "fixture replace failure"):
                settings.write_preserving_backup(path, "new", backup_root)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual([p.read_bytes() for p in backup_root.iterdir()], [original])
        self.assertFalse(list(path.parent.glob(".lorairo-settings-*")))

    def test_interrupted_staging_paths_are_gitignored(self):
        fixture = self.root / "git-fixture"
        subprocess.run(["git", "init", str(fixture)], capture_output=True, check=True)
        (fixture / ".gitignore").write_bytes((settings.ROOT / ".gitignore").read_bytes())
        paths = [
            ".codex/.lorairo-settings-fixture/config.toml",
            ".claude/.lorairo-settings-fixture/settings.json",
        ]
        result = subprocess.run(
            ["git", "-C", str(fixture), "check-ignore", "--no-index", "--stdin", "-z"],
            input=("\0".join(paths) + "\0").encode(),
            capture_output=True,
            check=True,
        )
        self.assertEqual(result.stdout.decode().split("\0")[:-1], paths)

    def test_linked_sources_are_rejected_before_planning_reads(self):
        before = (self.codex / "config.toml").read_bytes()
        for location in (self.codex, self.project / ".claude/settings.local.json"):
            with (
                self.subTest(location=location.name),
                patch.object(
                    settings, "filesystem_link", side_effect=lambda path, linked=location: path == linked
                ),
                patch.object(
                    Path, "read_text", side_effect=AssertionError("No configuration should be read")
                ),
            ):
                with self.assertRaises(PermissionError):
                    self.configure()
        self.assertEqual((self.codex / "config.toml").read_bytes(), before)
        self.assertFalse((self.codex / "lorairo-config-backups").exists())

    def test_failed_partial_stage_write_is_cleaned_and_original_preserved(self):
        path = self.codex / "config.toml"
        before = path.read_bytes()
        root = self.codex / "lorairo-config-backups"
        original_open = settings.open_private_file

        class PartialWriter:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def write(self, content):
                self.stream.write(content[:2])
                raise OSError("fixture partial-write failure")

            def __exit__(self, *_args):
                self.stream.close()

        def fail_on_stage(output):
            stream = original_open(output)
            return PartialWriter(stream) if output.parent.name.startswith(".lorairo-settings-") else stream

        with patch.object(settings, "open_private_file", side_effect=fail_on_stage):
            with self.assertRaisesRegex(OSError, "fixture partial-write failure"):
                settings.write_preserving_backup(path, "new values", root)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual([p.read_bytes() for p in root.iterdir()], [before])
        self.assertFalse(list(path.parent.glob(".lorairo-settings-*")))

    def test_unc_paths_and_posix_permission_grammar_are_distinct(self):
        for value, expected in (
            (r"\\server\share\models", "nt"),
            ("//server/share/models", "nt"),
            (r"\\?\UNC\server\share\models", "nt"),
            (r'Bash("\\server\share\python.exe" *)', "nt"),
            ('Bash("//server/share/python.exe" *)', "nt"),
            ("Read(//workspaces/LoRAIro/**)", "posix"),
            ("Edit(//home/vscode/project/**)", "posix"),
            ("Bash(/workspaces/LoRAIro/.venv/bin/python *)", "posix"),
            ("https://server/share/models", None),
            ("Bash(git *)", None),
        ):
            with self.subTest(value=value):
                self.assertEqual(settings.path_platform(value), expected)

    def test_unc_environment_and_permissions_migrate_only_to_windows(self):
        unc = r"\\server\share\models"
        local = {
            "env": {"MODEL_DIR": unc, "CACHE_DIR": "//server/share/cache"},
            "permissions": {"allow": [f"Bash({unc} *)", "Read(//workspaces/LoRAIro/**)", "Bash(git *)"]},
        }
        self.write(self.project / ".claude/settings.local.json", json.dumps(local))
        self.assertTrue(validate_project_environment(self.project))
        self.configure()
        self.assertEqual(validate_project_environment(self.project), [])
        user = json.loads((self.claude / "settings.json").read_text())
        if os.name == "nt":
            self.assertEqual(user["env"]["MODEL_DIR"], unc)
            self.assertEqual(user["env"]["CACHE_DIR"], "//server/share/cache")
            self.assertIn(f"Bash({unc} *)", user["permissions"]["allow"])
            self.assertNotIn("Read(//workspaces/LoRAIro/**)", user["permissions"]["allow"])
        else:
            self.assertNotIn("MODEL_DIR", user["env"])
            self.assertNotIn("CACHE_DIR", user["env"])
            self.assertIn("Read(//workspaces/LoRAIro/**)", user["permissions"]["allow"])


if __name__ == "__main__":
    unittest.main()
