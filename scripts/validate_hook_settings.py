"""Validate project hook registrations without executing their commands."""

import json
import re
from pathlib import Path

CODEX_EVENTS = {
    "SessionStart",
    "SessionEnd",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "UserPromptSubmit",
    "SubagentStart",
    "SubagentStop",
    "Stop",
    "Interrupt",
}


def validate_hook_settings(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in (".claude/settings.json", ".claude/settings.local.json", ".codex/hooks.json"):
        path = root / relative
        if not path.exists():
            continue
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"Hooks: {relative}: {exc}")
            continue
        if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
            errors.append(f"Hooks: {relative}: expected a hooks object")
            continue
        for event, groups in settings.get("hooks", {}).items():
            location = f"{relative}:{event}"
            if relative.startswith(".codex") and event not in CODEX_EVENTS:
                errors.append(f"Hooks: {location}: unsupported Codex event")
            errors.extend(validate_groups(root, location, groups))
    return errors


def validate_groups(root: Path, location: str, groups: object) -> list[str]:
    if not isinstance(groups, list):
        return [f"Hooks: {location}: expected a group list"]
    errors: list[str] = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            errors.append(f"Hooks: {location}: expected a handler list")
            continue
        for handler in group["hooks"]:
            errors.extend(validate_handler(root, location, handler))
    return errors


def validate_handler(root: Path, location: str, handler: object) -> list[str]:
    if not isinstance(handler, dict):
        return [f"Hooks: {location}: handler must be an object"]
    if handler.get("type") != "command":
        return []
    command = handler.get("command")
    args = handler.get("args", [])
    if not isinstance(command, str) or not command.strip():
        return [f"Hooks: {location}: command is required"]
    if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
        return [f"Hooks: {location}: args must be strings"]
    errors: list[str] = []
    for value in [command, *args, handler.get("commandWindows", "")]:
        if not isinstance(value, str):
            errors.append(f"Hooks: {location}: commandWindows must be a string")
            continue
        errors.extend(validate_command_paths(root, location, value))
    timeout = handler.get("timeout")
    if timeout is not None and (type(timeout) not in (int, float) or timeout <= 0):
        errors.append(f"Hooks: {location}: timeout must be positive seconds")
    return errors


def validate_command_paths(root: Path, location: str, value: str) -> list[str]:
    errors: list[str] = []
    if "/workspaces/LoRAIro" in value or "/usr/bin/timeout" in value:
        errors.append(f"Hooks: {location}: legacy Linux-only command; migrate this definition")
    # Supports exec-form args, quoted shell paths, and the Codex Python bootstrap.
    for script in re.findall(r"(?:\.claude/hooks/|\.codex/hooks/|scripts/)[\w./-]+\.py", value):
        if not (root / script).is_file():
            errors.append(f"Hooks: {location}: script not found: {script}")
    return errors
