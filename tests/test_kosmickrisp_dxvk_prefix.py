import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE = Path(__file__).resolve().parents[1] / "runtime/kosmickrisp/dxvk-prefix.py"
spec = importlib.util.spec_from_file_location("dxvk_prefix", MODULE)
dxvk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dxvk)


class PrefixInstallationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.prefix, self.payload = root / "prefix", root / "dxvk"
        for lane, arch in dxvk.LANES:
            target = self.prefix / "drive_c/windows" / lane
            source = self.payload / arch
            target.mkdir(parents=True)
            source.mkdir(parents=True)
            for name in dxvk.NAMES:
                (target / name).write_bytes(("wine-" + lane + name).encode())
                (source / name).write_bytes(("dxvk-" + arch + name).encode())

    def test_install_and_restore_both_architectures(self):
        self.assertEqual(dxvk.install(self.prefix, self.payload), "installed")
        self.assertEqual(dxvk.install(self.prefix, self.payload), "already installed")
        for lane, arch in dxvk.LANES:
            for name in dxvk.NAMES:
                self.assertEqual((self.prefix / "drive_c/windows" / lane / name).read_bytes(),
                                 (self.payload / arch / name).read_bytes())
        self.assertEqual(dxvk.restore(self.prefix, self.payload), "restored")
        for lane, _ in dxvk.LANES:
            for name in dxvk.NAMES:
                self.assertEqual((self.prefix / "drive_c/windows" / lane / name).read_bytes(),
                                 ("wine-" + lane + name).encode())

    def test_restore_refuses_changed_dll(self):
        dxvk.install(self.prefix, self.payload)
        changed = self.prefix / "drive_c/windows/system32/dxgi.dll"
        changed.write_bytes(b"another installer")
        with self.assertRaisesRegex(ValueError, "changed since installation"):
            dxvk.restore(self.prefix, self.payload)
        self.assertEqual(changed.read_bytes(), b"another installer")

    def test_symlinked_prefix_is_rejected(self):
        link = self.prefix.parent / "linked-prefix"
        link.symlink_to(self.prefix, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            dxvk.install(link, self.payload)


if __name__ == "__main__":
    unittest.main()
