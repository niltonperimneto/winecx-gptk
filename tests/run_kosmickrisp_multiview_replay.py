import argparse
import json
from pathlib import Path
import shutil
import subprocess

from run_kosmickrisp_gpl_batch import prepare, scenario
from run_kosmickrisp_variant_replay import run_probe


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Multiview harness anchor changed: ' + old[:80])
    return source.replace(old, new, 1)


def multiview_source(source, clear=True):
    replacements = [
        ('    VkPhysicalDeviceColorWriteEnableFeaturesEXT color_write_features = {',
         '    VkPhysicalDeviceMultiviewFeatures multiview = { .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MULTIVIEW_FEATURES };\n'
         '    VkPhysicalDeviceColorWriteEnableFeaturesEXT color_write_features = {'),
        ('        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COLOR_WRITE_ENABLE_FEATURES_EXT };',
         '        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COLOR_WRITE_ENABLE_FEATURES_EXT, .pNext = &multiview };'),
        ('    vkGetPhysicalDeviceFeatures2(physical, &features);',
         '    vkGetPhysicalDeviceFeatures2(physical, &features);\n'
         '    if (!multiview.multiview) return 77;\n'
         '    multiview.multiviewGeometryShader = VK_FALSE;\n'
         '    multiview.multiviewTessellationShader = VK_FALSE;'),
        ('    provoking.pNext = objects ? (void *)&object_features : dynamic_pso ? (void *)&dynamic_features : NULL;',
         '    provoking.pNext = objects ? (void *)&object_features : dynamic_pso ? (void *)&dynamic_features : (void *)&multiview;'),
        ('    VkImageSubresourceRange range = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 };',
         '    VkImageSubresourceRange range = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 2 };'),
        ('            .extent = {8, 8, 1}, .mipLevels = 1, .arrayLayers = 1,',
         '            .extent = {8, 8, 1}, .mipLevels = 1, .arrayLayers = 2,'),
        ('            .image = images[i], .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = info.format, .subresourceRange = range };',
         '            .image = images[i], .viewType = VK_IMAGE_VIEW_TYPE_2D_ARRAY, .format = info.format, .subresourceRange = range };'),
        ('        .size = descriptors ? uniform_offsets[1] + 16 : 1024,',
         '        .size = descriptors ? uniform_offsets[1] + 16 : 2048,'),
        ('    VkRenderPassCreateInfo render_info = { .sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO,',
         '    uint32_t view_mask = 3;\n'
         '    VkRenderPassMultiviewCreateInfo multiview_info = {\n'
         '        .sType = VK_STRUCTURE_TYPE_RENDER_PASS_MULTIVIEW_CREATE_INFO,\n'
         '        .subpassCount = 1, .pViewMasks = &view_mask };\n'
         '    VkRenderPassCreateInfo render_info = { .sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO, .pNext = &multiview_info,'),
        ('        VkBufferImageCopy copy = { .imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1}, .imageExtent = {8, 8, 1} };',
         '        VkBufferImageCopy copy = { .imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 2}, .imageExtent = {8, 8, 1} };'),
    ]
    for old, new in replacements:
        source = replace_once(source, old, new)
    if not clear:
        source = replace_once(source,
            '.samples = i ? VK_SAMPLE_COUNT_1_BIT : sample_count, .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,',
            '.samples = i ? VK_SAMPLE_COUNT_1_BIT : sample_count, .loadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE,')
    first = source.index('        for (unsigned y = 1; y < 7; ++y) for (unsigned x = 1; x < 7; ++x) {')
    last = source.index('        printf("stage=%s case=%d gpl=%d last=%d samples=%d result=%s', first)
    source = source[:first] + '''        for (unsigned layer = 0; layer < 2; ++layer) {
            float expected = .25f + .5f * layer;
            for (unsigned y = 1; y < 7; ++y) for (unsigned x = 1; x < 7; ++x) {
                float actual = pixels[(layer * 64 + y * 8 + x) * 4];
                if (!isfinite(actual) || fabsf(actual - expected) > .0001f) {
                    fprintf(stderr, "layer %u pixel %u,%u: %f expected %f\\n", layer, x, y, actual, expected);
                    failed = 1;
                }
            }
            printf("MULTIVIEW layer=%u expected=%f result=%s\\n", layer, expected, failed ? "FAIL" : "PASS");
        }
''' + source[last:]
    return source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--icd', required=True, type=Path)
    parser.add_argument('--headers', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    icd, headers, out = args.icd.resolve(), args.headers.resolve(), args.out.resolve()
    if not icd.is_file() or not (headers / 'vulkan/vulkan.h').is_file():
        parser.error('ICD or Vulkan headers do not exist')
    if args.timeout <= 0 or not shutil.which('clang') or not shutil.which('glslangValidator'):
        parser.error('Positive timeout, clang and glslangValidator are required')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        parser.error('Output directory must be empty to preserve evidence')
    out.mkdir(parents=True, exist_ok=True)
    tests = Path(__file__).resolve().parent
    prepare(out, headers)
    probes = {}
    for clear in (False, True):
        label = 'clear' if clear else 'raster'
        source = out / ('multiview-' + label + '.c')
        source.write_text(multiview_source((tests / 'kosmickrisp_interpolation.c').read_text(), clear=clear))
        probe = out / ('multiview-' + label + '-probe')
        subprocess.run(['clang', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
            '-I' + str(headers), '-I' + str(tests), str(source), '-o', str(probe)], check=True)
        probes[clear] = probe
    fragment = out / 'multiview.frag'
    fragment.write_text('''#version 450
#extension GL_EXT_multiview : require
layout(location=0) out vec4 color;
void main() { color = vec4(.25 + .5 * float(gl_ViewIndex), 0, 0, 1); }
''')
    subprocess.run(['glslangValidator', '-V', '-S', 'frag', str(fragment),
        '-o', str(out / 'vs-frag-1.spv')], check=True)
    report = {'schema': 1, 'fixture': 'Two layers, viewMask=3, distinct gl_ViewIndex outputs',
        'scope': 'Raster replay requires zero warm draw work; layered meta clear is measured separately.',
        'known_gap': 'Layered load-op clear creates a meta pipeline at command recording even on a warm cache.',
        'results': []}
    for clear in (False, True):
        item = scenario('multiview-clear' if clear else 'multiview-raster')
        for phase in ('cold', 'warm', 'warm2'):
            row = run_probe(probes[clear], icd, out, item, out / item['name'], phase, args.timeout,
                require_zero=not clear and phase != 'cold')
            blocking = {name: value.get('draw_count', 0) for name, value in row.get('variant_stats', {}).items()
                if name in ('fs_prepare', 'fs_wait', 'raster_prepare', 'raster_wait', 'pso_create',
                            'pso_wait', 'archive_lookup', 'archive_load', 'native_create') and value.get('draw_count', 0)}
            row['zero_target_met'] = not blocking
            row['draw_variant_work'] = blocking
            report['results'].append(row)
            (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print(item['name'], phase, row['status'], 'zero_target_met=' + str(row['zero_target_met']),
                '; '.join(row['reasons']), flush=True)
            if row['status'] != 'pass':
                break
    return int(any(row['status'] == 'fail' for row in report['results']))


if __name__ == '__main__':
    raise SystemExit(main())
