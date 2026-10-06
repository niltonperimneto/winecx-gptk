import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run_kosmickrisp_integer_replay as integer
import run_kosmickrisp_point_replay as point


class OutputReplayTests(unittest.TestCase):
    def setUp(self):
        self.original = Path(__file__).with_name('kosmickrisp_interpolation.c').read_text()

    def test_point_rejects_missing_draw_anchor(self):
        with self.assertRaises(ValueError):
            point.point_harness(self.original.replace('vkCmdDraw(command, 3, 1, 0, 0);', ''))

    def test_point_rejects_ambiguous_readback(self):
        anchor = '        for (unsigned y = 1; y < 7; ++y) for (unsigned x = 1; x < 7; ++x) {'
        with self.assertRaises(ValueError):
            point.point_harness(self.original + anchor)

    def test_integer_rejects_unexpected_attachment(self):
        with self.assertRaises(ValueError):
            integer.integer_harness(self.original.replace('VK_FORMAT_R32G32B32A32_SFLOAT', 'VK_FORMAT_R32_UINT', 1))

    def test_integer_rejects_missing_clear_boundary(self):
        with self.assertRaises(ValueError):
            integer.integer_harness(self.original.replace('        VkRenderPassBeginInfo render_begin = ', ''))

    def test_integer_format_guard(self):
        headers = Path(os.environ.get('KK_TEST_VULKAN_HEADERS', '../kk-shader-build/headers/include')).resolve()
        if not (headers / 'vulkan/vulkan.h').is_file():
            self.skipTest('Vulkan headers unavailable for CPU format-guard test')
        code = '''#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
static VkFormatFeatureFlags supported;
static int available = 1;
static void VKAPI_CALL query(VkPhysicalDevice physical, VkFormat format, VkFormatProperties *out)
{
    assert(format == VK_FORMAT_R32G32B32A32_UINT);
    *out = (VkFormatProperties){.optimalTilingFeatures = supported};
}
static PFN_vkVoidFunction VKAPI_CALL resolve(VkInstance instance, const char *name)
{
    return available ? (PFN_vkVoidFunction)query : NULL;
}
static int guard(const char *blend_mode)
{
    PFN_vkGetInstanceProcAddr gipa = resolve;
    VkInstance instance = VK_NULL_HANDLE;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
''' + integer.FORMAT_CHECK + '''    return 0;
}
int main(void)
{
    supported = 0;
    assert(guard(NULL) == 77);
    supported = VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT;
    assert(guard(NULL) == 77);
    supported |= VK_FORMAT_FEATURE_TRANSFER_SRC_BIT;
    assert(guard(NULL) == 0);
    assert(guard("add") == 77);
    supported |= VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BLEND_BIT;
    assert(guard("add") == 0);
    available = 0;
    assert(guard(NULL) == 1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            source, binary = Path(temp) / 'guard.c', Path(temp) / 'guard'
            source.write_text(code)
            compiled = subprocess.run(['clang', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-parameter', '-I' + str(headers), str(source), '-o', str(binary)],
                capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_runner_requires_warm_readiness_and_preserves_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            icd = root / 'icd'; icd.write_bytes(b'fixture')
            headers = root / 'headers'; (headers / 'vulkan').mkdir(parents=True)
            (headers / 'vulkan/vulkan.h').touch()
            out = root / 'out'
            results = [{'name': 'integer-default', 'phase': phase,
                'status': 'fail' if phase == 'warm' else 'pass',
                'reasons': ['draw work'] if phase == 'warm' else []}
                for phase in ('cold', 'warm', 'cold', 'warm', 'cold', 'warm')]
            with patch('sys.argv', ['test', '--icd', str(icd), '--headers', str(headers), '--out', str(out)]), \
                 patch.object(integer, 'prepare_integer', return_value=root / 'probe'), \
                 patch.object(integer.shutil, 'which', return_value='tool'), \
                 patch.object(integer, 'run_probe', side_effect=results) as run:
                self.assertEqual(integer.main(), 1)
            self.assertEqual([call.kwargs['require_zero'] for call in run.call_args_list],
                [False, True, False, True, False, True])
            report = json.loads((out / 'report.json').read_text())
            self.assertEqual(report['counts']['fail'], 3)
            self.assertEqual(report['counts']['pass'], 3)

    def test_integer_skip_does_not_become_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            icd = root / 'icd'; icd.write_bytes(b'fixture')
            headers = root / 'headers'; (headers / 'vulkan').mkdir(parents=True)
            (headers / 'vulkan/vulkan.h').touch()
            out = root / 'out'
            skipped = {'status': 'skip', 'reasons': [], 'phase': 'cold'}
            with patch('sys.argv', ['test', '--icd', str(icd), '--headers', str(headers), '--out', str(out)]), \
                 patch.object(integer, 'prepare_integer', return_value=root / 'probe'), \
                 patch.object(integer.shutil, 'which', return_value='tool'), \
                 patch.object(integer, 'run_probe', return_value=skipped) as run:
                self.assertEqual(integer.main(), 0)
            self.assertEqual(run.call_count, 3)
            report = json.loads((out / 'report.json').read_text())
            self.assertEqual(report['counts']['skip'], 3)
            self.assertEqual(report['counts']['pass'], 0)


if __name__ == '__main__':
    unittest.main()
