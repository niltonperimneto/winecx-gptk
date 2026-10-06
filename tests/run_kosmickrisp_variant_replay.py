import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import zlib

from run_kosmickrisp_gpl_batch import clean_env, digest, parse_cache_events, parse_compiles, parse_metrics, prepare, scenario


BLOCKING_PHASES = frozenset({'fs_prepare', 'fs_wait', 'raster_prepare', 'raster_wait',
    'pso_create', 'pso_wait', 'archive_lookup', 'archive_load', 'native_create'})
BLOCKING_COMPILES = frozenset({'shaders', 'pso', 'pso_archive', 'compute', 'compute_archive',
    'fs_variant', 'fs_variant_wait', 'rast_variant', 'rast_variant_wait', 'rast_points', 'variant_wait', 'pso_wait'})


def fixtures():
    return [
        scenario('default'),
        scenario('dynamic-default', options={'KK_PROBE_DYNAMIC_PSO': 'all'}),
        scenario('dynamic-mask-msaa', case=6, samples=4,
            options={'KK_PROBE_DYNAMIC_PSO': 'all', 'KK_PROBE_SAMPLE_MASK': '5'}),
        scenario('dynamic-native-blend', case=7,
            options={'KK_PROBE_DYNAMIC_PSO': 'all', 'KK_PROBE_BLEND': 'add'}),
        scenario('mixed-static-dynamic', case=7, samples=4,
            options={'KK_PROBE_DYNAMIC_PSO': 'mixed', 'KK_PROBE_BLEND': 'add'}),
        scenario('advanced-blend', case=9, samples=4, options={'KK_PROBE_BLEND': 'advanced'}),
        scenario('dual-source', case=8, samples=4, options={'KK_PROBE_BLEND': 'dual'}),
        scenario('concurrent-link', options={'KK_PROBE_LINK_COUNT': '16', 'KK_PROBE_THREADS': '4'}),
        scenario('concurrent-geometry', stage='gs', options={'KK_PROBE_LINK_COUNT': '16', 'KK_PROBE_THREADS': '4'}),
        scenario('geometry', stage='gs'),
        scenario('tessellation', stage='tes'),
    ]


def parse_stats(path):
    records = parse_cache_events(path)
    if not records:
        raise ValueError('Missing variant aggregate counters')
    stats = {}
    for record in records:
        phase = record.get('phase')
        if record['event'] != 'variant_summary' or not isinstance(phase, str) or phase in stats:
            raise ValueError('Invalid or duplicate variant summary')
        for key in ('count', 'duration_ns', 'draw_count', 'draw_duration_ns'):
            if type(record.get(key)) is not int or record[key] < 0:
                raise ValueError('Invalid variant counter')
        if record['draw_count'] > record['count'] or record['draw_duration_ns'] > record['duration_ns']:
            raise ValueError('Draw counter exceeds total')
        stats[phase] = record
    if not BLOCKING_PHASES.issubset(stats) or 'ready_hit' not in stats or 'first_demand' not in stats:
        raise ValueError('Incomplete variant counters')
    return stats


def readiness_errors(metrics, stats, compiles, required):
    errors = []
    readiness = [metric for metric in metrics if metric['kind'] == 'variant_readiness']
    if required and (not readiness or not all(metric.get('ready') is True for metric in readiness)):
        errors.append('Missing successful loading-phase readiness drain')
    if not stats or compiles is None:
        errors.append('Missing variant or compiler evidence')
        return errors
    if required:
        work = {phase: stats[phase]['draw_count'] for phase in BLOCKING_PHASES if stats[phase]['draw_count']}
        if work:
            errors.append('Draw variant work after readiness: ' + json.dumps(work, sort_keys=True))
        draw_compiles = [event['kind'] for event in compiles if event['origin'] == 'draw']
        if draw_compiles:
            errors.append('Draw compiler events after readiness: ' + ', '.join(draw_compiles))
        if not stats['ready_hit']['draw_count'] or not stats['first_demand']['draw_count']:
            errors.append('No resident variant draw was exercised')
    return errors


def run_probe(probe, icd, work, item, directory, phase, timeout, wait=True, require_zero=False):
    directory.mkdir(parents=True, exist_ok=True)
    paths = {name: directory / (phase + suffix) for name, suffix in {
        'compiler': '-compiler.csv', 'cache': '-cache.jsonl',
        'stats': '-stats.jsonl', 'timeline': '-variants.jsonl'}.items()}
    env = clean_env()
    for key in list(env):
        if key.startswith('MESA_KK_VARIANT_') or key == 'MESA_KK_TEST_PREWARM':
            del env[key]
    env.update({'KK_PROBE_METRICS': '1', 'KK_PROBE_REPEAT_DRAWS': '2',
        'MESA_SHADER_CACHE_DIR': str(directory / 'disk-cache'),
        'KK_PROBE_CACHE': str(directory / 'pipeline.cache'),
        'MESA_KK_COMPILE_LOG': str(paths['compiler']), 'MESA_KK_CACHE_LOG': str(paths['cache']),
        'MESA_KK_VARIANT_STATS': str(paths['stats']), 'MESA_KK_VARIANT_LOG': str(paths['timeline']),
        'MESA_KK_TEST_PREWARM': '1'})
    if wait:
        env['KK_PROBE_PREWARM_WAIT'] = '1'
    env.update(item['options'])
    if 'KK_PROBE_PREWARM_DELAY_MS' in env:
        raise ValueError('Artificial prewarm delay is forbidden in replay validation')
    command = [str(probe), str(icd), str(work), item['stage'], str(item['case']),
        str(item['mode']), '0', str(item['samples'])]
    start = time.monotonic_ns()
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout)
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
        status = 'pass' if code == 0 else 'skip' if code == 77 else 'fail'
        reasons = [] if status != 'fail' else ['Probe exit ' + str(code)]
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode(errors='replace') if isinstance(error.stdout, bytes) else error.stdout or ''
        stderr = error.stderr.decode(errors='replace') if isinstance(error.stderr, bytes) else error.stderr or ''
        code, status, reasons = None, 'fail', ['Timeout']
    elapsed = time.monotonic_ns() - start
    (directory / (phase + '-stdout.log')).write_text(stdout)
    (directory / (phase + '-stderr.log')).write_text(stderr)
    metrics, compiles, stats, timeline = [], None, {}, []
    if status == 'pass':
        try:
            metrics = parse_metrics(stdout)
            compiles = parse_compiles(paths['compiler'])
            stats = parse_stats(paths['stats'])
            timeline = parse_cache_events(paths['timeline']) or []
            reasons.extend(readiness_errors(metrics, stats, compiles, require_zero))
            if wait and not any(metric['kind'] == 'variant_readiness' for metric in metrics):
                reasons.append('Readiness test APIs were not exercised')
        except (ValueError, TypeError, KeyError, OSError) as error:
            reasons.append(str(error))
        if reasons:
            status = 'fail'
    return {'name': item['name'], 'phase': phase, 'status': status, 'returncode': code,
        'reasons': reasons, 'elapsed_ms': elapsed / 1e6, 'readiness_required': wait,
        'zero_draw_work_required': require_zero, 'metrics': metrics, 'compiler_events': compiles,
        'variant_stats': stats, 'variant_events': timeline, 'artifacts': str(directory)}


def history_cache_files(directory):
    found = []
    for path in directory.rglob('*'):
        if not path.is_file() or path.name == 'index' or path.stat().st_size > 1024 * 1024:
            continue
        data = path.read_bytes()
        identified = b'KKVHIST1' in data[:1024]
        for offset in range(min(len(data), 1024)):
            if identified:
                break
            if data[offset:offset + 2] in (b'\x78\xda', b'\x78\x9c', b'\x78\x01'):
                try:
                    payload = zlib.decompressobj().decompress(data[offset:], 1024 * 1024)
                    identified = payload.startswith(b'KKVHIST1')
                except zlib.error:
                    pass
            elif data[offset:offset + 4] == b'\x28\xb5\x2f\xfd' and shutil.which('zstd'):
                result = subprocess.run(['zstd', '-d', '-q', '-c'], input=data[offset:],
                    capture_output=True, timeout=10)
                identified = result.returncode == 0 and result.stdout.startswith(b'KKVHIST1')
        if identified:
            found.append(path)
    return found


def corrupt_history(directory):
    paths = history_cache_files(directory)
    if not paths:
        raise ValueError('No isolated history cache record was identified for corruption')
    records = []
    for path in paths:
        records.append({'path': str(path), 'original_sha256': digest(path), 'original_bytes': path.stat().st_size})
        path.write_bytes(b'KKVHIST1')
    return records


def demands(result):
    return {event['request_id'] for event in result['variant_events']
            if event.get('phase') == 'first_demand' and event.get('origin') == 'draw'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--icd', required=True, type=Path)
    parser.add_argument('--headers', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--fixture', action='append')
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--skip-negative', action='store_true')
    args = parser.parse_args()
    icd, headers, out = args.icd.resolve(), args.headers.resolve(), args.out.resolve()
    if not icd.is_file() or not (headers / 'vulkan/vulkan.h').is_file():
        parser.error('ICD or Vulkan headers do not exist')
    if args.timeout <= 0 or not shutil.which('clang') or not shutil.which('glslangValidator'):
        parser.error('Positive timeout, clang and glslangValidator are required')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        parser.error('Output directory must be empty to preserve evidence')
    selected = [item for item in fixtures() if not args.fixture or item['name'] in args.fixture]
    if not selected or args.fixture and set(args.fixture) != {item['name'] for item in selected}:
        parser.error('Unknown fixture selection')
    out.mkdir(parents=True, exist_ok=True)
    probe = prepare(out, headers)
    report = {'schema': 1, 'icd': str(icd), 'icd_sha256': digest(icd), 'results': [],
        'coverage_gaps': ['Point raster', 'Multiview', 'Integer outputs', 'Attachment remapping',
                         'Vulkan validation layers', 'Real-game automatic scheduling'],
        'scope': 'Fixed observed replay after an explicit loading-phase drain; immediate draws are reported separately.'}
    def record(row):
        report['results'].append(row)
        report['counts'] = {status: sum(result['status'] == status for result in report['results'])
                            for status in ('pass', 'fail', 'skip')}
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        print(row['name'], row['phase'], row['status'], '; '.join(row['reasons']), flush=True)
    for item in selected:
        directory = out / item['name']
        for phase in ('cold', 'warm', 'warm2'):
            row = run_probe(probe, icd, out, item, directory, phase, args.timeout,
                            require_zero=phase != 'cold')
            record(row)
            if row['status'] != 'pass':
                break
    if not args.skip_negative:
        seed = scenario('unseen-state', case=6, samples=4,
            options={'KK_PROBE_DYNAMIC_PSO': 'all', 'KK_PROBE_SAMPLE_MASK': '15'})
        directory = out / seed['name']
        before = run_probe(probe, icd, out, seed, directory, 'seed', args.timeout)
        record(before)
        if before['status'] == 'pass':
            seed['options']['KK_PROBE_SAMPLE_MASK'] = '5'
            unseen = run_probe(probe, icd, out, seed, directory, 'unseen', args.timeout)
            if unseen['status'] == 'pass' and not demands(unseen) - demands(before):
                unseen['status'] = 'fail'
                unseen['reasons'].append('Changed dynamic state did not exercise a new exact recipe')
            record(unseen)
            if unseen['status'] == 'pass':
                record(run_probe(probe, icd, out, seed, directory, 'observed-warm', args.timeout, require_zero=True))
        budget = scenario('exhausted-budget', case=6, samples=4,
            options={'KK_PROBE_DYNAMIC_PSO': 'all', 'KK_PROBE_SAMPLE_MASK': '5'})
        directory = out / budget['name']
        seeded = run_probe(probe, icd, out, budget, directory, 'seed', args.timeout)
        record(seeded)
        if seeded['status'] == 'pass':
            budget['options'].update({'MESA_KK_VARIANT_RECIPE_LIMIT': '1', 'KK_PROBE_PREWARM_EXPECT_UNREADY': '1'})
            limited = run_probe(probe, icd, out, budget, directory, 'limited', args.timeout)
            if limited['status'] == 'pass' and not any(metric['kind'] == 'variant_readiness'
                and metric.get('ready') is False and metric.get('result', 0) != 0 for metric in limited['metrics']):
                limited['status'] = 'fail'
                limited['reasons'].append('Exhausted budget was not reported as unmet')
            record(limited)
        corrupt = scenario('corrupt-history', case=6, samples=4,
            options={'KK_PROBE_DYNAMIC_PSO': 'all', 'KK_PROBE_SAMPLE_MASK': '5'})
        directory = out / corrupt['name']
        seeded = run_probe(probe, icd, out, corrupt, directory, 'seed', args.timeout)
        record(seeded)
        if seeded['status'] == 'pass':
            try:
                damaged = corrupt_history(directory / 'disk-cache')
                (directory / 'corruption.json').write_text(json.dumps(damaged, indent=2) + '\n')
                recovered = run_probe(probe, icd, out, corrupt, directory, 'damaged', args.timeout)
                record(recovered)
                if recovered['status'] == 'pass':
                    record(run_probe(probe, icd, out, corrupt, directory, 'recovered-warm', args.timeout, require_zero=True))
            except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                record({'name': corrupt['name'], 'phase': 'corruption', 'status': 'fail', 'reasons': [str(error)]})
        disabled = scenario('cache-disabled', case=6, samples=4, options={
            'KK_PROBE_DYNAMIC_PSO': 'all', 'KK_PROBE_SAMPLE_MASK': '5',
            'MESA_SHADER_CACHE_DISABLE': 'true', 'KK_PROBE_PREWARM_EXPECT_UNREADY': '1'})
        for phase in ('cold', 'repeat'):
            record(run_probe(probe, icd, out, disabled, out / disabled['name'], phase, args.timeout))
        immediate = scenario('immediate-draw', case=6, samples=4,
            options={'KK_PROBE_DYNAMIC_PSO': 'all', 'KK_PROBE_SAMPLE_MASK': '5'})
        for phase in ('cold', 'warm', 'warm2'):
            record(run_probe(probe, icd, out, immediate, out / immediate['name'], phase,
                             args.timeout, wait=False))
    return int(report['counts']['fail'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())
