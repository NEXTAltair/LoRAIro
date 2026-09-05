"""Runtime restoration preserves the consumer's settings and policy overrides."""

import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "install_agent_harness.py"
SPEC = importlib.util.spec_from_file_location("install_agent_harness", SCRIPT)
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)
REVISION = "a16f3a6b2d638852ad47285195394d36ddfd44d9"

# Mirrors the upstream runtime-only contract, without fetching or importing app dependencies.
INSTALLER = """from pathlib import Path
import shutil
KIT = Path(__file__).resolve().parents[1]
def install_runtime(target, force=False):
    assert force is True
    for directory, pattern, destination in (
        ("hooks/scripts", "*.py", ".claude/hooks"),
        ("hooks/rules", "*.default.json", ".claude/hooks/rules"),
        ("codex/hooks", "*.py", ".codex/hooks"),
    ):
        for source in (KIT / directory).glob(pattern):
            output = target / destination / source.name
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output)
"""


class HarnessRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / "project"
        self.target.mkdir()
        self.write_pin()
        self.kit = self.root / f"altairs-agent-dev-kit-{REVISION}"
        for name, content in {
            "scripts/install_harness.py": INSTALLER,
            "hooks/scripts/hook_common.py": "# restored runtime\n",
            "hooks/rules/pre_commands.default.json": "{}\n",
            "hooks/rules/pre_commands.json": "DO NOT COPY\n",
            "codex/hooks/hook_pre_commands.py": "# restored adapter\n",
        }.items():
            path = self.kit / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def write_pin(self, **overrides):
        pin = {"repository": HARNESS.REPOSITORY, "revision": REVISION, **overrides}
        (self.target / "agent-harness.lock.json").write_text(json.dumps(pin), encoding="utf-8")

    def test_local_restore_preserves_settings_and_overrides(self):
        preserved = (
            ".claude/settings.json",
            ".claude/settings.local.json",
            ".codex/hooks.json",
            ".codex/config.toml",
            ".claude/hooks/rules/pre_commands.json",
        )
        for name in preserved:
            path = self.target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"consumer-owned\n")
        stale = self.target / ".claude/hooks/hook_common.py"
        stale.write_text("# stale", encoding="utf-8")
        HARNESS.restore(self.target, self.kit)
        self.assertEqual(stale.read_text(encoding="utf-8"), "# restored runtime\n")
        self.assertTrue((self.target / ".codex/hooks/hook_pre_commands.py").is_file())
        self.assertTrue((self.target / ".claude/hooks/rules/pre_commands.default.json").is_file())
        for name in preserved:
            self.assertEqual((self.target / name).read_bytes(), b"consumer-owned\n")

    def test_invalid_pin_fails_before_download(self):
        for overrides in ({"revision": "main"}, {"revision": "../bad"}, {"repository": "other/repo"}):
            with (
                self.subTest(overrides=overrides),
                patch.object(HARNESS.urllib.request, "urlopen") as download,
            ):
                self.write_pin(**overrides)
                with self.assertRaises(ValueError):
                    HARNESS.restore(self.target)
                download.assert_not_called()

    def test_pinned_archive_download_and_restore(self):
        content = io.BytesIO()
        with tarfile.open(fileobj=content, mode="w:gz") as archive:
            archive.add(self.kit, arcname=self.kit.name)
        with patch.object(
            HARNESS.urllib.request, "urlopen", return_value=io.BytesIO(content.getvalue())
        ) as download:
            HARNESS.restore(self.target)
        download.assert_called_once_with(
            f"https://codeload.github.com/{HARNESS.REPOSITORY}/tar.gz/{REVISION}", timeout=60
        )
        self.assertTrue((self.target / ".claude/hooks/hook_common.py").is_file())

    def test_unsafe_archive_member_rejected(self):
        content = io.BytesIO()
        with tarfile.open(fileobj=content, mode="w:gz") as archive:
            member = tarfile.TarInfo("../../escape.py")
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        with patch.object(HARNESS.urllib.request, "urlopen", return_value=io.BytesIO(content.getvalue())):
            with self.assertRaises(tarfile.FilterError):
                HARNESS.restore(self.target)
        self.assertFalse((self.target / ".claude").exists())


if __name__ == "__main__":
    unittest.main()
