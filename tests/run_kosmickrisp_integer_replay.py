import argparse
import json
from pathlib import Path
import shutil
import subprocess

from run_kosmickrisp_gpl_batch import digest, scenario
from run_kosmickrisp_point_replay import replace_once
from run_kosmickrisp_variant_replay import run_probe


READBACK = '''        for (unsigned y = 0; y < 8; ++y) for (unsigned x = 0; x < 8; ++x) {
            const uint32_t output[4] = {65537u, 123456789u, 0xdeadbeefu, 0xfedcba98u};
            const uint32_t cleared[4] = {31u, 63u, 127u, 255u};
            for (unsigned channel = 0; channel < 4; ++channel) {
                uint32_t expected = blend.colorWriteMask & (1u << channel) ? output[channel] : cleared[channel];
                uint32_t actual = pixels[(y * 8 + x) * 4 + channel];
                if (actual != expected) {
                    fprintf(stderr, "integer pixel %u,%u channel %u: %u expected %u\\n",
                        x, y, channel, actual, expected);
                    failed = 1;
                }
            }
        }
'''

FORMAT_CHECK = '''    PFN_vkGetPhysicalDeviceFormatProperties format_properties =
        (PFN_vkGetPhysicalDeviceFormatProperties)gipa(instance, "vkGetPhysicalDeviceFormatProperties");
    if (!format_properties) return 1;
    VkFormatProperties integer_format;
    format_properties(physical, VK_FORMAT_R32G32B32A32_UINT, &integer_format);
    VkFormatFeatureFlags required_format =
        VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT | VK_FORMAT_FEATURE_TRANSFER_SRC_BIT;
    if ((integer_format.optimalTilingFeatures & required_format) != required_format) {
        fprintf(stderr, "SKIP integer attachment or transfer-source format support unavailable\\n");
        return 77;
    }
    if (blend_mode && !(integer_format.optimalTilingFeatures & VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BLEND_BIT)) {
        fprintf(stderr, "SKIP blend-enable requires format COLOR_ATTACHMENT_BLEND_BIT\\n");
        return 77;
    }
'''


def integer_harness(source):
    if source.count('VK_FORMAT_R32G32B32A32_SFLOAT') != 2:
        raise ValueError('Integer attachment format anchors changed')
    source = source.replace('VK_FORMAT_R32G32B32A32_SFLOAT', 'VK_FORMAT_R32G32B32A32_UINT')
    source = replace_once(source, '    float *pixels;', '    uint32_t *pixels;')
    source = replace_once(source, '    vkGetPhysicalDeviceFeatures2(physical, &features);',
        '    vkGetPhysicalDeviceFeatures2(physical, &features);\n' + FORMAT_CHECK)
    source = replace_once(source,
        '    VkPipelineColorBlendAttachmentState blend = { .colorWriteMask = test == 4 ? 0 : 15 };',
        '''    VkPipelineColorBlendAttachmentState blend = { .colorWriteMask = 15 };
    const char *write_mask = getenv("KK_PROBE_UINT_WRITE_MASK");
    if (write_mask) {
        char *end;
        unsigned long value = strtoul(write_mask, &end, 0);
        if (!*write_mask || *end || value > 15) return 1;
        blend.colorWriteMask = (VkColorComponentFlags)value;
    }''')
    clear_start = '        VkClearValue clear[2] = '
    clear_end = '        VkRenderPassBeginInfo render_begin = '
    if source.count(clear_start) != 1 or source.count(clear_end) != 1:
        raise ValueError('Integer clear anchors changed')
    start, end = source.index(clear_start), source.index(clear_end)
    source = source[:start] + '''        VkClearValue clear[2] = {
            {.color = {.uint32 = {31u, 63u, 127u, 255u}}},
            {.color = {.uint32 = {31u, 63u, 127u, 255u}}},
        };
''' + source[end:]
    start_anchor = '        for (unsigned y = 1; y < 7; ++y) for (unsigned x = 1; x < 7; ++x) {'
    end_anchor = '        printf("stage=%s case=%d gpl=%d last=%d samples=%d result=%s\\n",'
    if source.count(start_anchor) != 1 or source.count(end_anchor) != 1:
        raise ValueError('Integer readback anchors changed')
    start, end = source.index(start_anchor), source.index(end_anchor)
    return source[:start] + READBACK + source[end:]


def prepare_integer(out, headers):
    tests = Path(__file__).resolve().parent
    generated = out / 'integer-probe.c'
    generated.write_text(integer_harness((tests / 'kosmickrisp_interpolation.c').read_text()))
    binary = out / 'integer-probe'
    subprocess.run(['clang', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
        '-I' + str(headers), '-I' + str(tests), str(generated), '-o', str(binary)], check=True)
    for case in (1, 7):
        for stage in ('vert', 'frag'):
            path = tests / ('kosmickrisp_integer_output.' + stage)
            subprocess.run(['glslangValidator', '-V', '-S', stage, str(path),
                '-o', str(out / f'vs-{stage}-{case}.spv')], check=True,
                stdout=subprocess.DEVNULL)
    return binary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--icd', required=True, type=Path)
    parser.add_argument('--headers', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--compile-only', action='store_true')
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    icd, headers, out = args.icd.resolve(), args.headers.resolve(), args.out.resolve()
    if not icd.is_file() or not (headers / 'vulkan/vulkan.h').is_file():
        parser.error('ICD or Vulkan headers do not exist')
    if not shutil.which('clang') or not shutil.which('glslangValidator') or args.timeout <= 0:
        parser.error('clang, glslangValidator, and positive timeout are required')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        parser.error('Output directory must be empty')
    out.mkdir(parents=True, exist_ok=True)
    probe = prepare_integer(out, headers)
    report = {'schema': 1, 'icd_sha256': digest(icd), 'compiled_only': args.compile_only,
        'readback_pixels': 64, 'readback_channels': 4, 'format': 'R32G32B32A32_UINT',
        'scope': 'Exact uint32 attachment replay after an explicit loading-phase drain.',
        'blend_rule': 'Blend-enabled case requires advertised COLOR_ATTACHMENT_BLEND_BIT; otherwise skipped.',
        'results': []}
    if not args.compile_only:
        cases = [scenario('integer-default'), scenario('integer-dynamic-write-mask',
            options={'KK_PROBE_DYNAMIC_PSO': 'all', 'KK_PROBE_UINT_WRITE_MASK': '5'}),
            scenario('integer-blend-enable', case=7, options={'KK_PROBE_BLEND': 'add'})]
        for item in cases:
            for phase in ('cold', 'warm', 'warm2'):
                result = run_probe(probe, icd, out, item, out / item['name'], phase,
                    args.timeout, require_zero=phase != 'cold')
                report['results'].append(result)
                report['counts'] = {status: sum(row['status'] == status for row in report['results'])
                    for status in ('pass', 'fail', 'skip')}
                (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
                print(item['name'], phase, result['status'], '; '.join(result['reasons']), flush=True)
                if result['status'] != 'pass':
                    break
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return int(any(row['status'] == 'fail' for row in report['results']))


if __name__ == '__main__':
    raise SystemExit(main())
