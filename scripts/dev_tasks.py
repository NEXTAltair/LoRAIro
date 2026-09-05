"""Portable development tasks; ordinary commands never synchronize dependencies."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, NamedTuple, TypedDict

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("image-annotator-lib", "genai-tag-db-tools")
SAFE_MARKERS = "not downloads_and_runs_model and not calls_real_webapi"


class TaskSpec(NamedTuple):
    """Declare prerequisites independently of command selection.

    Only ``sync`` may write the shared environment, and only from main.
    ``packages`` identifies required checkouts, not installed dependencies.
    ``imports_source`` enables worktree source precedence for application code.
    """

    runtime: Literal["stdlib", "shared", "sync"]
    packages: tuple[str, ...] = ()
    imports_source: bool = False
    headless: bool = False


TASKS = {
    "install": TaskSpec("sync", PACKAGES),
    "install-dev": TaskSpec("sync", PACKAGES),
    "test": TaskSpec("shared", PACKAGES, imports_source=True, headless=True),
    "test-iam-lib": TaskSpec("shared", (PACKAGES[0],), imports_source=True, headless=True),
    "test-genai-tag": TaskSpec("shared", (PACKAGES[1],), imports_source=True, headless=True),
    "test-all": TaskSpec("shared", PACKAGES, imports_source=True, headless=True),
    "lint": TaskSpec("shared"),
    "mypy": TaskSpec("shared", PACKAGES, imports_source=True),
    "format": TaskSpec("shared"),
    "format-iam-lib": TaskSpec("shared", (PACKAGES[0],)),
    "format-genai-tag": TaskSpec("shared", (PACKAGES[1],)),
    "run-gui": TaskSpec("shared", PACKAGES, imports_source=True),
    "test-runtime-local": TaskSpec("shared", (PACKAGES[0],), imports_source=True, headless=True),
    "test-runtime-webapi": TaskSpec("shared", (PACKAGES[0],), imports_source=True, headless=True),
    "generate-ui": TaskSpec("shared"),
    "adr-drift": TaskSpec("stdlib"),
    "adr-index": TaskSpec("stdlib"),
    "adr-okf": TaskSpec("stdlib"),
    "docs-okf": TaskSpec("stdlib"),
}


class Command(TypedDict):
    """JSON-compatible execution plan, also consumed by explicit cleanup."""

    argv: list[str]
    cwd: str
    env: dict[str, str]


def git(root: Path, *args: str) -> str:
    """Read git metadata without changing the checkout."""
    return subprocess.check_output(["git", "-C", str(root), *args], encoding="utf-8").strip()


def shared_root(root: Path) -> Path:
    """Find the main checkout, including when called inside a linked worktree."""
    common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    if common.name != ".git":
        raise ValueError("Expected a normal Git checkout with a shared .git directory.")
    return common.parent.resolve()


def environment_python(venv: Path) -> Path:
    """Select the platform's Python path without resolving Linux venv symlinks."""
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def resolve_shared_environment(root: Path, env: Mapping[str, str], *, require_python: bool = True) -> Path:
    """Validate the explicitly configured environment against the main checkout."""
    expected = shared_root(root) / ".venv"
    configured = env.get("UV_PROJECT_ENVIRONMENT")
    if configured is not None:
        supplied = Path(configured)
        if not supplied.is_absolute() or supplied.resolve() != expected.resolve():
            raise ValueError(
                f"UV_PROJECT_ENVIRONMENT must be the absolute shared path {expected}; "
                f"received {configured!r}. Correct the shell/session configuration first."
            )
    interpreter = environment_python(expected)
    if require_python and not interpreter.is_file():
        raise ValueError(
            f"Shared Python is missing: {interpreter}. From {expected.parent}, initialize "
            "submodules (git submodule update --init --recursive), then run "
            "python scripts/dev_tasks.py install-dev."
        )
    return expected


def check_submodules(root: Path, packages: tuple[str, ...] = PACKAGES) -> None:
    """Validate only selected package checkouts, without fetching any sources."""
    if not packages:
        return
    paths = [f"local_packages/{name}" for name in packages]
    status = git(root, "submodule", "status", "--recursive", "--", *paths)
    missing = [
        name for name in packages if not (root / "local_packages" / name / "pyproject.toml").is_file()
    ]
    if missing or any(line.startswith(("-", "U")) for line in status.splitlines()):
        raise ValueError(
            "Local packages are missing or conflicted. Resolve conflicts and run "
            f'git -C "{root}" submodule update --init --recursive explicitly.'
        )


def build_plan(task: str, root: Path, base_env: Mapping[str, str]) -> list[Command]:
    """Build validated commands and a small, non-secret environment overlay."""
    if task not in TASKS:
        raise ValueError(f"Unknown task: {task}")
    root = root.resolve()
    spec = TASKS[task]
    # A stdlib task must not even inspect Git/uv/venv configuration. Its own
    # script owns any tool-specific checks (e.g. ADR drift's optional Git use).
    if spec.runtime == "stdlib":
        return runtime_plan(task, root, {}, Path(sys.executable))
    installing = spec.runtime == "sync"
    if installing and root != shared_root(root):
        raise ValueError("Dependency installation is only allowed from the main checkout, not a worktree.")
    venv = resolve_shared_environment(root, base_env, require_python=not installing)
    check_submodules(root, spec.packages)
    overlay = {"UV_PROJECT_ENVIRONMENT": str(venv)}
    if spec.imports_source:
        overlay["PYTHONPATH"] = os.pathsep.join(
            str(p)
            for p in [root / "src", *[root / "local_packages" / name / "src" for name in spec.packages]]
        )
    if spec.headless:
        overlay["QT_QPA_PLATFORM"] = "offscreen"
    if installing:
        args = ["uv", "sync"] + (
            ["--dev", "--all-packages", "--all-groups"] if task == "install-dev" else []
        )
        return [{"argv": args, "cwd": str(root), "env": overlay}]
    overlay["UV_PYTHON_DOWNLOADS"] = "never"
    interpreter = environment_python(venv)
    overlay["VIRTUAL_ENV"] = str(venv)
    overlay["PATH"] = os.pathsep.join([str(interpreter.parent), base_env.get("PATH", os.defpath)])
    return runtime_plan(task, root, overlay, interpreter)


def runtime_plan(task: str, root: Path, overlay: dict[str, str], interpreter: Path) -> list[Command]:
    """Keep package-local command selection separate from environment validation."""
    # The selected interpreter runs installed tools directly. No project
    # discovery, environment creation, resolution, or implicit synchronization.
    prefix = [str(interpreter), "-X", "utf8"]
    if task in ("generate-ui", "adr-drift", "adr-index", "adr-okf", "docs-okf"):
        return [
            {"argv": prefix + args, "cwd": str(root), "env": overlay.copy()}
            for args in documentation_commands(task, root)
        ]
    plan: list[Command] = []

    def add(args: list[str], package: str | None = None) -> None:
        cwd = root / "local_packages" / package if package else root
        plan.append({"argv": prefix + args, "cwd": str(cwd), "env": overlay.copy()})

    if task in ("test", "test-iam-lib", "test-genai-tag", "test-all"):
        selected = {
            "test": (None,),
            "test-iam-lib": (PACKAGES[0],),
            "test-genai-tag": (PACKAGES[1],),
            "test-all": (None, *PACKAGES),
        }[task]
        for package in selected:
            add(["-m", "pytest", "-m", SAFE_MARKERS], package)
    elif task == "test-runtime-local":
        add(
            [
                "-m",
                "pytest",
                "tests/runtime_validation/test_real_model_runtime.py",
                "-m",
                "downloads_and_runs_model",
            ],
            PACKAGES[0],
        )
    elif task == "test-runtime-webapi":
        add(["scripts/run_runtime_webapi_tests.py"])
    elif task == "run-gui":
        add(["-c", "import sys; from lorairo.main import main; sys.exit(main())"])
    elif task == "mypy":
        add(["-m", "mypy", "-p", "lorairo"])
    elif task == "lint":
        add(["-m", "ruff", "check", "src/", "tests/", "--no-fix"])
        add(["-m", "ruff", "format", "src/", "tests/", "--check"])
    else:
        package = {"format": None, "format-iam-lib": PACKAGES[0], "format-genai-tag": PACKAGES[1]}[task]
        targets = ["."] if package == PACKAGES[1] else ["src/", "tests/"]
        add(["-m", "ruff", "format", *targets], package)
        add(["-m", "ruff", "check", *targets, "--fix"], package)
    return plan


def documentation_commands(task: str, root: Path) -> list[list[str]]:
    """Preserve OKF commands while avoiding shell loops and line continuations."""
    if task in ("generate-ui", "adr-drift"):
        script = "generate_ui.py" if task == "generate-ui" else "check_adr_drift.py"
        return [[f"scripts/{script}"]]
    scripts = ".agents/skills/okf-bundle/scripts"
    validate = f"{scripts}/okf_validate.py"
    index = f"{scripts}/okf_index.py"
    if task == "docs-okf":
        exclude = "README.md,CHANGELOG.md,CLAUDE.md,AGENTS.md,GEMINI.md,SKILL.md"
        roots = ["docs", *[f"local_packages/{package}/docs" for package in PACKAGES]]
        return [
            [validate, "--bundle-root", path, "--skip-missing", "--exclude", exclude]
            for path in roots
            if path == "docs" or (root / path).is_dir()
        ]
    common = [index, "--bundle-root", "docs/decisions"]
    commands = [
        [
            *common,
            "--table",
            "--columns",
            "id,title,timestamp,status",
            "--headers",
            "ADR,タイトル,日付,ステータス",
            "--link-column",
            "id",
            "--exclude",
            "README.md",
            "--table-output",
            "docs/decisions/README.md",
        ],
        [
            *common,
            "--index",
            "--index-output",
            "docs/decisions/index.md",
            "--index-title",
            "Architecture Decision Records",
            "--exclude",
            "README.md",
        ],
    ]
    if task == "adr-okf":
        return [
            [
                validate,
                "--bundle-root",
                "docs/decisions",
                "--require",
                "type,title,status,timestamp",
                "--exclude",
                "README.md",
            ],
            *[[*command, "--check"] for command in commands],
        ]
    return commands


def main(argv: list[str] | None = None) -> int:
    """Print a dry-run plan or execute it, stopping at the first failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=TASKS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args.task, ROOT, os.environ)
        if args.dry_run:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        for command in plan:
            result = subprocess.run(
                command["argv"], cwd=command["cwd"], env={**os.environ, **command["env"]}, check=False
            )
            if result.returncode:
                return result.returncode
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Development task error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
