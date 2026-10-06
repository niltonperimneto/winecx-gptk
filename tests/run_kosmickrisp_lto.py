import argparse
import json
import os
import subprocess
from pathlib import Path

from run_kosmickrisp_gpl_batch import parse_compiles, parse_metrics, prepare


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--icd', required=True, type=Path)
    parser.add_argument('--headers', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--architecture', choices=('arm64', 'x86_64'), default='arm64')
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error('--out must be empty')
    out.mkdir(parents=True, exist_ok=True)
    probe = prepare(out, args.headers.resolve())
    if args.architecture == 'x86_64':
        command = ['clang', '-arch', 'x86_64', '-O2', '-Wall', '-Wextra', '-Werror',
                   '-pthread', '-I' + str(args.headers.resolve()),
                   str(Path(__file__).with_name('kosmickrisp_interpolation.c')),
                   '-o', str(probe)]
        subprocess.run(command, check=True)
    cases = [
        ('static', 'vs', 1, 1, {}, 'monolithic'),
        ('grouped', 'vs', 1, 1, {'KK_PROBE_GROUPS': '3,12'}, 'monolithic'),
        ('nested', 'vs', 1, 1, {'KK_PROBE_NESTED': '1'}, 'monolithic'),
        ('dynamic', 'vs', 6, 4,
         {'KK_PROBE_DYNAMIC_PSO': 'all', 'KK_PROBE_SAMPLE_MASK': '5'}, 'partition'),
        ('geometry', 'gs', 1, 1, {}, 'partition'),
        ('tessellation', 'tes', 1, 1, {}, 'monolithic'),
    ]
    results = []
    for name, stage, case, samples, options, path in cases:
        for lto in (False, True):
            directory = out / (name + ('-lto' if lto else '-fast'))
            directory.mkdir()
            for temperature in ('cold', 'warm'):
                log = directory / (temperature + '.csv')
                env = {k: v for k, v in os.environ.items()
                       if not k.startswith(('MESA_KK_', 'MESA_SHADER_', 'KK_PROBE_'))}
                env.update(options, MESA_SHADER_CACHE_DIR=str(directory / 'cache'),
                           MESA_KK_COMPILE_LOG=str(log), KK_PROBE_METRICS='1',
                           KK_PROBE_DESTROY_LIBRARIES='1')
                if lto:
                    env['KK_PROBE_LTO'] = '1'
                command = ['arch', '-' + args.architecture, str(probe),
                           str(args.icd.resolve()), str(out), stage,
                           str(case), '1', '0', str(samples)]
                run = subprocess.run(command, env=env, capture_output=True,
                                     text=True, timeout=60)
                (directory / (temperature + '.stdout')).write_text(run.stdout)
                (directory / (temperature + '.stderr')).write_text(run.stderr)
                events = parse_compiles(log) or []
                creates = [e for e in events if e['kind'] in ('pso', 'pso_archive')
                           and e['origin'] == 'create']
                draws = [e for e in events if e['kind'] in ('pso', 'pso_archive')
                         and e['origin'] == 'draw']
                partitions = [e for e in events
                              if e['kind'] in ('pso', 'pso_archive')
                              and e['origin'] in ('draw', 'prewarm')]
                errors = []
                if run.returncode:
                    errors.append('Probe failed: ' + str(run.returncode))
                if temperature == 'cold':
                    if lto and path == 'monolithic':
                        if not creates or draws:
                            errors.append('Expected creation-time monolithic PSO')
                    elif creates or not partitions:
                        errors.append('Expected partitioned PSO on worker or draw')
                elif not any(e['kind'] in ('deserialize', 'pso_archive') for e in events):
                    errors.append('Expected warm cache reuse')
                row = dict(case=name, lto=lto, run=temperature,
                           architecture=args.architecture, returncode=run.returncode,
                           expected_path=path if lto else 'partition', errors=errors,
                           events=events, metrics=parse_metrics(run.stdout))
                results.append(row)
                (out / 'report.json').write_text(json.dumps(results, indent=2) + '\n')
                print(name, 'lto' if lto else 'fast', temperature,
                      'PASS' if not errors else 'FAIL', flush=True)
    return int(any(row['errors'] for row in results))


if __name__ == '__main__':
    raise SystemExit(main())
