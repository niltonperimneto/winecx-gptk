#!/usr/bin/env python3
"""Fail when a runtime tree lacks a path Whisky relies on (contracts/runtime-layout.json)."""
import argparse
import json
import sys
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[1] / 'contracts/runtime-layout.json'


def missing(libraries, contract, kosmickrisp):
    if contract.get('schema') != 1:
        raise ValueError('unsupported runtime layout contract')
    paths = list(contract['required']) + (list(contract['kosmickrisp']) if kosmickrisp else [])
    return [path for path in paths if not (Path(libraries) / path).exists()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('libraries', type=Path)
    parser.add_argument('--kosmickrisp', action='store_true')
    args = parser.parse_args()
    absent = missing(args.libraries, json.loads(CONTRACT.read_text()), args.kosmickrisp)
    for path in absent:
        print(f'::error::runtime layout contract: missing Libraries/{path}')
    if absent:
        return 1
    print('runtime layout contract: satisfied')
    return 0


if __name__ == '__main__':
    sys.exit(main())
