#!/usr/bin/env python3
"""Require matching physical-host campaigns before promoting a layout-v2 runtime."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

TITLES = {'hades-vulkan', 'hades-dxvk', 'portal2-d3d9', 'skywalker', 'steam-cef'}


def digest_file(root, record):
    relative = Path(record['path'])
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError('evidence path escapes campaign')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != record['sha256']:
        raise ValueError(f'evidence hash mismatch: {relative}')
    return data


def metrics(root, run):
    for flag in ('focused', 'awake', 'capture_valid', 'rendering_correct'):
        if run.get(flag) is not True:
            raise ValueError(f'invalid measurement: {flag}')
    digest_file(root, run['visual_evidence'])
    times = json.loads(digest_file(root, run['frame_times']))
    if (not isinstance(times, list) or len(times) < 100 or
            any(type(t) not in (int, float) or not math.isfinite(t) or t <= 0 for t in times)):
        raise ValueError('missing or invalid frame times')
    if sum(times) < 30000:
        raise ValueError('measured scene must cover at least 30 seconds')
    return 1000 / statistics.mean(times), sorted(times)[math.ceil(len(times) * .99) - 1]


def campaign_blockers(campaign, root, validation):
    failures = []
    try:
        if campaign.get('schema') != 1 or campaign.get('manifest_sha256') != validation.get('manifest_sha256'):
            raise ValueError('campaign does not identify the validated runtime manifest')
        if campaign.get('os') != validation.get('os') or not campaign.get('hardware'):
            raise ValueError('campaign and device validation must use the same OS and identify hardware')
        cases = campaign['cases']
        if {case['id'] for case in cases} != TITLES or len(cases) != len(TITLES):
            raise ValueError('all five required game/client cases must be present exactly once')
        baselines = set()
        for case in cases:
            label = case['id']
            if case.get('resolution') != [1280, 720] or case.get('vsync') is not False:
                raise ValueError(f'{label}: require 1280x720 with VSync disabled')
            for fixture in ('settings', 'scene', 'harness', 'game_build'):
                digest_file(root, case[fixture])
            if case.get('gameplay_confirmed') is not True:
                raise ValueError(f'{label}: missing gameplay/CEF rendering confirmation')
            # A screenshot and a log are separate evidence: neither substitutes for the other.
            digest_file(root, case['visual_evidence'])
            log = digest_file(root, case['candidate_backend_log']).decode(errors='replace')
            if 'KosmicKrisp' not in log or ('DXVK' not in log and label != 'hades-vulkan'):
                raise ValueError(f'{label}: missing actual candidate driver/backend identity')
            if label == 'steam-cef':
                if case.get('gpu_compositing') is not True or case.get('game_backend_preserved') is not True:
                    raise ValueError('Steam CEF must retain GPU compositing and the selected game backend')
                continue
            lanes = []
            for name in ('baseline', 'candidate'):
                lane = case[name]
                digest = lane.get('runtime_sha256', '')
                if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                    raise ValueError(f'{label}: missing immutable {name} runtime digest')
                if name == 'baseline':
                    baselines.add(digest)
                    if digest == validation.get('archive_sha256'):
                        raise ValueError(f'{label}: baseline must be the previous validated runtime')
                if len(lane.get('warmups', [])) != 2 or len(lane.get('measured', [])) != 3:
                    raise ValueError(f'{label}: require two warmups and three measured repetitions')
                for warmup in lane['warmups']:
                    if warmup.get('completed') is not True:
                        raise ValueError(f'{label}: incomplete warmup')
                    digest_file(root, warmup['log'])
                if name == 'candidate' and lane['runtime_sha256'] != validation.get('archive_sha256'):
                    raise ValueError(f'{label}: candidate archive differs from the validated build')
                samples = [metrics(root, run) for run in lane['measured']]
                lanes.append(tuple(statistics.median(sample[i] for sample in samples) for i in (0, 1)))
            old, new = lanes
            if new[0] < old[0] * .95 or new[1] > old[1] * 1.10:
                failures.append(f'{label}: performance regression exceeds 5% mean FPS or 10% p99 frame time')
        if len(baselines) != 1:
            raise ValueError('all cases must use the same frozen baseline runtime')
    except (KeyError, TypeError, ValueError, OSError) as error:
        failures.append(str(error))
    return failures


def blockers(directory):
    failures = []
    manifests = set()
    for platform in ('macos26', 'newer'):
        root = directory / f'kosmickrisp-validation-results-{platform}'
        try:
            validation = json.loads((root / 'results.json').read_text())
            campaign = json.loads((root / 'campaign.json').read_text())
            failures.extend(f'{platform}: {reason}' for reason in campaign_blockers(campaign, root, validation))
            manifests.add(validation['manifest_sha256'])
        except (KeyError, ValueError, OSError) as error:
            failures.append(f'{platform}: missing or invalid campaign evidence: {error}')
    if len(manifests) != 1:
        failures.append('both physical OS lanes must validate the same runtime manifest')
    return failures


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--attach', action='store_true', help='validate one physical campaign and attach game evidence')
    args = parser.parse_args()
    if args.attach:
        try:
            report_path = args.directory / 'results.json'
            report = json.loads(report_path.read_text())
            campaign = json.loads((args.directory / 'campaign.json').read_text())
            failures = campaign_blockers(campaign, args.directory, report)
            if not failures:
                report['migration']['game'] = {'status': 'passed',
                    'reason': 'five pinned game/client cases and baseline performance campaign passed'}
                report_path.write_text(json.dumps(report, indent=2) + '\n')
        except (KeyError, ValueError, OSError) as error:
            failures = [str(error)]
    else:
        failures = blockers(args.directory)
    for failure in failures:
        print(f'::error::{failure}')
    raise SystemExit(bool(failures))
