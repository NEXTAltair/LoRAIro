"""Restore kit-owned hook runtimes from the project's pinned agent harness revision."""

import argparse
import importlib.util
import json
import re
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPOSITORY = "NEXTAltair/altairs-agent-dev-kit"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_pin(target: Path) -> str:
    """Reject malformed or unexpected download locations before accessing the network."""
    pin = json.loads((target / "agent-harness.lock.json").read_text(encoding="utf-8"))
    if not isinstance(pin, dict) or pin.get("repository") != REPOSITORY:
        raise ValueError(f"agent-harness.lock.json repository must be {REPOSITORY}")
    revision = pin.get("revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise ValueError("agent-harness.lock.json revision must be a full 40-character commit hash")
    return revision.lower()


def install_from_source(source: Path, target: Path, refresh_wiring: bool = False) -> None:
    """Use the kit's runtime-only API, preserving consumer settings and policy overrides."""
    installer = source / "scripts/install_harness.py"
    required = (installer, source / "hooks/scripts", source / "hooks/rules", source / "codex/hooks")
    if not installer.is_file() or not all(path.is_dir() for path in required[1:]):
        raise ValueError(f"Incomplete agent harness source: {source}")
    spec = importlib.util.spec_from_file_location("agent_kit_runtime_installer", installer)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load kit installer: {installer}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Refuse to change an existing branch runtime lock during ordinary restoration.
    module.install_runtime(target, force=refresh_wiring)
    if refresh_wiring:
        refresh_registrations(module, target)


def refresh_registrations(kit, target: Path) -> None:
    """Explicit migration of kit events and consumer hooks using the upstream generator."""
    path = target / ".claude/settings.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    hooks = settings.setdefault("hooks", {})
    generated = kit.claude_wiring()["hooks"]
    # `python` is present on both supported environments; setup-python supplies it in CI.
    for groups in generated.values():
        for group in groups:
            for handler in group["hooks"]:
                handler["command"] = "python"
    hooks.update(generated)
    for event, script in (
        ("FileChanged", "scripts/hook_generate_ui.py"),
        ("TeammateIdle", ".claude/hooks/hook_teammate_monitor.py"),
        ("TaskCreated", ".claude/hooks/hook_teammate_monitor.py"),
        ("TaskCompleted", ".claude/hooks/hook_teammate_monitor.py"),
    ):
        for group in hooks.get(event, []):
            for handler in group["hooks"]:
                handler["command"] = "python"
                handler["args"] = [
                    "-I",
                    "-X",
                    "utf8",
                    "-c",
                    kit.hook_bootstrap(script, event=event, consumer=True),
                ]
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    (target / ".codex/hooks.json").write_text(
        json.dumps(kit.codex_wiring(), indent=2) + "\n", encoding="utf-8"
    )


def restore(target: Path, kit_source: Path | None = None, refresh_wiring: bool = False) -> None:
    target = target.resolve()
    revision = read_pin(target)
    if kit_source is not None:
        # Explicit offline/development override; the caller chooses this local source.
        install_from_source(kit_source.resolve(), target, refresh_wiring)
        return
    with tempfile.TemporaryDirectory(prefix="lorairo-agent-harness-") as temporary:
        root = Path(temporary)
        archive_path = root / "kit.tar.gz"
        url = f"https://codeload.github.com/{REPOSITORY}/tar.gz/{revision}"
        with urllib.request.urlopen(url, timeout=60) as response, archive_path.open("wb") as destination:
            shutil.copyfileobj(response, destination)
        extracted = root / "source"
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(extracted, filter="data")
        install_from_source(extracted / f"altairs-agent-dev-kit-{revision}", target, refresh_wiring)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=PROJECT_ROOT, help="Consumer project directory")
    parser.add_argument(
        "--kit-source", type=Path, help="Use a trusted local kit checkout instead of downloading"
    )
    parser.add_argument(
        "--refresh-wiring",
        action="store_true",
        help="Explicitly repin the runtime and regenerate kit/consumer registrations; review and commit the diff",
    )
    args = parser.parse_args()
    try:
        restore(args.target, args.kit_source, args.refresh_wiring)
    except (OSError, ValueError, tarfile.TarError, AttributeError, RuntimeError) as error:
        parser.exit(1, f"Agent harness restore failed: {error}\n")


if __name__ == "__main__":
    main()
