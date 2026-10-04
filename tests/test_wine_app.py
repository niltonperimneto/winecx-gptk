"""Exercise make-wine-app.sh's profile checks and bundle layout with stand-in tools."""
import datetime
import hashlib
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENTITLEMENT = "com.apple.developer.cross-architecture-support"
TEAM = "ABCDE12345"
DEVICE = "00008140-0000000000000001"
CERTIFICATE = b"stand-in developer certificate"
IDENTITY = hashlib.sha1(CERTIFICATE).hexdigest().upper()


def write_tool(directory, name, body):
    path = directory / name
    path.write_text("#!/bin/bash\n" + body + "\n")
    path.chmod(0o755)


class MakeWineAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wine app ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.executable = self.root / "loader"
        self.executable.write_text("arm64 loader")
        self.profile = self.root / "profile.provisionprofile"
        self.app = self.root / "out/wine.app"
        self.app.parent.mkdir()
        self.signed = self.root / "signed-entitlements.plist"
        self.write_profile()
        write_tool(self.tools, "lipo", 'printf "%s\\n" "${MOCK_ARCH:-arm64}"')
        # `security cms -D` decodes the CMS envelope; the stand-in profile is a bare plist.
        write_tool(self.tools, "security", f'''case "$1" in
    find-identity) echo '  1) {IDENTITY} "Apple Development: test"' ;;
    cms) cat "$4" ;;
esac''')
        write_tool(self.tools, "system_profiler", f'echo "      Provisioning UDID: {DEVICE}"')
        write_tool(self.tools, "codesign", f'''for ((i = 1; i <= $#; i++)); do
    if [ "${{!i}}" = --entitlements ] && [ "$1" = --force ]; then next=$((i + 1)); cp "${{!next}}" "{self.signed}"; fi
done
if [ "$1" = -d ]; then cat "{self.signed}"; fi
exit "${{MOCK_SIGN_EXIT:-0}}"''')

    def write_profile(self, **changes):
        profile = {
            "Name": "Wine cross-architecture",
            "Platform": ["OSX"],
            "TeamIdentifier": [TEAM],
            "ExpirationDate": datetime.datetime.now() + datetime.timedelta(days=30),
            "DeveloperCertificates": [CERTIFICATE],
            "ProvisionedDevices": [DEVICE],
            "Entitlements": {ENTITLEMENT: True, "com.apple.application-identifier": f"{TEAM}.org.example.wine"},
        }
        profile.update(changes)
        self.profile.write_bytes(plistlib.dumps(profile))

    def make(self, *links, identity=IDENTITY, **values):
        return subprocess.run(["bash", str(ROOT / "arm64/make-wine-app.sh"), str(self.executable), str(self.app),
                               str(self.profile), identity, *links],
                              env=dict(os.environ, PATH=str(self.tools) + os.pathsep + os.environ["PATH"], **values),
                              capture_output=True, text=True)

    def assertRefused(self, result, message):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertFalse(self.app.exists())

    def test_valid_profile_builds_signed_bundle(self):
        result = self.make("ntdll.so=../../../ntdll.so")
        self.assertEqual(result.returncode, 0, result.stderr)
        contents = self.app / "Contents"
        self.assertEqual((contents / "MacOS/wine").read_text(), "arm64 loader")
        self.assertEqual(os.readlink(contents / "MacOS/ntdll.so"), "../../../ntdll.so")
        self.assertEqual((contents / "embedded.provisionprofile").read_bytes(), self.profile.read_bytes())
        info = plistlib.loads((contents / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleIdentifier"], "org.example.wine")
        self.assertEqual(info["CFBundleExecutable"], "wine")
        signed = plistlib.loads(self.signed.read_bytes())
        self.assertIs(signed[ENTITLEMENT], True)
        self.assertEqual(signed["com.apple.application-identifier"], f"{TEAM}.org.example.wine")
        self.assertEqual(signed["com.apple.developer.team-identifier"], TEAM)

    def test_profile_without_entitlement(self):
        self.write_profile(Entitlements={"com.apple.application-identifier": f"{TEAM}.org.example.wine"})
        self.assertRefused(self.make(), f"does not grant {ENTITLEMENT}")

    def test_expired_profile(self):
        self.write_profile(ExpirationDate=datetime.datetime(2020, 1, 1))
        self.assertRefused(self.make(), "expired")

    def test_profile_for_another_certificate(self):
        self.write_profile(DeveloperCertificates=[b"someone else"])
        self.assertRefused(self.make(), f"was not issued for signing identity {IDENTITY}")

    def test_profile_without_this_mac(self):
        self.write_profile(ProvisionedDevices=["00008140-0000000000000002"])
        self.assertRefused(self.make(), "does not include this Mac")

    def test_all_devices_profile_covers_this_mac(self):
        self.write_profile(ProvisionsAllDevices=True, ProvisionedDevices=[])
        result = self.make()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wildcard_app_id(self):
        self.write_profile(Entitlements={ENTITLEMENT: True, "com.apple.application-identifier": f"{TEAM}.*"})
        self.assertRefused(self.make(), "needs an explicit App ID")

    def test_ios_profile(self):
        self.write_profile(Platform=["iOS"])
        self.assertRefused(self.make(), "is not a macOS profile")

    def test_unknown_identity(self):
        self.assertRefused(self.make(identity="0" * 40), "No valid codesigning identity")

    def test_wrong_architecture(self):
        self.assertRefused(self.make(MOCK_ARCH="x86_64"), "Not an arm64 executable")

    def test_signing_failure_leaves_no_bundle(self):
        self.assertNotEqual(self.make(MOCK_SIGN_EXIT="1").returncode, 0)
        self.assertFalse(self.app.exists())

    def test_existing_bundle_is_preserved(self):
        self.app.mkdir()
        (self.app / "marker").write_text("original")
        self.assertNotEqual(self.make().returncode, 0)
        self.assertEqual((self.app / "marker").read_text(), "original")


if __name__ == "__main__":
    unittest.main()
