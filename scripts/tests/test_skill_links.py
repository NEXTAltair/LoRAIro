"""Actual directory links work without Windows symlink privileges and keep targets safe."""

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
        self.temporary = tempfile.TemporaryDirectory(prefix="skill links ")
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

    def test_real_link_creation_and_idempotent_validation(self):
        installer.ensure_claude_symlinks()
        link = self.links / "example"
        self.assertTrue(link.is_symlink() or link.is_junction())
        self.assertEqual((link / "SKILL.md").read_text(), "original")
        self.assertEqual(validate_claude_skill_links(self.root), [])
        with patch.object(installer, "create_claude_skill_link") as create:
            installer.ensure_claude_symlinks()
        create.assert_not_called()

    def test_wrong_target_is_rejected_then_repaired_without_deleting_target(self):
        other = self.skills / "other"
        other.mkdir()
        (other / "SKILL.md").write_text("preserve target", encoding="utf-8")
        installer.create_claude_skill_link(self.links / "example", other)
        errors = validate_claude_skill_links(self.root)
        self.assertTrue(any("points to" in error for error in errors))
        installer.ensure_claude_symlinks()
        self.assertEqual((other / "SKILL.md").read_text(), "preserve target")
        self.assertEqual((self.links / "example/SKILL.md").read_text(), "original")
        self.assertEqual(validate_claude_skill_links(self.root), [])


if __name__ == "__main__":
    unittest.main()
