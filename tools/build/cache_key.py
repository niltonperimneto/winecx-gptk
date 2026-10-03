#!/usr/bin/env python3
"""Content keys include recipes, pins, architecture, and the Apple toolchain."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
RECIPES = {
    'sysroot': ['tools/setup_sysroot.sh', 'tools/setup_mingw.sh'],
    'tools': ['tools/build_wine_tools.sh', 'tools/setup_sysroot.sh', 'tools/setup_mingw.sh', 'tools/prepare_source.sh', 'patches', 'runtime/kosmickrisp/wine-loader.patch'],
    'payloads': ['tools/fetch_payloads.sh', 'tools/build/pins.env', 'tools/prepare_source.sh', 'patches'],
    'kosmickrisp': ['tools/build_kosmickrisp.sh', 'runtime/kosmickrisp', 'tests/kosmickrisp_probe.c'],
}

def key(component):
    digest = hashlib.sha256(b'winecx-oci-v1\0')
    paths = ['tools/build/common.sh', 'tools/build/oci.sh', 'tools/build/archive.py', 'tools/import_layer.sh', 'tools/build/cache_key.py'] + RECIPES[component]
    for entry in paths:
        path = ROOT / entry
        files = sorted(path.rglob('*')) if path.is_dir() else [path]
        for file in files:
            if file.is_file() and '.DS_Store' not in file.parts and '__pycache__' not in file.parts:
                digest.update(str(file.relative_to(ROOT)).encode() + b'\0' + file.read_bytes())
    names = ('NIXPKGS_REV', 'MACOSX_DEPLOYMENT_TARGET') if component == 'sysroot' else (
        'WINECX_COMMIT', 'WINECX_REPO', 'NIXPKGS_REV', 'MACOSX_DEPLOYMENT_TARGET', 'KOSMICKRISP_ENABLED')
    for name in names:
        digest.update(f'{name}={os.environ.get(name, "")}\0'.encode())
    if component != 'payloads':
        for command in (['uname', '-m'], ['/usr/bin/xcrun', '--show-sdk-version'], ['/usr/bin/clang', '--version']):
            digest.update(subprocess.check_output(command))
    return digest.hexdigest()

if __name__ == '__main__':
    print(key(sys.argv[1]))
