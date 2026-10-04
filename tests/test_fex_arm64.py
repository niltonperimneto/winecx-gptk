"""Exercise FEX bundle installation and packaging with stand-in files, without Wine."""
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PE_FILES = ("aarch64-windows/xtajit64.dll", "aarch64-windows/xtajit.dll")
SO_FILES = ("aarch64-unix/libarm64ecfex.so", "aarch64-unix/libwow64fex.so")


ARM64, AMD64 = 0xaa64, 0x8664


def pe_image(machine=ARM64, chpe=False, marker=b"Wine builtin DLL"):
    """A minimal PE32+ image; chpe adds the hybrid metadata ARM64EC/ARM64X carry."""
    data = bytearray(0x400)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3c, 0x80)
    data[0x40:0x40 + len(marker)] = marker
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, machine, 1, 0, 0, 0, 0xf0, 0x2022)
    optional = 0x98
    struct.pack_into("<H", data, optional, 0x20b)
    struct.pack_into("<II", data, optional + 112 + 10 * 8, 0x1000, 0x140)  # load config
    struct.pack_into("<8sIIII", data, optional + 0xf0, b".rdata", 0x1000, 0x1000, 0x200, 0x200)
    struct.pack_into("<I", data, 0x200, 0x140)
    if chpe:
        struct.pack_into("<Q", data, 0x200 + 0xc8, 0x180001000)
    return bytes(data)


def write_tool(directory, name, body):
    path = directory / name
    path.write_text("#!/bin/bash\n" + body + "\n")
    path.chmod(0o755)


def make_bundle(bundle):
    for name, image in zip(PE_FILES, (pe_image(AMD64, chpe=True), pe_image(ARM64))):
        (bundle / name).parent.mkdir(parents=True, exist_ok=True)
        (bundle / name).write_bytes(image)
    for name in SO_FILES:
        (bundle / name).parent.mkdir(parents=True, exist_ok=True)
        (bundle / name).write_text("bundle " + name)
    (bundle / "SOURCE.txt").write_text("FEX_COMMIT=test\n")
    (bundle / "licenses").mkdir()
    (bundle / "licenses/fex.txt").write_text("MIT")


class InstallFexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fex install ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.wine = self.root / "Wine"
        self.bundle = self.root / "bundle"
        self.tools = self.root / "tools"
        for path in (self.wine / "lib/wine/aarch64-unix", self.wine / "lib/wine/aarch64-windows", self.bundle, self.tools):
            path.mkdir(parents=True)
        make_bundle(self.bundle)
        write_tool(self.tools, "lipo", 'printf "%s\\n" "${MOCK_ARCH:-arm64}"')
        write_tool(self.tools, "codesign", 'exit "${MOCK_SIGN_EXIT:-0}"')

    def install(self, **values):
        return subprocess.run(["bash", str(ROOT / "arm64/install-fex.sh"), str(self.wine), str(self.bundle)],
                              env=dict(os.environ, PATH=str(self.tools) + os.pathsep + os.environ["PATH"], **values),
                              capture_output=True, text=True)

    def assertNothingInstalled(self):
        self.assertFalse((self.wine / "lib/fex").exists())
        for name in PE_FILES + SO_FILES:
            self.assertFalse((self.wine / "lib/wine" / name).exists(), name)

    def test_bundle_installs_with_provenance(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in PE_FILES + SO_FILES:
            self.assertEqual((self.wine / "lib/wine" / name).read_bytes(), (self.bundle / name).read_bytes(), name)
        self.assertEqual((self.wine / "lib/fex/SOURCE.txt").read_text(), "FEX_COMMIT=test\n")
        self.assertTrue((self.wine / "lib/fex/licenses/fex.txt").exists())

    def test_missing_component_does_not_install(self):
        for name in PE_FILES + SO_FILES + ("SOURCE.txt",):
            with self.subTest(name=name):
                saved = (self.bundle / name).read_bytes()
                (self.bundle / name).unlink()
                self.assertNotEqual(self.install().returncode, 0)
                self.assertNothingInstalled()
                (self.bundle / name).write_bytes(saved)

    def test_wrong_architecture_helper_does_not_install(self):
        self.assertNotEqual(self.install(MOCK_ARCH="x86_64").returncode, 0)
        self.assertNothingInstalled()

    def test_x86_64_translator_does_not_install(self):
        for name in PE_FILES:
            with self.subTest(name=name):
                saved = (self.bundle / name).read_bytes()
                (self.bundle / name).write_bytes(pe_image(AMD64))
                self.assertNotEqual(self.install().returncode, 0)
                self.assertNothingInstalled()
                (self.bundle / name).write_bytes(saved)

    def test_plain_arm64_image_as_arm64ec_translator_does_not_install(self):
        (self.bundle / PE_FILES[0]).write_bytes(pe_image(ARM64))
        self.assertNotEqual(self.install().returncode, 0)
        self.assertNothingInstalled()

    def test_hybrid_image_as_wow64_translator_does_not_install(self):
        for image in (pe_image(AMD64, chpe=True), pe_image(ARM64, chpe=True)):
            with self.subTest(machine=image[0x84:0x86].hex()):
                (self.bundle / PE_FILES[1]).write_bytes(image)
                self.assertNotEqual(self.install().returncode, 0)
                self.assertNothingInstalled()

    def test_arm64x_translator_installs(self):
        (self.bundle / PE_FILES[0]).write_bytes(pe_image(ARM64, chpe=True))
        self.assertEqual(self.install().returncode, 0)

    def test_truncated_translator_does_not_install(self):
        (self.bundle / PE_FILES[0]).write_bytes(pe_image(AMD64, chpe=True)[:0x100])
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNothingInstalled()

    @unittest.skipUnless(os.environ.get("FEX_TEST_BUNDLE"), "set FEX_TEST_BUNDLE to a build-fex-arm64.sh output")
    def test_real_bundle_installs(self):
        result = subprocess.run(["bash", str(ROOT / "arm64/install-fex.sh"), str(self.wine), os.environ["FEX_TEST_BUNDLE"]],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_translator_without_builtin_marker_does_not_install(self):
        (self.bundle / PE_FILES[0]).write_bytes(pe_image(marker=b"\0" * 16))
        self.assertNotEqual(self.install().returncode, 0)
        self.assertNothingInstalled()

    def test_non_pe_translator_does_not_install(self):
        (self.bundle / PE_FILES[0]).write_text("not a dll")
        self.assertNotEqual(self.install().returncode, 0)
        self.assertNothingInstalled()

    def test_bad_signature_does_not_install(self):
        self.assertNotEqual(self.install(MOCK_SIGN_EXIT="1").returncode, 0)
        self.assertNothingInstalled()


@unittest.skipUnless(platform.system() == "Darwin", "package-arm64.sh uses macOS cp -c")
class PackageFexTests(unittest.TestCase):
    """Run package-arm64.sh against a stand-in Wine build and base runtime."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fex package ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.scripts = self.root / "arm64"
        self.tools = self.root / "tools"
        self.runtimes = self.root / "Runtimes"
        self.bundle = self.root / "bundle"
        for path in (self.scripts, self.tools, self.bundle):
            path.mkdir()
        for name in ("package-arm64.sh", "install-fex.sh"):
            shutil.copy(ROOT / "arm64" / name, self.scripts / name)
        # Stand-in for `build-arm64-unix.sh install` with DESTDIR=$STAGE.
        write_tool(self.scripts, "build-arm64-unix.sh", 'set -e; W="${MAKEFLAGS_EXTRA#DESTDIR=}/opt/whiskywine"\n'
                   'mkdir -p "$W/bin" "$W/include" "$W/lib/wine/aarch64-unix" "$W/lib/wine/aarch64-windows"\n'
                   'touch "$W/bin/wineserver" "$W/lib/wine/aarch64-unix/ntdll.so" "$W/lib/wine/aarch64-windows/ntdll.dll"\n'
                   'printf "#!/bin/bash\\necho built-loader\\n" > "$W/lib/wine/aarch64-unix/wine"\n'
                   'chmod +x "$W/lib/wine/aarch64-unix/wine"')
        # Stand-in for make-wine-app.sh: its own checks are covered by test_wine_app.py.
        write_tool(self.scripts, "make-wine-app.sh", 'set -e; printf "%s\\n" "$@" > "$MAKE_WINE_APP_LOG"\n'
                   'mkdir -p "$2/Contents/MacOS"; cp "$1" "$2/Contents/MacOS/wine"')
        base = self.runtimes / "whisky-arm64-5.1.1"
        unix = base / "Wine/lib/wine/aarch64-unix"
        windows = base / "Wine/lib/wine/aarch64-windows"
        (unix / "wine.app/Contents/MacOS").mkdir(parents=True)
        windows.mkdir(parents=True)
        (base / "DXMT").mkdir()
        (base / "WhiskyWineVersion.plist").write_text("plist")
        write_tool(unix / "wine.app/Contents/MacOS", "wine", 'echo wine-test')
        for name in ("libstub.dylib", "winemetal.so"):
            (unix / name).write_text("base")
        (windows / "winemetal.dll").write_text("base")
        for name in PE_FILES + SO_FILES:
            (base / "Wine/lib/wine" / name).write_text("base " + name)
        make_bundle(self.bundle)
        self.mono = self.root / "mono.tar.xz"
        with tarfile.open(self.mono, "w:xz") as archive:
            info = tarfile.TarInfo("wine-mono/README")
            archive.addfile(info)
        write_tool(self.tools, "lipo", 'printf "%s\\n" "${MOCK_ARCH:-arm64}"')
        write_tool(self.tools, "codesign", 'exit 0')
        write_tool(self.tools, "otool", 'printf "%s:\\n" "$2"')
        write_tool(self.tools, "install_name_tool", 'exit 0')
        write_tool(self.tools, "plutil", 'echo 1.0')
        write_tool(self.tools, "ditto", 'exec python3 -c \'import shutil,sys; shutil.copytree(sys.argv[1],sys.argv[2])\' "$1" "$2"')

    def package(self, **values):
        env = dict(os.environ, PATH=str(self.tools) + os.pathsep + os.environ["PATH"],
                   RUNTIMES_ROOT=str(self.runtimes), STAGE=str(self.root / "stage"), MONO=str(self.mono), **values)
        return subprocess.run(["bash", str(self.scripts / "package-arm64.sh"), "9.9.9"], env=env, capture_output=True, text=True)

    @property
    def packaged(self):
        return self.runtimes / "whisky-arm64-9.9.9/Wine"

    def test_default_packaging_carries_base_fex(self):
        result = self.package()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in PE_FILES + SO_FILES:
            self.assertEqual((self.packaged / "lib/wine" / name).read_text(), "base " + name)
        self.assertFalse((self.packaged / "lib/fex").exists())
        self.assertEqual((self.packaged / "lib/wine/aarch64-unix/winemetal.so").read_text(), "base")

    def test_fex_bundle_replaces_base_fex(self):
        result = self.package(FEX_BUNDLE=str(self.bundle))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in PE_FILES + SO_FILES:
            self.assertEqual((self.packaged / "lib/wine" / name).read_bytes(), (self.bundle / name).read_bytes(), name)
        self.assertEqual((self.packaged / "lib/fex/SOURCE.txt").read_text(), "FEX_COMMIT=test\n")
        self.assertEqual((self.packaged / "lib/wine/aarch64-unix/winemetal.so").read_text(), "base")

    def test_default_packaging_carries_crossover_loader(self):
        result = self.package()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("wine-test", result.stdout)
        base = self.runtimes / "whisky-arm64-5.1.1/Wine/lib/wine/aarch64-unix/wine.app/Contents/MacOS/wine"
        self.assertEqual((self.packaged / "lib/wine/aarch64-unix/wine.app/Contents/MacOS/wine").read_text(), base.read_text())

    def test_wine_app_profile_signs_built_loader(self):
        log = self.root / "make-wine-app.log"
        result = self.package(WINE_APP_PROFILE="/profiles/wine.provisionprofile", WINE_APP_IDENTITY="A" * 40,
                              MAKE_WINE_APP_LOG=str(log))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        arguments = log.read_text().splitlines()
        self.assertTrue(arguments[0].endswith("/lib/wine/aarch64-unix/wine"))
        self.assertTrue(arguments[1].endswith("/lib/wine/aarch64-unix/wine.app"))
        self.assertEqual(arguments[2:], ["/profiles/wine.provisionprofile", "A" * 40, "ntdll.so=../../../ntdll.so"])
        unix = self.packaged / "lib/wine/aarch64-unix"
        self.assertIn("built-loader", result.stdout)
        self.assertIn("echo built-loader", (unix / "wine.app/Contents/MacOS/wine").read_text())
        self.assertEqual(os.readlink(unix / "wine"), "wine.app/Contents/MacOS/wine")

    def test_wine_app_profile_needs_identity(self):
        self.assertNotEqual(self.package(WINE_APP_PROFILE="/profiles/wine.provisionprofile").returncode, 0)
        self.assertFalse((self.runtimes / "whisky-arm64-9.9.9").exists())

    def test_bad_fex_bundle_stops_packaging(self):
        (self.bundle / SO_FILES[0]).unlink()
        self.assertNotEqual(self.package(FEX_BUNDLE=str(self.bundle)).returncode, 0)
        self.assertFalse((self.runtimes / "whisky-arm64-9.9.9").exists())

    def test_wrong_architecture_fex_bundle_stops_packaging(self):
        self.assertNotEqual(self.package(FEX_BUNDLE=str(self.bundle), MOCK_ARCH="x86_64").returncode, 0)
        self.assertFalse((self.runtimes / "whisky-arm64-9.9.9").exists())


if __name__ == "__main__":
    unittest.main()
