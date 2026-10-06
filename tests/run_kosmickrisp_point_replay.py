import argparse
import json
from pathlib import Path
import shutil
import subprocess

from run_kosmickrisp_gpl_batch import digest, scenario
from run_kosmickrisp_variant_replay import run_probe


READBACK = '''        for (unsigned y = 0; y < 8; ++y) for (unsigned x = 0; x < 8; ++x) {
            float value = (y * 8 + x) / 64.0f;
            float coverage = test == 6 ?
                (float)__builtin_popcount(sample_mask & ((1u << sample_count) - 1)) / sample_count : 1;
            float expected[4] = {value * coverage, value * .5f * coverage,
                (1 - value) * coverage, coverage};
            for (unsigned channel = 0; channel < 4; ++channel) {
                float actual = pixels[(y * 8 + x) * 4 + channel];
                if (!isfinite(actual) || fabsf(actual - expected[channel]) > .0001f) {
                    fprintf(stderr, "point pixel %u,%u channel %u: %f expected %f\\n",
                        x, y, channel, actual, expected[channel]);
                    failed = 1;
                }
            }
        }
'''


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('Point harness anchor changed: ' + before)
    return source.replace(before, after)


def point_harness(source):
    source = replace_once(source,
        '.topology = tes ? VK_PRIMITIVE_TOPOLOGY_PATCH_LIST : VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST',
        '.topology = VK_PRIMITIVE_TOPOLOGY_POINT_LIST')
    source = replace_once(source, 'vkCmdDraw(command, 3, 1, 0, 0);',
        'vkCmdDraw(command, 64, 1, 0, 0);')
    start_anchor = '        for (unsigned y = 1; y < 7; ++y) for (unsigned x = 1; x < 7; ++x) {'
    end_anchor = '        printf("stage=%s case=%d gpl=%d last=%d samples=%d result=%s\\n",'
    if source.count(start_anchor) != 1 or source.count(end_anchor) != 1:
        raise ValueError('Point readback anchors changed')
    start, end = source.index(start_anchor), source.index(end_anchor)
    return source[:start] + READBACK + source[end:]


def prepare_point(out, headers):
    tests = Path(__file__).resolve().parent
    generated = out / 'point-probe.c'
    generated.write_text(point_harness((tests / 'kosmickrisp_interpolation.c').read_text()))
    binary = out / 'point-probe'
    subprocess.run(['clang', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
        '-I' + str(headers), '-I' + str(tests), str(generated), '-o', str(binary)], check=True)
    for case in (1, 6):
        for stage, suffix in (('vert', 'vert'), ('frag', 'frag')):
            path = tests / ('kosmickrisp_point_raster.' + suffix)
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
    probe = prepare_point(out, headers)
    report = {'schema': 1, 'icd_sha256': digest(icd), 'compiled_only': args.compile_only,
        'readback_pixels': 64, 'readback_channels': 4, 'vertices': 64, 'point_size': 1,
        'scope': 'Fixed one-pixel point replay after an explicit loading-phase drain.',
        'results': []}
    if not args.compile_only:
        cases = [scenario('point-default'), scenario('point-dynamic-mask', case=6, samples=4,
            options={'KK_PROBE_DYNAMIC_PSO': 'all', 'KK_PROBE_SAMPLE_MASK': '5'})]
        for item in cases:
            for phase in ('cold', 'warm', 'warm2'):
                result = run_probe(probe, icd, out, item, out / item['name'], phase,
                    args.timeout, require_zero=phase != 'cold')
                if result['status'] == 'pass' and not result['variant_stats'].get('raster_prepare', {}).get('count'):
                    result['status'] = 'fail'
                    result['reasons'].append('No actual point raster variant preparation was exercised')
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
