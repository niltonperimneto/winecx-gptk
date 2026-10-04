#!/usr/bin/env python3
"""Check the package envelope and reject archive paths escaping the workspace."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile


def verify(directory, component):
    directory = Path(directory)
    metadata = json.loads((directory / 'metadata.json').read_text())
    if metadata['schema'] != 1 or metadata['component'] != component:
        raise ValueError('OCI package component/schema mismatch')
    digest = hashlib.sha256()
    with (directory / 'layer.tar.zst').open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if metadata['sha256'] != digest.hexdigest():
        raise ValueError('OCI package checksum mismatch')


def check_tar(stream):
    with tarfile.open(fileobj=stream, mode='r|') as archive:
        for entry in archive:
            path = PurePosixPath(entry.name)
            if path.is_absolute() or '..' in path.parts or entry.isdev() or entry.isfifo():
                raise ValueError(f'unsafe archive member: {entry.name}')
            if entry.issym() or entry.islnk():
                target = PurePosixPath(entry.linkname)
                resolved = path.parent / target if entry.issym() else target
                depth = 0
                for part in resolved.parts:
                    depth += -1 if part == '..' else (0 if part == '.' else 1)
                    if depth < 0:
                        raise ValueError(f'escaping archive link: {entry.name}')
                if target.is_absolute():
                    raise ValueError(f'absolute archive link: {entry.name}')

if __name__ == '__main__':
    if sys.argv[1] == 'check-tar':
        check_tar(sys.stdin.buffer)
    else:
        verify(sys.argv[2], sys.argv[3])
