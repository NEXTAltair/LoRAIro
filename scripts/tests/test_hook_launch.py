"""Execute the configured entrypoints on the current OS, from a subdirectory."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class HookLaunchTests(unittest.TestCase):
    def test_configured_pretool_and_stop_commands(self):
        for provider, filename in (("claude", "settings.json"), ("codex", "hooks.json")):
            config = json.loads((ROOT / f".{provider}" / filename).read_text(encoding="utf-8"))
            for event in ("PreToolUse", "Stop"):
                for group in config["hooks"][event]:
                    for handler in group["hooks"]:
                        with self.subTest(provider=provider, event=event, command=handler):
                            if provider == "claude":
                                command = [
                                    handler["command"],
                                    *[
                                        value.replace("${CLAUDE_PROJECT_DIR}", str(ROOT))
                                        for value in handler["args"]
                                    ],
                                ]
                            elif os.name == "nt":
                                command = [
                                    "powershell",
                                    "-NoProfile",
                                    "-Command",
                                    handler["commandWindows"],
                                ]
                            else:
                                command = ["sh", "-c", handler["command"]]
                            payload = {
                                "hook_event_name": event,
                                "cwd": str(ROOT),
                                "tool_name": "Bash",
                                "tool_input": {"command": "git status"},
                                "last_assistant_message": "作業を確認しました。",
                                "stop_hook_active": True,
                            }
                            result = subprocess.run(
                                command,
                                input=json.dumps(payload),
                                text=True,
                                encoding="utf-8",
                                capture_output=True,
                                cwd=ROOT / "scripts",
                                timeout=20,
                                env=dict(os.environ, CLAUDE_PROJECT_DIR=str(ROOT)),
                            )
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertNotIn("Traceback", result.stderr)
                            self.assertNotIn("runtime unavailable", result.stderr)
                            self.assertNotIn("permissionDecision", result.stdout)


class FreshCheckoutTests(unittest.TestCase):
    """Exercise the downloaded pinned kit, not a mocked copy-layout installer."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.main = Path(cls.temporary.name) / "fresh project"
        cls.main.mkdir()
        cls.linked = Path(cls.temporary.name) / "linked worktree"
        for name in (
            "agent-harness.lock.json",
            ".agent-kit/hooks.lock.json",
            ".gitignore",
            ".claude/settings.json",
            ".codex/hooks.json",
            ".claude/hooks/hook_teammate_monitor.py",
            ".claude/hooks/rules/hook_teammate_rules.json",
            ".claude/hooks/rules/pre_commands.json",
        ):
            destination = cls.main / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        cls.git("init")
        cls.restore(cls.main)
        cls.git("add", ".")
        cls.git(
            "-c",
            "user.name=Harness Test",
            "-c",
            "user.email=harness@example.test",
            "commit",
            "-m",
            "fixture",
        )
        cls.git("worktree", "add", "-b", "test-linked", str(cls.linked))
        cls.restore(cls.linked)

    @classmethod
    def git(cls, *args):
        subprocess.run(["git", "-C", str(cls.main), *args], check=True, capture_output=True)

    @classmethod
    def restore(cls, target):
        subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(ROOT / "scripts/install_agent_harness.py"),
                "--target",
                str(target),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )

    def run_hook(self, root, event, command="git status"):
        config = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))
        handler = config["hooks"][event][0]["hooks"][0]
        nested = root / "nested"
        nested.mkdir(exist_ok=True)
        result = subprocess.run(
            [handler["command"], *handler["args"]],
            cwd=nested,
            input=json.dumps(
                {
                    "hook_event_name": event,
                    "cwd": str(self.main),
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                    "task_subject": "Fresh consumer task",
                }
            ),
            env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.main), AGENT_KIT_PROJECT_DIR=str(self.main)),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("runtime unavailable", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def test_fresh_and_linked_launch_without_copied_framework(self):
        self.assertFalse((self.linked / ".agent-kit/runtimes").exists())
        for root in (self.main, self.linked):
            self.assertFalse((root / ".claude/hooks/hook_common.py").exists())
            self.assertEqual(self.run_hook(root, "PreToolUse").stdout, "")
            self.run_hook(root, "TaskCreated")
            self.assertIn(
                "イベント受信: TaskCreated",
                (root / ".claude/logs/hook_teammate_monitor_debug.log").read_text(encoding="utf-8"),
            )

    def test_active_branch_overrides_with_stale_environment(self):
        path = self.linked / ".claude/hooks/rules/pre_commands.json"
        original = path.read_bytes()
        try:
            path.write_text(
                json.dumps(
                    {
                        "blocked_commands": [
                            {"pattern": "^echo branch-policy$", "reason": "ACTIVE BRANCH OVERRIDE"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_hook(self.linked, "PreToolUse", "echo branch-policy")
            self.assertIn("ACTIVE BRANCH OVERRIDE", result.stdout)
            self.assertEqual(self.run_hook(self.main, "PreToolUse", "echo branch-policy").stdout, "")
        finally:
            path.write_bytes(original)

    def test_documented_restore_is_not_redirected_to_syncing_uv(self):
        for root in (self.main, self.linked):
            result = self.run_hook(
                root, "PreToolUse", "python -X utf8 scripts/install_agent_harness.py"
            )
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
