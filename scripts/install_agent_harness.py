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


def install_from_source(source: Path, target: Path) -> None:
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
    module.install_runtime(target, force=True)


def restore(target: Path, kit_source: Path | None = None) -> None:
    target = target.resolve()
    revision = read_pin(target)
    if kit_source is not None:
        # Explicit offline/development override; the caller chooses this local source.
        install_from_source(kit_source.resolve(), target)
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
        install_from_source(extracted / f"altairs-agent-dev-kit-{revision}", target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=PROJECT_ROOT, help="Consumer project directory")
    parser.add_argument(
        "--kit-source", type=Path, help="Use a trusted local kit checkout instead of downloading"
    )
    args = parser.parse_args()
    try:
        restore(args.target, args.kit_source)
    except (OSError, ValueError, tarfile.TarError, AttributeError) as error:
        parser.exit(1, f"Agent harness restore failed: {error}\n")


if __name__ == "__main__":
    main()
