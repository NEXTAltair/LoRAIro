"""Migration removes higher-priority overrides and preserves each OS user home."""

import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import configure_agent_environment as settings
from validate_harness import validate_project_environment


class AgentEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
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
            config["shell_environment_policy"]["set"]["UV_PROJECT_ENVIRONMENT"], self.venv.as_posix()
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


if __name__ == "__main__":
    unittest.main()
