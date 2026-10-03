import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_archive', ROOT / 'tools/build/archive.py')
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class OCIArchiveTests(unittest.TestCase):
    def test_envelope_accepts_matching_component_and_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = b'compressed fixture'
            (root / 'layer.tar.zst').write_bytes(data)
            metadata = {'schema': 1, 'component': 'core', 'sha256': hashlib.sha256(data).hexdigest()}
            (root / 'metadata.json').write_text(json.dumps(metadata))
            archive.verify(root, 'core')
            with self.assertRaises(ValueError):
                archive.verify(root, 'sysroot')
            (root / 'layer.tar.zst').write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                archive.verify(root, 'core')

    def check_members(self, members):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as tar:
            for name, kind, link in members:
                item = tarfile.TarInfo(name)
                item.type, item.linkname = kind, link
                tar.addfile(item)
        stream.seek(0)
        archive.check_tar(stream)

    def test_relative_runtime_links_are_preserved(self):
        self.check_members([('Libraries/Wine/bin/wine64', tarfile.SYMTYPE,
                             '../lib/wine/x86_64-unix/wine')])

    def test_source_relative_tool_links_are_allowed(self):
        self.check_members([('build-tools/include/wine/test.h', tarfile.SYMTYPE,
                             '../../../winecx/include/wine/test.h')])

    def test_archive_rejects_traversal_and_special_files(self):
        for name, kind, link in [('../escape', tarfile.REGTYPE, ''),
                                 ('/absolute', tarfile.REGTYPE, ''),
                                 ('device', tarfile.CHRTYPE, ''),
                                 ('fifo', tarfile.FIFOTYPE, ''),
                                 ('root/link', tarfile.SYMTYPE, '../../escape'),
                                 ('root/link', tarfile.SYMTYPE, '/etc/passwd'),
                                 ('root/link', tarfile.LNKTYPE, '../escape')]:
            with self.subTest(name=name, kind=kind, link=link), self.assertRaises(ValueError):
                self.check_members([(name, kind, link)])


class OCITransportTests(unittest.TestCase):
    def test_digest_transport_and_fail_closed_cache(self):
        """Exercise the real shell/archive path with a registry protocol fixture."""
        import os
        import shutil
        import subprocess
        if not shutil.which('zstd'):
            self.skipTest('zstd is required for OCI shell integration')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'tools', root / 'tools')
            (root / 'staging').mkdir()
            (root / 'staging/file').write_bytes(b'fixture')
            (root / 'staging/link').symlink_to('file')
            (root / 'bin').mkdir()
            fake = root / 'bin/oras'
            fake.write_text('''#!/usr/bin/env python3
import hashlib, os, pathlib, shutil, sys
args = sys.argv[1:]
registry = pathlib.Path(os.environ['FAKE_REGISTRY'])
registry.mkdir(exist_ok=True)
if args[0] == 'push':
    for name in ['layer.tar.zst', 'metadata.json']:
        shutil.copy(name, registry / name)
    digest = hashlib.sha256((registry / 'layer.tar.zst').read_bytes()).hexdigest()
    (registry / 'digest').write_text('sha256:' + digest)
elif args[0] == 'resolve':
    if os.environ.get('FAKE_ERROR'):
        print(os.environ['FAKE_ERROR'], file=sys.stderr)
        sys.exit(1)
    print((registry / 'digest').read_text())
elif args[0] == 'pull':
    output = pathlib.Path(args[args.index('--output') + 1])
    for name in ['layer.tar.zst', 'metadata.json']:
        shutil.copy(registry / name, output / name)
else:
    sys.exit(2)
''')
            fake.chmod(0o755)
            environment = {**os.environ, 'PATH': str(root / 'bin') + ':' + os.environ['PATH'],
                           'FAKE_REGISTRY': str(root / 'registry'), 'GITHUB_SHA': 'fixture',
                           'RUNNER_TEMP': str(root / 'tmp'), 'GITHUB_RUN_ID': '1',
                           'GITHUB_OUTPUT': str(root / 'output'), 'GITHUB_ENV': str(root / 'env'),
                           'GITHUB_PATH': str(root / 'path'), 'GITHUB_STEP_SUMMARY': str(root / 'summary')}
            def call(*args, **env):
                return subprocess.run(['bash', str(root / 'tools/build/oci.sh'), *args],
                                      env={**environment, **env}, capture_output=True, text=True)
            result = call('push', 'core', 'staging')
            self.assertEqual(result.returncode, 0, result.stderr)
            reference = (root / 'output').read_text().strip().removeprefix('ref=')
            self.assertIn('@sha256:', reference)
            shutil.rmtree(root / 'staging')
            result = call('pull', 'core', reference)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'staging/link').read_bytes(), b'fixture')
            result = call('pull', 'core', 'ghcr.io/example/core:moving-tag')
            self.assertNotEqual(result.returncode, 0)
            # Payload cache keys do not need Apple toolchain commands.
            result = call('restore', 'payloads', FAKE_ERROR='401 unauthorized')
            self.assertNotEqual(result.returncode, 0)
            result = call('restore', 'payloads', FAKE_ERROR='404 MANIFEST_UNKNOWN')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('hit=false', (root / 'output').read_text())
            # Simulate distinct Actions steps: NIX values are inherited but
            # the producer's new GITHUB_ENV file is empty.
            (root / 'tools/build/cache_key.py').write_text('print("fixture-key")')
            nix = root / 'bin/nix-store'
            nix.write_text("#!/bin/sh\ncase \"$1\" in\n"
                           "--query) printf '/nix/store/fixture\\n' ;;\n"
                           "--export) printf 'fixture NAR' ;;\n"
                           "--import) cat > \"$FAKE_REGISTRY/imported\" ;;\n"
                           "*) exit 2 ;;\nesac\n")
            nix.chmod(0o755)
            for name in ['store-outs.txt', 'native-store-outs.txt', 'nix-tool-outs.txt']:
                (root / name).write_text('/nix/store/fixture\n')
            (root / 'env').write_text('')
            result = call('push', 'sysroot', 'sysroot-closure.nar', 'sysroot.env',
                          'store-outs.txt', 'native-store-outs.txt', 'nix-tool-outs.txt',
                          NIX_TOOL_PATH='/nix/store/fixture/bin:',
                          NIX_PKG_CONFIG_PATH='/nix/store/fixture/lib/pkgconfig',
                          NIX_INCS=' -I/nix/store/fixture/include', NIX_LDFS=' -L/nix/store/fixture/lib')
            self.assertEqual(result.returncode, 0, result.stderr)
            reference = (root / 'output').read_text().splitlines()[-1].removeprefix('ref=')
            (root / 'sysroot.env').unlink()
            result = call('pull', 'sysroot', reference)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'registry/imported').read_bytes(), b'fixture NAR')
            self.assertIn('NIX_TOOL_PATH=/nix/store/fixture/bin:', (root / 'env').read_text())



if __name__ == '__main__':
    unittest.main()
