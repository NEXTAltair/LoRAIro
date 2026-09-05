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
import hook_generate_ui


class UiGenerationHookTests(unittest.TestCase):
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
