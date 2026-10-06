from pathlib import Path
import unittest

from run_kosmickrisp_attachment_replay import attachment_source


class AttachmentReplayTests(unittest.TestCase):
    def test_pipeline_and_command_mappings_match(self):
        source = attachment_source(Path(__file__).with_name('kosmickrisp_interpolation.c').read_text())
        self.assertIn('if (!f13.dynamicRendering || !local_read.dynamicRenderingLocalRead) return 77;', source)
        self.assertIn('uint32_t output_location = 1;', source)
        self.assertIn('.pColorAttachmentLocations = &output_location', source)
        self.assertIn('command_locations.pNext = NULL;', source)
        self.assertIn('if (!map_before_bind) set_locations', source)
        self.assertIn('if (map_before_bind) {', source)
        self.assertIn('.renderPass = VK_NULL_HANDLE', source)
        self.assertIn('pixel < 64', source)
        self.assertNotIn('VK_DYNAMIC_STATE_RENDERING_ATTACHMENT_LOCATIONS', source)

    def test_missing_capability_anchor_is_rejected(self):
        source = Path(__file__).with_name('kosmickrisp_interpolation.c').read_text()
        with self.assertRaisesRegex(ValueError, 'anchor changed'):
            attachment_source(source.replace('    vkGetPhysicalDeviceFeatures2(physical, &features);', ''))


if __name__ == '__main__':
    unittest.main()
