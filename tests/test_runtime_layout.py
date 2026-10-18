import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_runtime_layout', ROOT / 'tools/check_runtime_layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)
CONTRACT = json.loads((ROOT / 'contracts/runtime-layout.json').read_text())


class RuntimeLayoutTests(unittest.TestCase):
    def tree(self, paths):
        root = Path(tempfile.mkdtemp())
        for path in paths:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text('')
        return root

    def test_new_layout_requires_driver_even_without_flag(self):
        root = self.tree(CONTRACT['required'])
        self.assertEqual(layout.missing(root, CONTRACT, kosmickrisp=False), [])
        (root / 'Wine/lib/kosmickrisp/libvulkan.1.dylib').unlink()
        self.assertIn('Wine/lib/kosmickrisp/libvulkan.1.dylib',
                      layout.missing(root, CONTRACT, kosmickrisp=False))

    def test_rejects_stale_payload_and_symlink_target(self):
        root = self.tree(CONTRACT['required'])
        (root / 'DXVK').mkdir()
        (root / 'Wine/lib/stale.dylib').symlink_to('/old/libMoltenVK.dylib')
        self.assertEqual(set(layout.forbidden(root, CONTRACT, inspect_macho=False)),
                         {'DXVK', 'Wine/lib/stale.dylib'})

    def test_rejects_macho_dependency_even_with_an_innocent_filename(self):
        from unittest.mock import patch
        root = self.tree(['Wine/lib/bridge.dylib'])
        (root / 'Wine/lib/bridge.dylib').write_bytes(bytes.fromhex('cffaedfe'))
        with patch.object(layout.subprocess, 'check_output', return_value='@rpath/libMoltenVK.dylib'):
            self.assertEqual(layout.forbidden(root, CONTRACT),
                             ['Wine/lib/bridge.dylib: MoltenVK load command'])

    def test_legacy_contract_remains_readable(self):
        old = {'schema': 1, 'required': ['Wine/bin/wine64'], 'kosmickrisp': ['driver']}
        root = self.tree(old['required'])
        self.assertEqual(layout.missing(root, old, False), [])
        self.assertEqual(layout.missing(root, old, True), ['driver'])

    def test_every_missing_path_is_reported(self):
        root = self.tree(CONTRACT['required'][1:])
        self.assertEqual(layout.missing(root, CONTRACT, kosmickrisp=False), CONTRACT['required'][:1])

    def test_relay12_builtins_whisky_imports_are_in_the_contract(self):
        for module in ('d3d11on12core', 'd3d11on12', 'd3d11on12host', 'dxilconv'):
            self.assertIn(f'Wine/lib/wine/x86_64-windows/{module}.dll', CONTRACT['required'])


if __name__ == '__main__':
    unittest.main()
