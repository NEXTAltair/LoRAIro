"""Run UI generation in the shared environment, without syncing dependencies."""

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    data = json.load(sys.stdin)
    cwd = Path(data.get("cwd") or Path(__file__).resolve().parent.parent)
    root = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True, encoding="utf-8"
        ).strip()
    )
    common = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=root,
            text=True,
            encoding="utf-8",
        ).strip()
    ).parent
    environment = Path(os.environ.get("UV_PROJECT_ENVIRONMENT", str(common / ".venv")))
    if not environment.is_absolute():
        environment = common / environment
    interpreter = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not interpreter.is_file():
        print(f"UI hook: shared Python not found: {interpreter}", file=sys.stderr)
        return 1
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(
            str(root / part)
            for part in (
                "src",
                "local_packages/image-annotator-lib/src",
                "local_packages/genai-tag-db-tools/src",
            )
        ),
    )
    return subprocess.run(
        [str(interpreter), "-X", "utf8", str(root / "scripts/generate_ui.py")],
        cwd=root,
        env=env,
        stdout=sys.stderr,
        timeout=110,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
