import hashlib
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bump_pin', ROOT / 'tools/build/bump_pin.py')
bump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bump)

SHA = 'a' * 40


class SetPinsTests(unittest.TestCase):
    def test_rewrites_only_named_keys_and_keeps_export(self):
        text = '# comment\nexport WINECX_COMMIT=old\nexport NIXPKGS_REV=keep\nPLAIN=x\n'
        out = bump.set_pins(text, {'WINECX_COMMIT': 'new', 'PLAIN': 'y'})
        self.assertEqual(out, '# comment\nexport WINECX_COMMIT=new\nexport NIXPKGS_REV=keep\nPLAIN=y\n')

    def test_missing_key_is_an_error(self):
        with self.assertRaises(KeyError):
            bump.set_pins('A=1\n', {'B': '2'})

    def test_real_pin_files_carry_every_bumped_key(self):
        bump.set_pins(bump.BUILD_PINS.read_text(), {
            'WINECX_COMMIT': SHA, 'FAUDIO_VERSION': '26.10', 'RELAY12_COMMIT': SHA,
            'RELAY12_RELEASE_TAG': 'runtime-aaaaaaa', 'RELAY12_ARTIFACT_SHA256': 'b' * 64})
        bump.set_pins(bump.KOSMICKRISP_PINS.read_text(), {'KOSMICKRISP_MESA_COMMIT': SHA})


class PlanTests(unittest.TestCase):
    def test_winecx_reads_the_vendored_faudio_version(self):
        header = b'#define FAUDIO_MAJOR_VERSION\t26\n#define FAUDIO_MINOR_VERSION\t 9\n'
        path, values = bump.plan('winecx', SHA, fetcher=lambda url: header)
        self.assertEqual(path, bump.BUILD_PINS)
        self.assertEqual(values, {'WINECX_COMMIT': SHA, 'FAUDIO_VERSION': '26.09'})

    def test_relay12_archive_must_match_the_reported_digest(self):
        archive = b'relay12 archive'
        digest = hashlib.sha256(archive).hexdigest()
        _, values = bump.plan('relay12', SHA, 'runtime-aaaaaaa', digest, fetcher=lambda url: archive)
        self.assertEqual(values['RELAY12_ARTIFACT_SHA256'], digest)
        with self.assertRaises(ValueError):
            bump.plan('relay12', SHA, 'runtime-aaaaaaa', 'c' * 64, fetcher=lambda url: archive)

    def test_rejects_abbreviated_shas_and_unknown_components(self):
        with self.assertRaises(ValueError):
            bump.plan('mesa', 'abc123')
        with self.assertRaises(ValueError):
            bump.plan('dxvk', SHA)


if __name__ == '__main__':
    unittest.main()
