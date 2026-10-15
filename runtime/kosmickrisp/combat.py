#!/usr/bin/env python3
"""Bounded, isolated Hades DX11 combat fixture and presentation evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from hades import claim_prefix, isolate_saves, environment, stop_prefix


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    work, wine, game = args.work.resolve(), args.wine.resolve(), args.game.resolve()
    # This command only accepts an explicitly marked, disposable game copy.
    if not (game / '.kk-combat-copy').is_file():
        raise ValueError('game must be a staged copy with .kk-combat-copy marker')
    if not game.is_relative_to(work):
        raise ValueError('game must be inside the benchmark workspace')
    prefix = work / 'combat-prefix'
    lock = claim_prefix(prefix)
    output = (work / args.output).resolve()
    if not output.is_relative_to(work) or output == work or output.is_relative_to(game):
        raise ValueError('output must be a new evidence directory inside the workspace')
    output.mkdir(parents=True, exist_ok=False)
    env = environment(prefix, 'kosmickrisp')
    env['WINEDLLOVERRIDES'] = 'd3d11,dxgi=n;mscoree,mshtml,winemenubuilder,nvapi,nvapi64='
    launcher = wine / 'bin/wine-kosmickrisp'
    if not (prefix / '.combat-ready').exists():
        with (output / 'setup.log').open('w') as log:
            subprocess.run([str(launcher), 'wineboot.exe', '-u'], env=env,
                           stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
        subprocess.run([str(wine / 'bin/wineserver'), '-w'], env=env, timeout=30, check=True)
        isolate_saves(prefix)
        (prefix / '.combat-ready').touch()
    isolate_saves(prefix)
    profiles = [p / 'Documents/Saved Games/Hades' for p in (prefix / 'drive_c/users').iterdir()
                if p.is_dir() and p.name != 'Public']
    config = 'Width = 1280\nHeight = 720\nWindowed = true\nMusicVolume = 0\nSFXVolume = 0\nVoiceVolume = 0\n'
    for profile in profiles:
        # A fresh initial state is the fixture; never import the user's saves.
        for p in profile.iterdir():
            if p.is_file(): p.unlink()
        (profile / 'Profile1.sjson').write_text(config)
        (profile / 'activeProfile').write_text('1')
    scripts = game / 'Content/Scripts'
    fixture = Path(__file__).with_name('hades-combat.lua')
    shutil.copy2(fixture, scripts / fixture.name)
    room = scripts / 'RoomManager.lua'
    original = room.with_suffix('.lua.kk-original')
    if not original.exists(): shutil.copy2(room, original)
    room.write_bytes(original.read_bytes() + b'\nImport "hades-combat.lua"\n')
    dxvk = wine.parent / 'DXVK3/x64'
    for name in ('d3d11.dll', 'dxgi.dll'):
        shutil.copy2(dxvk / name, game / 'x64' / name)
    cache = work / 'combat-caches' / args.configuration
    if args.fresh and cache.exists(): shutil.rmtree(cache)
    (cache / 'mesa').mkdir(parents=True, exist_ok=True)
    (cache / 'dxvk').mkdir(exist_ok=True)
    env.update(MESA_SHADER_CACHE_DIR=str(cache / 'mesa'),
               DXVK_SHADER_CACHE_PATH='Z:' + str(cache / 'dxvk'),
               DXVK_LOG_PATH='Z:' + str(output), MESA_SHADER_CACHE_SHOW_STATS='true')
    if args.configuration == 'baseline':
        env.update(MESA_SHADER_CACHE_DISABLE='true', DXVK_SHADER_CACHE='0')
    else:
        env.pop('MESA_SHADER_CACHE_DISABLE', None)
        env['DXVK_SHADER_CACHE'] = '1'
    configuration = output / 'dxvk.conf'
    configuration.write_text('dxvk.enableGraphicsPipelineLibrary = ' +
        ('Auto' if args.configuration == 'gpl' else 'False') + '\ndxgi.syncInterval = 1\n')
    env['DXVK_CONFIG_FILE'] = 'Z:' + str(configuration)
    env['MESA_KK_PRESENT_LOG'] = str(output / 'present.csv')
    if args.capture:
        env.update(MESA_KK_GPU_CAPTURE_TRIGGER=str(output / 'capture.trigger'),
                   MESA_KK_GPU_CAPTURE_DIRECTORY=str(output), MESA_KK_GPU_CAPTURE_FRAMES='3',
                   MTL_CAPTURE_ENABLED='1')
    report = {'schema': 1, 'configuration': args.configuration, 'fresh': args.fresh,
              'capture': args.capture, 'fixture_sha256': digest(fixture),
              'game_sha256': digest(game / 'x64/Hades.exe'), 'events': [],
              'status': 'starting', 'gameplay_verified': False}
    shared_profile = Path.home() / 'Documents/Saved Games/Hades/Profile1.sjson'
    before = digest(shared_profile) if shared_profile.exists() else None
    (output / 'background-load.txt').write_text(subprocess.check_output(
        ['ps', '-axo', 'pid,%cpu,comm'], text=True))
    start = time.monotonic()
    seen = set()
    process = None
    try:
        with (output / 'wine.log').open('w') as log:
            process = subprocess.Popen([str(launcher), str(game / 'x64/Hades.exe'),
                '/DebugRNGSeed=44786', '/Logging=true', '/DebugLog=true',
                '/Width=1280', '/Height=720', '/Windowed=true'], cwd=game / 'x64',
                env=env, stdout=log, stderr=subprocess.STDOUT)
            next_key = start + 20
            while process.poll() is None and time.monotonic() - start < args.timeout:
                markers = list(prefix.glob('drive_c/users/*/Documents/Saved Games/Hades/**/kk-combat.csv'))
                for marker in markers:
                    for line in marker.read_text(errors='replace').splitlines():
                        if line in seen: continue
                        seen.add(line)
                        report['events'].append({'line': line, 'observed_ns': time.monotonic_ns()})
                        print(line, flush=True)
                        if args.capture and line.startswith('tick-20,'):
                            (output / 'capture.trigger').touch()
                if any(e['line'].startswith('measurement-end,') for e in report['events']):
                    report['status'] = 'completed'
                    break
                if not seen and time.monotonic() >= next_key:
                    subprocess.run([str(launcher), str(args.window_helper.resolve()), '13'],
                        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                    next_key = time.monotonic() + 3
                time.sleep(0.2)
            if report['status'] != 'completed': report['status'] = 'incomplete'
            subprocess.run([str(launcher), str(args.window_helper.resolve()), 'close'],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: stop_prefix(wine, env, output)
    finally:
        if process and process.poll() is None: stop_prefix(wine, env, output)
        isolate_saves(prefix)
        report['shared_profile_unchanged'] = before == (digest(shared_profile) if shared_profile.exists() else None)
        report['seconds'] = time.monotonic() - start
        for profile in profiles:
            for p in profile.glob('*.log'): shutil.copy2(p, output / p.name)
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        lock.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('work', 'wine', 'game', 'window-helper'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--configuration', choices=('baseline', 'cache', 'gpl'), default='gpl')
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--capture', action='store_true')
    parser.add_argument('--timeout', type=int, default=150)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'completed' and result['shared_profile_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
