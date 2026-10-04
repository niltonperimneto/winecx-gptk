"""Exercise packaging guards and the launcher with stand-in tools, without Wine."""
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Arm64PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="arm64 relocated ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.wine = self.root / "Wine"
        self.bundle = self.root / "bundle"
        self.tools = self.root / "tools"
        for path in (self.wine / "bin", self.wine / "lib/wine/aarch64-unix", self.bundle, self.tools):
            path.mkdir(parents=True, exist_ok=True)
        (self.wine / "lib/wine/aarch64-unix/win32u.so").write_text("CX_LIBVULKAN\n")
        for name in ("libvulkan.1.dylib", "libvulkan_kosmickrisp.dylib", "kosmickrisp_icd.json", "SOURCE.txt"):
            (self.bundle / name).touch()
        (self.bundle / "kosmickrisp_icd.json").write_text(json.dumps({"ICD": {"library_path": "./libvulkan_kosmickrisp.dylib"}}))
        self.tool("lipo", 'case "$2" in *libvulkan_kosmickrisp.dylib) printf "%s\\n" "${MOCK_DRIVER_ARCH:-${MOCK_ARCH:-arm64}}" ;; *) printf "%s\\n" "${MOCK_ARCH:-arm64}" ;; esac')
        self.tool("codesign", 'exit "${MOCK_SIGN_EXIT:-0}"')
        self.tool("otool", 'printf "library:\\n @loader_path/library (id)\\n ${MOCK_DEP:-/usr/lib/libSystem.B.dylib} (dependency)\\n"')
        self.tool("ditto", 'exec python3 -c \'import shutil,sys; shutil.copytree(sys.argv[1],sys.argv[2])\' "$1" "$2"')

    def tool(self, name, body):
        path = self.tools / name
        path.write_text("#!/bin/bash\n" + body + "\n")
        path.chmod(0o755)

    def install(self, **values):
        return subprocess.run(["bash", str(ROOT / "arm64/install-kosmickrisp.sh"), str(self.wine), str(self.bundle)],
                              env=dict(os.environ, PATH=str(self.tools) + os.pathsep + os.environ["PATH"], **values),
                              capture_output=True, text=True)

    def test_native_bundle_installs_relocated_launcher(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.wine / "lib/kosmickrisp/SOURCE.txt").exists())
        self.assertEqual((self.wine / "bin/wine-kosmickrisp").read_bytes(),
                         (ROOT / "runtime/kosmickrisp/wine-kosmickrisp-arm64").read_bytes())

    def test_wrong_architecture_does_not_install(self):
        self.assertNotEqual(self.install(MOCK_ARCH="x86_64").returncode, 0)
        self.assertFalse((self.wine / "lib/kosmickrisp").exists())

    def test_mixed_architecture_does_not_install(self):
        self.assertNotEqual(self.install(MOCK_DRIVER_ARCH="x86_64").returncode, 0)
        self.assertFalse((self.wine / "lib/kosmickrisp").exists())

    def test_manifest_cannot_select_an_external_library(self):
        (self.bundle / "kosmickrisp_icd.json").write_text(json.dumps({"ICD": {"library_path": "/foreign/driver.dylib"}}))
        self.assertNotEqual(self.install().returncode, 0)
        self.assertFalse((self.wine / "lib/kosmickrisp").exists())

    def test_missing_override_does_not_install(self):
        (self.wine / "lib/wine/aarch64-unix/win32u.so").write_text("no loader override")
        self.assertNotEqual(self.install().returncode, 0)
        self.assertFalse((self.wine / "lib/kosmickrisp").exists())

    def test_missing_bundle_component(self):
        (self.bundle / "kosmickrisp_icd.json").unlink()
        self.assertNotEqual(self.install().returncode, 0)
        self.assertFalse((self.wine / "lib/kosmickrisp").exists())

    def test_unbundled_dependency_does_not_install(self):
        self.assertNotEqual(self.install(MOCK_DEP="@rpath/unbundled.dylib").returncode, 0)
        self.assertFalse((self.wine / "lib/kosmickrisp").exists())

    def test_bad_signature_does_not_install(self):
        self.assertNotEqual(self.install(MOCK_SIGN_EXIT="1").returncode, 0)
        self.assertFalse((self.wine / "lib/kosmickrisp").exists())

    def test_existing_install_is_preserved(self):
        installed = self.wine / "lib/kosmickrisp"
        installed.mkdir()
        (installed / "SOURCE.txt").write_text("original")
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual((installed / "SOURCE.txt").read_text(), "original")

    @unittest.skipUnless(platform.system() == "Darwin" and platform.machine() == "arm64", "native arch launcher needs Apple Silicon")
    def test_arm64_launcher_environment_arguments_and_exit(self):
        self.assertEqual(self.install().returncode, 0)
        fake = self.wine / "bin/wine"
        fake.write_text('#!/usr/bin/env python3\nimport json,os,sys\nprint(json.dumps({"args":sys.argv[1:],"env":dict(os.environ)}))\nsys.exit(17)\n')
        fake.chmod(0o755)
        env = dict(os.environ, WINEPREFIX="prefix with spaces", WINE_VULKAN_LIBRARY="wrong.dylib",
                   VK_ICD_FILENAMES="wrong.json", CX_ACTIVE_GRAPHICS_BACKEND="dxmt")
        result = subprocess.run([str(self.wine / "bin/wine-kosmickrisp"), "game with spaces.exe", "", "$literal"],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 17, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["args"], ["game with spaces.exe", "", "$literal"])
        self.assertEqual(report["env"]["CX_ACTIVE_GRAPHICS_BACKEND"], "wined3d")
        self.assertEqual(report["env"]["WINEPREFIX"], "prefix with spaces")
        self.assertEqual(Path(report["env"]["CX_LIBVULKAN"]).resolve(), self.wine / "lib/kosmickrisp/libvulkan.1.dylib")
        self.assertNotIn("WINE_VULKAN_LIBRARY", report["env"])
        self.assertNotIn("VK_ICD_FILENAMES", report["env"])


if __name__ == "__main__":
    unittest.main()
