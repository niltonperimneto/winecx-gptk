#!/usr/bin/env python3
"""Content keys include recipes, pins, architecture, and the Apple toolchain.

Each layer hashes only what can change its output, so a component bump
rebuilds the layers that consume it and restores every other one: a
relay12 or DXMT bump touches payloads, a Mesa bump touches kosmickrisp,
and a Wine bump touches tools and core.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
COMMON = ['tools/build/common.sh', 'tools/build/oci.sh', 'tools/build/archive.py',
          'tools/import_layer.sh', 'tools/build/cache_key.py']
WINE = ('WINECX_COMMIT', 'WINECX_REPO', 'NIXPKGS_REV', 'MACOSX_DEPLOYMENT_TARGET')
RECIPES = {
    'sysroot': ['tools/setup_sysroot.sh', 'tools/setup_mingw.sh'],
    'tools': ['tools/build_wine_tools.sh', 'tools/setup_sysroot.sh', 'tools/setup_mingw.sh',
              'tools/prepare_source.sh', 'patches', 'runtime/kosmickrisp/wine-loader.patch'],
    'core': ['tools/build_wine_core.sh', 'tools/configure_wine.sh', 'tools/make_wine.sh',
             'tools/setup_sysroot.sh', 'tools/setup_mingw.sh', 'tools/prepare_source.sh',
             'patches', 'runtime/kosmickrisp/wine-loader.patch'],
    'payloads': ['tools/fetch_payloads.sh'],
    'kosmickrisp': ['tools/build_kosmickrisp.sh', 'runtime/kosmickrisp/build.sh',
                    'runtime/kosmickrisp/pins.env', 'runtime/kosmickrisp/source-snapshot.py',
                    'runtime/kosmickrisp/optional_entrypoints.py',
                    'tests/kosmickrisp_probe.c', 'tests/dlopenall.c'],
}
ENVIRONMENT = {
    'sysroot': ('NIXPKGS_REV', 'MACOSX_DEPLOYMENT_TARGET'),
    'tools': WINE,
    'core': WINE + ('OPT_LEVEL', 'FAUDIO_VERSION'),
    'payloads': ('DXVK_VERSION', 'DXVK_UPSTREAM_SHA256', 'MOLTENVK_VERSION', 'DXMT_REPO',
                 'DXMT_COMMIT', 'DXMT_RELEASE_TAG', 'DXMT_ARTIFACT', 'DXMT_ARTIFACT_SHA256',
                 'RELAY12_REPO', 'RELAY12_COMMIT', 'RELAY12_RELEASE_TAG', 'RELAY12_ARTIFACT_SHA256'),
    'kosmickrisp': ('MACOSX_DEPLOYMENT_TARGET',),
}
# Source files read from the Wine checkout. The addon versions come from
# addons.c, so payloads follow Wine only when those versions move.
WINE_SOURCES = {'payloads': ['winecx/dlls/appwiz.cpl/addons.c']}
# Payloads are downloads verified by digest, independent of the build host.
HOST_INDEPENDENT = {'payloads'}


def key(component):
    digest = hashlib.sha256(b'winecx-oci-v2\0' + component.encode() + b'\0')
    for entry in COMMON + RECIPES[component]:
        path = ROOT / entry
        files = sorted(path.rglob('*')) if path.is_dir() else [path]
        for file in files:
            if file.is_file() and '.DS_Store' not in file.parts and '__pycache__' not in file.parts:
                digest.update(str(file.relative_to(ROOT)).encode() + b'\0' + file.read_bytes())
    for entry in WINE_SOURCES.get(component, []):
        path = ROOT / entry
        digest.update(entry.encode() + b'\0' + (path.read_bytes() if path.is_file() else b'<absent>'))
    for name in ENVIRONMENT[component]:
        digest.update(f'{name}={os.environ.get(name, "")}\0'.encode())
    if component not in HOST_INDEPENDENT:
        for command in (['uname', '-m'], ['/usr/bin/xcrun', '--show-sdk-version'], ['/usr/bin/clang', '--version']):
            digest.update(subprocess.check_output(command))
    return digest.hexdigest()


if __name__ == '__main__':
    print(key(sys.argv[1]))
