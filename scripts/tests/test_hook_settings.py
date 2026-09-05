"""Regression tests for hook settings missed by the previous validator."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate_hook_settings import validate_hook_settings


class HookSettingsTests(unittest.TestCase):
    def test_tracked_claude_settings_missing_exec_script_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".claude").mkdir()
            (root / ".claude/settings.json").write_text(
                json.dumps(
                    {
                        "hooks": {
                            "Stop": [
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "python",
                                            "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/missing.py"],
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(any("script not found" in error for error in validate_hook_settings(root)))

    def test_codex_unknown_event_and_legacy_command_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".codex").mkdir()
            (root / ".codex/hooks.json").write_text(
                json.dumps(
                    {
                        "hooks": {
                            "WorktreeCreate": [
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "/usr/bin/timeout 5s /workspaces/LoRAIro/hook.py",
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            errors = validate_hook_settings(root)
            self.assertTrue(any("unsupported Codex event" in error for error in errors))
            self.assertTrue(any("Linux-only" in error for error in errors))

    def test_malformed_handler_does_not_crash_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".claude").mkdir()
            (root / ".claude/settings.json").write_text(
                json.dumps({"hooks": {"Stop": [{"hooks": [None]}]}}), encoding="utf-8"
            )
            self.assertTrue(validate_hook_settings(root))


if __name__ == "__main__":
    unittest.main()
