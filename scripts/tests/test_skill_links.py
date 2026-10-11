"""Portable skill projections synchronize content without requiring OS link support."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_agent_skills as installer
from validate_harness import validate_claude_skill_links


class SkillLinkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="skill copies ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.skills = self.root / ".agents/skills"
        self.links = self.root / ".claude/skills"
        self.links.mkdir(parents=True)
        self.skill = self.skills / "example"
        self.skill.mkdir(parents=True)
        (self.skill / "SKILL.md").write_text("original", encoding="utf-8")
        self.enterContext(patch.object(installer, "SKILLS_DIR", self.skills))
        self.enterContext(patch.object(installer, "CLAUDE_SKILLS_DIR", self.links))

    def test_copies_and_repeat_install_do_not_create_os_links(self):
        with patch.object(Path, "symlink_to", side_effect=AssertionError("No OS links")):
            installer.ensure_claude_symlinks()
            link = self.links / "example"
            self.assertFalse(link.is_symlink() or link.is_junction())
            self.assertEqual((link / "SKILL.md").read_text(), "original")
            self.assertEqual(validate_claude_skill_links(self.root), [])
            with patch.object(installer.shutil, "copytree") as copy:
                installer.ensure_claude_symlinks()
            copy.assert_not_called()

    def test_source_change_synchronizes_a_generated_copy(self):
        installer.ensure_claude_symlinks()
        (self.skill / "SKILL.md").write_text("updated", encoding="utf-8")
        self.assertTrue(validate_claude_skill_links(self.root))
        installer.ensure_claude_symlinks()
        self.assertEqual((self.links / "example/SKILL.md").read_text(), "updated")
        self.assertEqual(validate_claude_skill_links(self.root), [])

    def test_edited_projection_is_preserved_without_partial_updates(self):
        installer.ensure_claude_symlinks()
        (self.links / "example/SKILL.md").write_text("unsaved user work", encoding="utf-8")
        another = self.skills / "another"
        another.mkdir()
        (another / "SKILL.md").write_text("new", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Preserving edited"):
            installer.ensure_claude_symlinks()
        self.assertFalse((self.links / "another").exists())
        self.assertEqual((self.links / "example/SKILL.md").read_text(), "unsaved user work")

    def test_unmanaged_directory_is_preserved(self):
        unrelated = self.links / "personal"
        unrelated.mkdir()
        (unrelated / "SKILL.md").write_text("personal", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Preserving unmanaged"):
            installer.ensure_claude_symlinks()
        self.assertEqual((unrelated / "SKILL.md").read_text(), "personal")

    def test_removed_source_removes_only_the_generated_projection(self):
        installer.ensure_claude_symlinks()
        installer.shutil.rmtree(self.skill)
        installer.ensure_claude_symlinks()
        self.assertFalse((self.links / "example").exists())

    def test_failed_copy_keeps_the_previous_projection(self):
        installer.ensure_claude_symlinks()
        (self.skill / "SKILL.md").write_text("updated", encoding="utf-8")
        with (
            patch.object(installer.shutil, "copytree", side_effect=OSError("disk full")),
            self.assertRaises(OSError),
        ):
            installer.ensure_claude_symlinks()
        self.assertEqual((self.links / "example/SKILL.md").read_text(), "original")

    def test_legacy_link_is_unlinked_without_removing_target(self):
        link = self.links / "example"
        try:
            link.symlink_to(self.skill, target_is_directory=True)
        except OSError:
            self.skipTest("Current Windows user has no symlink privileges")
        self.assertTrue(validate_claude_skill_links(self.root))
        installer.ensure_claude_symlinks()
        self.assertFalse(link.is_symlink())
        self.assertEqual((self.skill / "SKILL.md").read_text(), "original")
        self.assertEqual(validate_claude_skill_links(self.root), [])


if __name__ == "__main__":
    unittest.main()
