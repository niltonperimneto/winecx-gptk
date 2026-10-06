from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_kosmickrisp_multiview_replay import multiview_source


class MultiviewReplayTests(unittest.TestCase):
    def test_both_layers_and_view_mask_are_consistent(self):
        base = Path(__file__).with_name('kosmickrisp_interpolation.c').read_text()
        source = multiview_source(base)
        self.assertIn('if (!multiview.multiview) return 77;', source)
        self.assertIn('.pNext = &multiview };', source)
        self.assertIn('uint32_t view_mask = 3;', source)
        self.assertIn('.arrayLayers = 2,', source)
        self.assertIn('.viewType = VK_IMAGE_VIEW_TYPE_2D_ARRAY', source)
        self.assertIn('0, 1, 0, 2 };', source)
        self.assertIn('0, 0, 2}, .imageExtent', source)
        self.assertIn('layer * 64 + y * 8 + x', source)
        self.assertIn('float expected = .25f + .5f * layer;', source)
        self.assertIn('uniform_offsets[1] + 16 : 2048', source)

    def test_raster_case_excludes_measured_meta_clear(self):
        base = Path(__file__).with_name('kosmickrisp_interpolation.c').read_text()
        source = multiview_source(base, clear=False)
        self.assertIn('sample_count, .loadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE,', source)
        self.assertIn('sample_count, .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,', multiview_source(base))

    def test_changed_base_anchor_fails_loudly(self):
        base = Path(__file__).with_name('kosmickrisp_interpolation.c').read_text()
        with self.assertRaisesRegex(ValueError, 'anchor changed'):
            multiview_source(base.replace('.arrayLayers = 1,', '.arrayLayers = 4,'))


if __name__ == '__main__':
    unittest.main()
