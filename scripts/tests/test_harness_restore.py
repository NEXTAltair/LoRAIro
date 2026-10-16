"""Runtime restoration preserves the consumer's settings and policy overrides."""

import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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
    assert force is False
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
        self.root = Path(self.temporary.name).resolve()
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
            "agents/investigation.md": "# common agent\n",
            "rules/git-workflow.md": "# common workflow\n",
            "codex/agents/investigation.toml": 'model = "default"\n',
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

    def test_missing_common_guidance_restored_without_generating_environment_config(self):
        HARNESS.restore(self.target, self.kit)
        self.assertEqual((self.target / ".claude/agents/investigation.md").read_text(), "# common agent\n")
        self.assertEqual((self.target / ".claude/rules/git-workflow.md").read_text(), "# common workflow\n")
        self.assertTrue((self.target / ".codex/agents/investigation.toml").is_file())
        self.assertFalse((self.target / ".codex/config.toml").exists())

    def test_existing_consumer_guidance_preserved_across_reinstall(self):
        HARNESS.restore(self.target, self.kit)
        workflow = self.target / ".claude/rules/git-workflow.md"
        workflow.write_text("# consumer instructions\n", encoding="utf-8")
        (self.kit / "rules/git-workflow.md").write_text("# new kit instructions\n", encoding="utf-8")
        HARNESS.restore(self.target, self.kit)
        self.assertEqual(workflow.read_text(), "# consumer instructions\n")

    def test_kit_guidance_updates_only_the_unmodified_generated_copy(self):
        HARNESS.restore(self.target, self.kit)
        (self.kit / "agents/investigation.md").write_text("# new agent\n", encoding="utf-8")
        HARNESS.restore(self.target, self.kit)
        self.assertEqual((self.target / ".claude/agents/investigation.md").read_text(), "# new agent\n")

    def test_removed_and_renamed_generated_guidance_is_reconciled_in_all_destinations(self):
        HARNESS.restore(self.target, self.kit)
        names = (
            ("agents/investigation.md", ".claude/agents/investigation.md"),
            ("rules/git-workflow.md", ".claude/rules/git-workflow.md"),
            ("codex/agents/investigation.toml", ".codex/agents/investigation.toml"),
        )
        for source, _destination in names:
            upstream = self.kit / source
            upstream.rename(upstream.with_name("renamed" + upstream.suffix))
        HARNESS.restore(self.target, self.kit)
        state_path = self.target / ".agent-kit/guidance-state.json"
        state = json.loads(state_path.read_text())
        for source, destination in names:
            self.assertFalse((self.target / destination).exists())
            renamed = Path(destination).with_name("renamed" + Path(source).suffix)
            self.assertTrue((self.target / renamed).is_file())
            self.assertNotIn(destination, state)
            self.assertIn(renamed.as_posix(), state)
            (self.kit / source).with_name("renamed" + Path(source).suffix).unlink()
        HARNESS.restore(self.target, self.kit)
        self.assertEqual(json.loads(state_path.read_text()), {})
        HARNESS.restore(self.target, self.kit)
        self.assertEqual(json.loads(state_path.read_text()), {})

    def test_removed_edited_guidance_is_preserved_and_no_longer_generated(self):
        HARNESS.restore(self.target, self.kit)
        output = self.target / ".claude/rules/git-workflow.md"
        output.write_text("# consumer instructions\n", encoding="utf-8")
        (self.kit / "rules/git-workflow.md").unlink()
        for _ in range(2):
            HARNESS.restore(self.target, self.kit)
            self.assertEqual(output.read_text(), "# consumer instructions\n")
            state = json.loads((self.target / ".agent-kit/guidance-state.json").read_text())
            self.assertNotIn(".claude/rules/git-workflow.md", state)

    def test_absent_guidance_state_is_retired_without_touching_unmanaged_files(self):
        HARNESS.restore(self.target, self.kit)
        (self.kit / "agents/investigation.md").unlink()
        (self.target / ".claude/agents/investigation.md").unlink()
        personal = self.target / ".claude/agents/personal.md"
        personal.write_text("# personal agent\n", encoding="utf-8")
        HARNESS.restore(self.target, self.kit)
        state = json.loads((self.target / ".agent-kit/guidance-state.json").read_text())
        self.assertNotIn(".claude/agents/investigation.md", state)
        self.assertEqual(personal.read_text(), "# personal agent\n")

    def test_unmanaged_manifest_entries_never_authorize_deletion(self):
        HARNESS.restore(self.target, self.kit)
        unrelated = self.target / "personal.md"
        unrelated.write_text("private work", encoding="utf-8")
        external = self.root / "outside.md"
        external.write_text("outside the checkout", encoding="utf-8")
        invalid_digest = self.target / ".claude/agents/personal.md"
        invalid_digest.write_text("unmanaged", encoding="utf-8")
        state_path = self.target / ".agent-kit/guidance-state.json"
        state = json.loads(state_path.read_text())
        extra = {
            "personal.md": HARNESS.guidance_digest(unrelated),
            "../outside.md": HARNESS.guidance_digest(external),
            ".claude/agents/personal.md": "not-a-generated-digest",
        }
        state.update(extra)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        HARNESS.restore(self.target, self.kit)
        self.assertEqual(unrelated.read_text(), "private work")
        self.assertEqual(external.read_text(), "outside the checkout")
        self.assertEqual(invalid_digest.read_text(), "unmanaged")
        restored = json.loads(state_path.read_text())
        for key, value in extra.items():
            self.assertEqual(restored[key], value)

    def test_stale_guidance_below_linked_parent_is_not_read_or_deleted(self):
        HARNESS.restore(self.target, self.kit)
        (self.kit / "agents/investigation.md").unlink()
        relative = ".claude/agents/investigation.md"
        output = self.target / relative
        parent = output.parent
        original = HARNESS.guidance_digest

        def digest(path):
            self.assertNotEqual(path, output, "Never read guidance below a linked parent")
            return original(path)

        with (
            patch.object(HARNESS, "filesystem_link", side_effect=lambda path: path == parent),
            patch.object(HARNESS, "guidance_digest", digest),
        ):
            HARNESS.restore(self.target, self.kit)
        self.assertEqual((self.target / relative).read_text(), "# common agent\n")
        self.assertNotIn(relative, json.loads((self.target / ".agent-kit/guidance-state.json").read_text()))

    def test_stale_guidance_replaced_with_consumer_directory_is_preserved(self):
        HARNESS.restore(self.target, self.kit)
        (self.kit / "agents/investigation.md").unlink()
        output = self.target / ".claude/agents/investigation.md"
        output.unlink()
        output.mkdir()
        personal = output / "notes.txt"
        personal.write_text("unfinished work", encoding="utf-8")
        for _ in range(2):
            HARNESS.restore(self.target, self.kit)
            self.assertEqual(personal.read_text(), "unfinished work")

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
