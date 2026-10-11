"""Keep machine-specific agent environment settings in the current OS user homes.

Only config.toml/settings.json are read. Authentication and history are never opened.
Project overrides have higher precedence, so their managed environment keys must be
removed as part of the migration; changing CODEX_HOME alone is insufficient.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGED_KEYS = frozenset({"UV_PROJECT_ENVIRONMENT"})
SECTION = re.compile(r"^\s*\[\s*shell_environment_policy\s*\.\s*set\s*\]\s*(?:#.*)?$")
HEADER = re.compile(r"^\s*\[")


def merge_codex_scalar(text: str, table: str | None, key: str, value: str) -> str:
    """Merge the former local sandbox/inheritance preference without rewriting other sections."""
    parsed = tomllib.loads(text)
    current = parsed.get(table, {}) if table else parsed
    if current.get(key) == value:
        return text
    lines = text.splitlines(keepends=True)
    section = re.compile(rf"^\s*\[\s*{re.escape(table)}\s*\]\s*(?:#.*)?$") if table else None
    start = next(
        (index + 1 for index, line in enumerate(lines) if section and section.fullmatch(line.strip())), None
    )
    if table and start is None:
        text = text.rstrip() + f"\n\n[{table}]\n{key} = {json.dumps(value)}\n"
    else:
        start = start or 0
        end = next((index for index in range(start, len(lines)) if HEADER.match(lines[index])), len(lines))
        assignment = re.compile(rf'^\s*(?:{re.escape(key)}|"{re.escape(key)}")\s*=')
        existing = next((index for index in range(start, end) if assignment.match(lines[index])), None)
        if existing is None and key in current:
            raise ValueError(f"Use an ordinary {key} assignment before migrating Codex preferences")
        if existing is not None:
            lines[existing] = f"{key} = {json.dumps(value)}\n"
        else:
            lines.insert(start, f"{key} = {json.dumps(value)}\n")
        text = "".join(lines)
    tomllib.loads(text)
    return text


def path_platform(value: str) -> str | None:
    """Recognize absolute paths and permission rules containing machine paths."""
    if re.search(r"(?<![\w])[A-Za-z]:[/\\]", value):
        return "nt"
    if value.startswith("/") or re.search(r"\(\s*//|[\s=(\"']/(?!/)", value):
        return "posix"
    return None


def rewrite_codex_environment(text: str, updates: dict[str, str], *, project: bool = False) -> str:
    """Edit one environment table while retaining unrelated TOML and preferences."""
    parsed = tomllib.loads(text)
    environment = parsed.get("shell_environment_policy", {}).get("set", {})
    if not isinstance(environment, dict) or any(
        not isinstance(value, str) for value in environment.values()
    ):
        raise ValueError("Codex shell_environment_policy.set must be a table of strings")
    merged = {
        key: value
        for key, value in environment.items()
        if not (project and (key in MANAGED_KEYS or path_platform(value)))
    }
    merged.update(updates)
    if merged == environment:
        return text
    lines = text.splitlines(keepends=True)
    start = next((index for index, line in enumerate(lines) if SECTION.fullmatch(line.strip())), None)
    if start is None and environment:
        raise ValueError(
            "Use a [shell_environment_policy.set] table before migrating inline Codex settings"
        )
    if start is None:
        start = len(lines)
        end = start
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        if lines and lines[-1].strip():
            lines.append("\n")
            start += 1
            end += 1
    else:
        end = next(
            (index for index in range(start + 1, len(lines)) if HEADER.match(lines[index])), len(lines)
        )
    replacement = []
    if merged:
        replacement = ["[shell_environment_policy.set]\n"] + [
            f"{json.dumps(key)} = {json.dumps(value, ensure_ascii=False)}\n"
            for key, value in merged.items()
        ]
        replacement.append("\n")
    result = "".join([*lines[:start], *replacement, *lines[end:]])
    tomllib.loads(result)
    return result


def json_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("env", {}), dict)
        or not isinstance(value.get("permissions", {}), dict)
    ):
        raise ValueError(f"Expected settings, env and permissions objects: {path}")
    return value


def relocate_claude_settings(project: dict, user: dict) -> bool:
    """Relocate own-OS paths; foreign paths remain recoverable in private backups."""
    changed = relocate_claude_environment(project, user)
    for key, entries in project.get("permissions", {}).items():
        if not isinstance(entries, list):
            continue
        paths = [item for item in entries if isinstance(item, str) and path_platform(item)]
        if not paths:
            continue
        current = [item for item in paths if path_platform(item) == os.name]
        destination = user.setdefault("permissions", {}).setdefault(key, [])
        if not isinstance(destination, list):
            raise ValueError(f"Claude user permissions.{key} must be a list")
        destination.extend(item for item in current if item not in destination)
        project["permissions"][key] = [item for item in entries if item not in paths]
        changed = True
    return changed


def relocate_claude_environment(project: dict, user: dict) -> bool:
    environment = project.get("env", {})
    removed = {
        key
        for key, value in environment.items()
        if key in MANAGED_KEYS or (isinstance(value, str) and path_platform(value))
    }
    if not removed:
        return False
    for key in removed - MANAGED_KEYS:
        if path_platform(environment[key]) == os.name:
            user.setdefault("env", {})[key] = environment[key]
    project["env"] = {key: value for key, value in environment.items() if key not in removed}
    if not project["env"]:
        project.pop("env")
    return True


def write_preserving_backup(path: Path, content: str, backup_root: Path) -> None:
    """Keep private, content-addressed originals before changing a configuration."""
    original = path.read_bytes() if path.exists() else None
    encoded = content.encode("utf-8")
    if original == encoded:
        return
    if original is not None:
        identifier = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
        digest = hashlib.sha256(original).hexdigest()[:16]
        backup = backup_root / f"{identifier}-{digest}-{path.name}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(original)
        backup.chmod(0o600)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def configure(
    target: Path,
    venv: Path,
    codex_home: Path,
    claude_home: Path,
    *,
    migrate_codex_preferences: bool = False,
) -> list[Path]:
    """Merge into OS user settings and remove competing project environment keys."""
    target, venv = target.resolve(), venv.resolve()
    codex_home, claude_home = codex_home.resolve(), claude_home.resolve()
    if any(home.is_relative_to(target) for home in (codex_home, claude_home)):
        raise ValueError("Agent homes must be outside the shared project checkout")
    interpreter = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not interpreter.is_file():
        raise ValueError(f"The current OS shared venv interpreter is missing: {interpreter}")
    value = venv.as_posix()
    codex_config = codex_home / "config.toml"
    original = codex_config.read_text(encoding="utf-8") if codex_config.exists() else ""
    # Prepare and parse all changes before writing; a malformed project cannot
    # leave the homes updated while its higher-precedence override still wins.
    changes = []
    codex_updates = {"UV_PROJECT_ENVIRONMENT": value}
    claude_config = claude_home / "settings.json"
    user_settings = json_settings(claude_config)
    user_settings.setdefault("env", {})["UV_PROJECT_ENVIRONMENT"] = value
    project_codex = target / ".codex/config.toml"
    if project_codex.exists():
        text = project_codex.read_text(encoding="utf-8")
        project_settings = tomllib.loads(text)
        if migrate_codex_preferences:
            original = migrate_codex_local_preferences(original, project_settings)
        codex_updates.update(codex_machine_environment(project_settings))
        cleaned = rewrite_codex_environment(text, {}, project=True)
        changes.append((project_codex, cleaned, codex_home))
    for relative in (".claude/settings.json", ".claude/settings.local.json"):
        path = target / relative
        if not path.exists():
            continue
        settings = json_settings(path)
        if not relocate_claude_settings(settings, user_settings):
            continue
        changes.append((path, json.dumps(settings, indent=2, ensure_ascii=False) + "\n", claude_home))
    # Persist each user destination before removing the higher-precedence source.
    changes = [
        (codex_config, rewrite_codex_environment(original, codex_updates), codex_home),
        (claude_config, json.dumps(user_settings, indent=2, ensure_ascii=False) + "\n", claude_home),
        *changes,
    ]
    for path, content, home in changes:
        write_preserving_backup(path, content, home / "lorairo-config-backups")
    return [path for path, _, _ in changes]


def codex_machine_environment(project: dict) -> dict[str, str]:
    return {
        key: item
        for key, item in project.get("shell_environment_policy", {}).get("set", {}).items()
        if key not in MANAGED_KEYS and isinstance(item, str) and path_platform(item) == os.name
    }


def migrate_codex_local_preferences(user: str, project: dict) -> str:
    """Explicit transition when the formerly ignored local config becomes shared."""
    sandbox = project.get("sandbox_mode")
    inherit = project.get("shell_environment_policy", {}).get("inherit")
    if sandbox is not None:
        if not isinstance(sandbox, str):
            raise ValueError("Codex sandbox_mode must be a string")
        user = merge_codex_scalar(user, None, "sandbox_mode", sandbox)
    if inherit is not None:
        if not isinstance(inherit, str):
            raise ValueError("Codex shell_environment_policy.inherit must be a string")
        user = merge_codex_scalar(user, "shell_environment_policy", "inherit", inherit)
    return user


def shared_venv(target: Path) -> Path:
    common = subprocess.check_output(
        ["git", "-C", str(target), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        encoding="utf-8",
    ).strip()
    directory = Path(common)
    if directory.name != ".git":
        raise ValueError("Expected a standard checkout with a shared .git directory")
    return directory.parent / ".venv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=ROOT)
    parser.add_argument(
        "--venv", type=Path, help="The current OS shared venv; defaults to the Git common root"
    )
    parser.add_argument(
        "--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    )
    parser.add_argument(
        "--claude-home",
        type=Path,
        default=Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")),
    )
    parser.add_argument(
        "--migrate-codex-preferences",
        action="store_true",
        help="Preserve sandbox/inherit preferences before replacing a formerly ignored project config",
    )
    args = parser.parse_args()
    try:
        paths = configure(
            args.target,
            args.venv or shared_venv(args.target),
            args.codex_home,
            args.claude_home,
            migrate_codex_preferences=args.migrate_codex_preferences,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Agent environment configuration failed: {error}\n")
    for path in paths:
        print(f"Agent configuration: {path}")


if __name__ == "__main__":
    main()
