#!/usr/bin/env python3
"""Fail when a runtime tree lacks a path Whisky relies on (contracts/runtime-layout.json)."""
import argparse
import json
import sys
import subprocess
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[1] / 'contracts/runtime-layout.json'


def missing(libraries, contract, kosmickrisp):
    if contract.get('schema') not in (1, 2):
        raise ValueError('unsupported runtime layout contract')
    paths = list(contract['required']) + (list(contract['kosmickrisp']) if kosmickrisp else [])
    return [path for path in paths if not (Path(libraries) / path).exists()]


def forbidden(libraries, contract, inspect_macho=True):
    """Reject stale payloads, symlink targets and native dependencies after cache restore."""
    if contract.get('schema') != 2:
        return []
    root = Path(libraries)
    violations = []
    magic = {bytes.fromhex(value) for value in
             ('feedface', 'cefaedfe', 'feedfacf', 'cffaedfe', 'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca')}
    for entry in root.rglob('*'):
        relative = entry.relative_to(root).as_posix()
        if (relative.split('/')[0].lower() in {x.lower() for x in contract.get('forbidden', [])} or
                'moltenvk' in entry.name.lower() or
                (entry.is_symlink() and 'moltenvk' in str(entry.readlink()).lower())):
            violations.append(relative)
        if inspect_macho and entry.is_file() and not entry.is_symlink():
            with entry.open('rb') as stream:
                is_macho = stream.read(4) in magic
            if is_macho:
                deps = subprocess.check_output(['otool', '-L', str(entry)], text=True)
                if 'moltenvk' in deps.lower():
                    violations.append(relative + ': MoltenVK load command')
    return violations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('libraries', type=Path)
    parser.add_argument('--kosmickrisp', action='store_true')
    args = parser.parse_args()
    absent = missing(args.libraries, json.loads(CONTRACT.read_text()), args.kosmickrisp)
    for path in absent:
        print(f'::error::runtime layout contract: missing Libraries/{path}')
    violations = forbidden(args.libraries, json.loads(CONTRACT.read_text()))
    for entry in violations:
        print(f'::error::runtime layout contract: forbidden {entry}')
    if absent or violations:
        return 1
    print('runtime layout contract: satisfied')
    return 0


if __name__ == '__main__':
    sys.exit(main())
