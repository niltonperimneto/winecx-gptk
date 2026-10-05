#!/usr/bin/env python3
"""Assemble only the explicitly ordered Mesa patch series."""
from pathlib import Path
import sys


def assemble(directory, output):
    directory, output = Path(directory), Path(output)
    names = directory.joinpath('series').read_text().splitlines()
    if not names or len(names) != len(set(names)):
        raise ValueError('empty or duplicate patch series')
    if any(Path(n).name != n or not n.endswith('.patch') for n in names):
        raise ValueError('invalid patch name')
    if set(names) != {p.name for p in directory.glob('*.patch')}:
        raise ValueError('patch directory and series disagree')
    output.write_bytes(b'\n'.join((directory / n).read_bytes() for n in names))


if __name__ == '__main__':
    assemble(*sys.argv[1:])
