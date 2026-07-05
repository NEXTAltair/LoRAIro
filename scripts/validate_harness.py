#!/usr/bin/env python3
"""Agent harness validation script.

Validates that Claude Code/Codex skills, hooks, and settings are internally consistent:
- Skills: each shared skill directory has a SKILL.md with required frontmatter fields
- Claude skill links: .claude/skills/<name> points at .agents/skills/<name>
- Skills lock: skills-lock.json entries match installed shared skills
- Hooks: hook script files referenced in settings.local.json exist on disk
- Settings: settings.local.json has required structural fields

Usage:
    python scripts/validate_harness.py
"""

import json
import re
import sys
from pathlib import Path

SHARED_SKILLS_DIR = ".agents/skills"
CLAUDE_SKILLS_DIR = ".claude/skills"


def validate_skills(project_root: Path) -> list[str]:
    """Validate that all skill directories contain a valid SKILL.md.

    Args:
        project_root: Project root directory.

    Returns:
        List of error messages (empty if all pass).
    """
    errors: list[str] = []
    skills_dir = project_root / SHARED_SKILLS_DIR

    if not skills_dir.exists():
        return []

    # Find all SKILL.md files recursively (directories without SKILL.md are containers)
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        content = skill_md.read_text(encoding="utf-8")

        # Check for frontmatter block
        if not content.startswith("---"):
            errors.append(f"Skills: {skill_md.relative_to(skills_dir)} has no frontmatter")
            continue

        # Extract frontmatter
        end = content.find("---", 3)
        if end == -1:
            errors.append(f"Skills: {skill_md.relative_to(skills_dir)} has unclosed frontmatter")
            continue

        frontmatter = content[3:end]
        for field in ("name", "description"):
            if not re.search(rf"^{field}:", frontmatter, re.MULTILINE):
                errors.append(
                    f"Skills: {skill_md.relative_to(skills_dir)} frontmatter missing '{field}' field"
                )

    return errors


def validate_claude_skill_links(project_root: Path) -> list[str]:
    """Validate Claude Code skill symlinks point to shared skill directories."""
    errors: list[str] = []
    shared_skills_dir = project_root / SHARED_SKILLS_DIR
    claude_skills_dir = project_root / CLAUDE_SKILLS_DIR

    if not shared_skills_dir.exists() or not claude_skills_dir.exists():
        return []

    shared_skill_names = {
        skill_dir.name
        for skill_dir in shared_skills_dir.iterdir()
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists()
    }
    claude_skill_names = {
        skill_link.name
        for skill_link in claude_skills_dir.iterdir()
        if skill_link.is_dir() or skill_link.is_symlink()
    }

    missing_links = sorted(shared_skill_names - claude_skill_names)
    extra_links = sorted(claude_skill_names - shared_skill_names)
    for name in missing_links:
        errors.append(f"Claude skills: missing symlink for shared skill: {name}")
    for name in extra_links:
        errors.append(f"Claude skills: symlink has no shared skill target: {name}")

    for skill_link in sorted(claude_skills_dir.iterdir()):
        if not skill_link.is_symlink():
            errors.append(f"Claude skills: expected symlink, found real path: {skill_link.name}")
            continue
        target = skill_link.resolve()
        expected = (shared_skills_dir / skill_link.name).resolve()
        if target != expected:
            errors.append(f"Claude skills: {skill_link.name} points to {target}, expected {expected}")

    return errors


def validate_skills_lock(project_root: Path) -> list[str]:
    """Validate skills-lock.json matches the shared skills installed on disk."""
    errors: list[str] = []
    skills_dir = project_root / SHARED_SKILLS_DIR
    lock_path = project_root / "skills-lock.json"

    if not skills_dir.exists() or not lock_path.exists():
        return []

    try:
        lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"Skills lock: skills-lock.json is invalid JSON: {e}"]

    lock_skills = lock_data.get("skills")
    if not isinstance(lock_skills, dict):
        return ["Skills lock: skills-lock.json must contain a 'skills' object"]

    installed_skill_names = {
        skill_dir.name
        for skill_dir in skills_dir.iterdir()
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists()
    }
    locked_skill_names = set(lock_skills)

    for name in sorted(installed_skill_names - locked_skill_names):
        errors.append(f"Skills lock: installed skill missing from lock: {name}")
    for name in sorted(locked_skill_names - installed_skill_names):
        # 外部ソース (github) の skill は git 追跡外で、fresh checkout では実体が無い。
        # make setup (scripts/install_agent_skills.py) が lock から復元する運用のため許容する
        if lock_skills[name].get("sourceType") == "github":
            continue
        errors.append(f"Skills lock: lock entry has no installed skill: {name}")

    return errors


def validate_hooks(project_root: Path) -> list[str]:  # noqa: C901
    """Validate that hook scripts referenced in settings.local.json exist.

    Args:
        project_root: Project root directory.

    Returns:
        List of error messages (empty if all pass).
    """
    errors: list[str] = []
    settings_path = project_root / ".claude" / "settings.local.json"

    if not settings_path.exists():
        return []

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"Settings: settings.local.json is invalid JSON: {e}"]

    hooks_section = settings.get("hooks", {})
    for event, hook_entries in hooks_section.items():
        if not isinstance(hook_entries, list):
            continue
        for entry in hook_entries:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                if not cmd:
                    continue
                # Complex shell expressions (containing spaces, &&, |, ;) are not file paths.
                # Only validate simple direct-path commands like /path/to/hook.py
                if any(c in cmd for c in (" ", "&&", "|", ";")):
                    continue
                # Commands may be absolute paths like /workspaces/LoRAIro/.claude/hooks/foo.py
                # Resolve relative to project root if not absolute
                cmd_path = Path(cmd)
                if not cmd_path.is_absolute():
                    cmd_path = project_root / cmd_path
                else:
                    # Replace /workspaces/LoRAIro prefix with actual project root
                    try:
                        rel = cmd_path.relative_to("/workspaces/LoRAIro")
                        cmd_path = project_root / rel
                    except ValueError:
                        pass

                if not cmd_path.exists():
                    errors.append(f"Hooks: {event} hook script not found: {cmd}")

    return errors


def validate_settings_structure(project_root: Path) -> list[str]:
    """Validate settings.local.json has required structural fields.

    Args:
        project_root: Project root directory.

    Returns:
        List of error messages (empty if all pass).
    """
    errors: list[str] = []
    settings_path = project_root / ".claude" / "settings.local.json"

    if not settings_path.exists():
        # settings.local.json is optional in some setups
        return []

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"Settings: settings.local.json is invalid JSON: {e}"]

    if not isinstance(settings, dict):
        errors.append("Settings: settings.local.json root must be a JSON object")

    return errors


def main() -> int:
    """Run all harness validation checks.

    Returns:
        Exit code (0 = success, 1 = failure).
    """
    project_root = Path(__file__).resolve().parent.parent

    all_errors: list[str] = []

    print("Validating skills...")
    all_errors.extend(validate_skills(project_root))

    print("Validating Claude skill symlinks...")
    all_errors.extend(validate_claude_skill_links(project_root))

    print("Validating skills lock...")
    all_errors.extend(validate_skills_lock(project_root))

    print("Validating hook scripts...")
    all_errors.extend(validate_hooks(project_root))

    print("Validating settings structure...")
    all_errors.extend(validate_settings_structure(project_root))

    print("\n" + "=" * 60)
    print("HARNESS VALIDATION RESULTS")
    print("=" * 60)

    if all_errors:
        for err in all_errors:
            print(f"  FAIL: {err}")
        print(f"\nFailed: {len(all_errors)} issue(s) found")
        return 1

    print("  PASS: All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
