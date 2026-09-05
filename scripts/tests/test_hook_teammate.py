"""Teammate completion checks resolve a nested payload cwd to its Git root."""

import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class TeammateHookTests(unittest.TestCase):
    def test_nested_payload_cwd_uses_worktree_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "src/lorairo"
            common = types.SimpleNamespace(
                find_project_root=lambda: root,
                find_shared_root=lambda path: root,
                get_log_dir=lambda path: path / ".claude/logs",
            )
            spec = importlib.util.spec_from_file_location(
                "teammate_under_test", ROOT / ".claude/hooks/hook_teammate_monitor.py"
            )
            module = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {"hook_common": common}):
                spec.loader.exec_module(module)
            with (
                patch.object(
                    sys,
                    "stdin",
                    io.StringIO(json.dumps({"cwd": str(nested), "hook_event_name": "TaskCompleted"})),
                ),
                patch.object(module.subprocess, "check_output", return_value=str(root)) as resolve,
                patch.object(module, "load_rules", return_value={"task_completed": {}}),
                patch.object(module, "handle_task_completed") as handle,
                patch.object(module, "log_debug"),
                self.assertRaises(SystemExit) as exited,
            ):
                module.main()
            self.assertEqual(exited.exception.code, 0)
            self.assertEqual(resolve.call_args.kwargs["cwd"], nested.resolve())
            self.assertEqual(module.PROJECT_DIR, root.resolve())
            handle.assert_called_once()


if __name__ == "__main__":
    unittest.main()
