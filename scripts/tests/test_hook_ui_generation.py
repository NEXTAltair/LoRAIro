"""UI hooks must use the shared interpreter and the active worktree source."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_ui
import hook_generate_ui


class UiGenerationHookTests(unittest.TestCase):
    def test_uic_uses_selected_python_without_shell_or_uv(self):
        with patch.object(generate_ui.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertTrue(generate_ui.check_pyside6_uic())
        command = run.call_args.args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[-1], "--version")
        self.assertNotIn("uv", command)
        self.assertNotIn("which", command)
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_uic_generation_preserves_paths_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="ui 日本語 ") as directory:
            ui = Path(directory) / "example widget.ui"
            ui.write_text("<ui/>", encoding="utf-8")
            output = ui.with_name("example widget_ui.py")
            output.write_text("def setupUi(self, Widget):\n    pass\n", encoding="utf-8")
            with patch.object(generate_ui.subprocess, "run") as run:
                run.return_value.returncode = 0
                self.assertTrue(generate_ui.generate_python_from_ui(ui))
            self.assertEqual(run.call_args.args[0][-3:], [str(ui), "-o", str(output)])
            self.assertEqual(run.call_args.args[0][0], sys.executable)
            self.assertFalse(run.call_args.kwargs.get("shell", False))
            self.assertIn("Widget: QWidget", output.read_text(encoding="utf-8"))

    def test_shared_interpreter_and_worktree_sources_without_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            main = Path(directory)
            worktree = main / ".agents/worktree/child"
            environment = main / ".venv"
            interpreter = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            interpreter.parent.mkdir(parents=True)
            interpreter.touch()
            with (
                patch.object(sys, "stdin", io.StringIO(json.dumps({"cwd": str(worktree)}))),
                patch.dict(os.environ, {"UV_PROJECT_ENVIRONMENT": str(environment)}),
                patch.object(
                    hook_generate_ui.subprocess,
                    "check_output",
                    side_effect=[str(worktree), str(main / ".git")],
                ),
                patch.object(hook_generate_ui.subprocess, "run") as run,
            ):
                run.return_value.returncode = 0
                self.assertEqual(hook_generate_ui.main(), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[0], str(interpreter))
            self.assertEqual(command[-1], str(worktree / "scripts/generate_ui.py"))
            self.assertEqual(run.call_args.kwargs["cwd"], worktree)
            self.assertEqual(
                run.call_args.kwargs["env"]["PYTHONPATH"].split(os.pathsep)[0], str(worktree / "src")
            )


if __name__ == "__main__":
    unittest.main()
