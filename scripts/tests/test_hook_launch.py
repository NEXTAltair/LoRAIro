"""Execute the configured entrypoints on the current OS, from a subdirectory."""

import json
import os
import subprocess
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


if __name__ == "__main__":
    unittest.main()
