#!/usr/bin/env python3
"""Move one component pin to a new upstream commit.

Driven by bump-pins.yml when winecx, mesa or relay12 report a new main
commit. Rewrites only the keys that component owns and verifies what it
pins: relay12's archive must match the reported digest, and the Wine
pin carries the FAudio version vendored at that commit.
"""
import argparse
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD_PINS = ROOT / 'tools/build/pins.env'
KOSMICKRISP_PINS = ROOT / 'runtime/kosmickrisp/pins.env'
SHA = re.compile(r'^[0-9a-f]{40}$')
DIGEST = re.compile(r'^[0-9a-f]{64}$')


def set_pins(text, values):
    """Replace KEY=value lines (optionally `export`ed), keeping everything else."""
    seen = set()
    lines = []
    for line in text.splitlines(keepends=True):
        match = re.match(r'^(export )?([A-Z][A-Z0-9_]*)=', line)
        if match and match.group(2) in values:
            name = match.group(2)
            lines.append(f'{match.group(1) or ""}{name}={values[name]}\n')
            seen.add(name)
        else:
            lines.append(line)
    missing = set(values) - seen
    if missing:
        raise KeyError(f'pins not found: {", ".join(sorted(missing))}')
    return ''.join(lines)


def faudio_version(header):
    """FAUDIO_VERSION as prepare_source.sh spells it, e.g. 26.09."""
    parts = {}
    for name in ('MAJOR', 'MINOR'):
        match = re.search(rf'#define FAUDIO_{name}_VERSION\s+(\d+)', header)
        if not match:
            raise ValueError(f'FAudio.h has no FAUDIO_{name}_VERSION')
        parts[name] = int(match.group(1))
    return f'{parts["MAJOR"]}.{parts["MINOR"]:02d}'


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def plan(component, sha, release_tag=None, sha256=None, fetcher=fetch):
    """(pin file, {key: value}) for one component update."""
    if not SHA.match(sha):
        raise ValueError(f'not a full commit sha: {sha}')
    if component == 'winecx':
        header = fetcher(f'https://raw.githubusercontent.com/niltonperimneto/winecx/{sha}'
                         '/libs/faudio/include/FAudio.h').decode()
        return BUILD_PINS, {'WINECX_COMMIT': sha, 'FAUDIO_VERSION': faudio_version(header)}
    if component == 'mesa':
        return KOSMICKRISP_PINS, {'KOSMICKRISP_MESA_COMMIT': sha}
    if component == 'relay12':
        if not release_tag or not sha256 or not DIGEST.match(sha256):
            raise ValueError('relay12 needs its release tag and archive sha256')
        archive = fetcher(f'https://github.com/niltonperimneto/relay12/releases/download/'
                          f'{release_tag}/relay12-{release_tag}.tar.gz')
        actual = hashlib.sha256(archive).hexdigest()
        if actual != sha256:
            raise ValueError(f'relay12 archive is {actual}, dispatch reported {sha256}')
        return BUILD_PINS, {'RELAY12_COMMIT': sha, 'RELAY12_RELEASE_TAG': release_tag,
                            'RELAY12_ARTIFACT_SHA256': sha256}
    raise ValueError(f'unknown component: {component}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', choices=('winecx', 'mesa', 'relay12'))
    parser.add_argument('sha')
    parser.add_argument('--release-tag')
    parser.add_argument('--sha256')
    args = parser.parse_args()
    path, values = plan(args.component, args.sha, args.release_tag, args.sha256)
    before = path.read_text()
    after = set_pins(before, values)
    path.write_text(after)
    for name, value in values.items():
        print(f'{path.relative_to(ROOT)}: {name}={value}')
    return 0 if after != before else 3


if __name__ == '__main__':
    sys.exit(main())
