import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("mesa_patch", Path(__file__).resolve().parents[1] / "runtime/kosmickrisp/apply_patch.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "mesa"
        self.repo.mkdir()
        self.git("init", "-q")
        self.file = self.repo / "source.c"
        self.file.write_text("before\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
        self.revision = self.git("rev-parse", "HEAD").strip()
        self.patch = self.root / "change.patch"
        self.patch.write_text("diff --git a/source.c b/source.c\n--- a/source.c\n+++ b/source.c\n@@ -1 +1 @@\n-before\n+after\n")
        self.digest = hashlib.sha256(self.patch.read_bytes()).hexdigest()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True)

    def apply(self):
        return module.apply(self.repo, self.patch, self.revision, self.digest)

    def test_clean_and_idempotent(self):
        self.assertEqual(self.apply(), "applied")
        self.assertEqual(self.file.read_text(), "after\n")
        self.assertEqual(self.apply(), "already applied")
        self.assertEqual(self.git("diff", "--cached"), "")

    def test_corrupt_patch(self):
        self.patch.write_text(self.patch.read_text() + "corruption")
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            self.apply()
        self.assertEqual(self.file.read_text(), "before\n")

    def test_wrong_revision(self):
        self.revision = "0" * 40
        with self.assertRaisesRegex(RuntimeError, "revision"):
            self.apply()

    def test_dirty_preserved(self):
        self.file.write_text("user changes\n")
        with self.assertRaisesRegex(RuntimeError, "local changes"):
            self.apply()
        self.assertEqual(self.file.read_text(), "user changes\n")

    def test_staged_preserved(self):
        self.file.write_text("user changes\n")
        self.git("add", ".")
        with self.assertRaisesRegex(RuntimeError, "staged"):
            self.apply()

    def test_extra_change_after_application(self):
        self.apply()
        self.file.write_text("after\nuser changes\n")
        with self.assertRaisesRegex(RuntimeError, "local changes"):
            self.apply()

    def test_untracked_preserved(self):
        extra = self.repo / "new.c"
        extra.write_text("user changes\n")
        with self.assertRaisesRegex(RuntimeError, "untracked"):
            self.apply()
        self.assertTrue(extra.exists())


if __name__ == "__main__":
    unittest.main()
