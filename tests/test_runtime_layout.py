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

    def test_complete_tree_passes_and_kosmickrisp_is_opt_in(self):
        root = self.tree(CONTRACT['required'])
        self.assertEqual(layout.missing(root, CONTRACT, kosmickrisp=False), [])
        self.assertEqual(layout.missing(root, CONTRACT, kosmickrisp=True), CONTRACT['kosmickrisp'])

    def test_every_missing_path_is_reported(self):
        root = self.tree(CONTRACT['required'][1:])
        self.assertEqual(layout.missing(root, CONTRACT, kosmickrisp=False), CONTRACT['required'][:1])

    def test_relay12_builtins_whisky_imports_are_in_the_contract(self):
        for module in ('d3d11on12core', 'd3d11on12', 'd3d11on12host', 'dxilconv'):
            self.assertIn(f'Wine/lib/wine/x86_64-windows/{module}.dll', CONTRACT['required'])


if __name__ == '__main__':
    unittest.main()
