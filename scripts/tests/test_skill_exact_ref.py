"""Exact revision restoration verifies staged content before replacing a working skill."""

import importlib.util
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "skill_restorer", Path(__file__).resolve().parents[1] / "install_agent_skills.py"
)
RESTORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESTORE)


class ExactRefTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.skills = self.root / ".agents/skills"
        self.skill = self.skills / "example"
        self.skill.mkdir(parents=True)
        (self.skill / "SKILL.md").write_text("working original", encoding="utf-8")
        self.entry = {
            "source": "owner/repo",
            "sourceType": "github",
            "ref": "a" * 40,
            "skillPath": "skills/example/SKILL.md",
            "computedHash": "a" * 64,
        }
        self.lock = self.root / "skills-lock.json"
        self.lock.write_text(
            json.dumps({"version": 1, "skills": {"example": self.entry}}), encoding="utf-8"
        )
        self.before = self.lock.read_bytes()
        for name, value in (
            ("PROJECT_ROOT", self.root),
            ("SKILLS_DIR", self.skills),
            ("PENDING_DIR", self.skills / ".pending-replace"),
            ("STATE_FILE", self.skills / ".installed-lock-hashes.json"),
        ):
            self.enterContext(patch.object(RESTORE, name, value))

    def archive(self, name=None):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            member = tarfile.TarInfo(name or f"repo-{'a' * 40}/skills/example/SKILL.md")
            member.size = 8
            archive.addfile(member, io.BytesIO(b"verified"))
        return io.BytesIO(stream.getvalue())

    def cli(self, actual="a" * 64):
        def run(args, cwd, **kwargs):
            # Publication or backup must not occur before the CLI hash check.
            self.assertEqual((self.skill / "SKILL.md").read_text(), "working original")
            self.assertFalse((self.skills / ".pending-replace").exists())
            root = Path(cwd)
            output = root / ".agents/skills/example"
            output.mkdir(parents=True)
            (output / "SKILL.md").write_text("verified", encoding="utf-8")
            (root / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "skills": {
                            "example": {
                                "sourceType": "local",
                                "source": "temporary",
                                "computedHash": actual,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args, 0)

        return run

    def test_repository_revision_is_downloaded_once_per_invocation(self):
        with patch.object(RESTORE.urllib.request, "urlopen", return_value=self.archive()) as download:
            first = RESTORE.download_exact_source("owner/repo", "a" * 40, self.root / "cache")
            second = RESTORE.download_exact_source("owner/repo", "a" * 40, self.root / "cache")
        self.assertEqual(first, second)
        self.assertTrue((first / "skills/example/SKILL.md").is_file())
        download.assert_called_once()

    def test_exact_restore_preserves_github_lock_and_retains_backup(self):
        with (
            patch.object(RESTORE.urllib.request, "urlopen", return_value=self.archive()),
            patch.object(RESTORE.subprocess, "run", side_effect=self.cli()),
        ):
            backup = RESTORE.restore_exact_ref("example", self.entry)
        self.assertEqual((self.skill / "SKILL.md").read_text(), "verified")
        self.assertEqual((backup / "SKILL.md").read_text(), "working original")
        self.assertEqual(self.lock.read_bytes(), self.before)

    def test_mismatch_leaves_existing_skill_and_lock_untouched(self):
        with (
            patch.object(RESTORE.urllib.request, "urlopen", return_value=self.archive()),
            patch.object(RESTORE.subprocess, "run", side_effect=self.cli("drift")),
            self.assertRaisesRegex(ValueError, "hash mismatch"),
        ):
            RESTORE.restore_exact_ref("example", self.entry)
        self.assertEqual((self.skill / "SKILL.md").read_text(), "working original")
        self.assertFalse((self.skills / ".pending-replace").exists())
        self.assertEqual(self.lock.read_bytes(), self.before)

    def test_archive_traversal_never_runs_cli(self):
        with (
            patch.object(RESTORE.urllib.request, "urlopen", return_value=self.archive("../../escape")),
            patch.object(RESTORE.subprocess, "run") as cli,
            self.assertRaises(tarfile.FilterError),
        ):
            RESTORE.restore_exact_ref("example", self.entry)
        cli.assert_not_called()
        self.assertEqual((self.skill / "SKILL.md").read_text(), "working original")

    def test_main_preserves_lock_bytes_even_when_cli_reformats_provenance(self):
        self.entry["ref"] = "release-tag"
        self.lock.write_bytes(
            json.dumps({"version": 1, "skills": {"example": self.entry}}, indent=4).encode()
        )
        before = self.lock.read_bytes()

        def cli(args, cwd, **kwargs):
            self.skill.mkdir(parents=True)
            (self.skill / "SKILL.md").write_text("verified", encoding="utf-8")
            rewritten = json.loads(before)
            rewritten["skills"]["example"]["source"] = "CLI rewritten provenance"
            self.lock.write_text(json.dumps(rewritten), encoding="utf-8")
            return subprocess.CompletedProcess(args, 0)

        with (
            patch.object(RESTORE, "prune_removed_skills", return_value=([], [])),
            patch.object(RESTORE, "ensure_claude_symlinks"),
            patch.object(RESTORE.shutil, "which", return_value="npx"),
            patch.object(RESTORE.subprocess, "run", side_effect=cli),
        ):
            self.assertEqual(RESTORE.main(), 0)
        self.assertEqual(self.lock.read_bytes(), before)
        self.assertFalse((self.skills / ".pending-replace").exists())

    def test_invalid_provenance_rejected_before_download(self):
        for overrides in (
            {"source": "owner/repo/../../other"},
            {"ref": "main"},
            {"skillPath": "../SKILL.md"},
            {"computedHash": ""},
        ):
            with (
                self.subTest(overrides=overrides),
                patch.object(RESTORE.urllib.request, "urlopen") as download,
                self.assertRaises(ValueError),
            ):
                RESTORE.restore_exact_ref("example", {**self.entry, **overrides})
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
