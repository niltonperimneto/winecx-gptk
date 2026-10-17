import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ImmutableReleaseTests(unittest.TestCase):
    def publish(self, existing):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'Libraries.tar.gz').write_bytes(b'archive')
            digest = hashlib.sha256(b'archive').hexdigest()
            (root / 'Libraries.tar.gz.sha256').write_text(digest + '  Libraries.tar.gz\n')
            fake = root / 'gh'
            fake.write_text('''#!/usr/bin/env python3
import os, pathlib, sys
args = sys.argv[1:]
if args[:2] == ['release', 'view']:
    sys.exit(0 if os.environ['EXISTING'] else 1)
elif args[:2] == ['release', 'download']:
    directory = pathlib.Path(args[args.index('--dir') + 1])
    (directory / 'Libraries.tar.gz.sha256').write_text(os.environ['EXISTING'] + '  Libraries.tar.gz\\n')
elif args[:2] == ['release', 'create']:
    pathlib.Path('created').touch()
else:
    pathlib.Path('unexpected-mutation').touch()
    sys.exit(3)
''')
            fake.chmod(0o755)
            value = digest if existing == 'same' else ('f' * 64 if existing == 'different' else '')
            env = dict(os.environ, EXISTING=value, GITHUB_SHA='a' * 40, RUNTIME_VERSION='5.0.1',
                       RUNNER_TEMP=str(root), PATH=f'{root}:{os.environ["PATH"]}')
            result = subprocess.run(['bash', str(ROOT / 'tools/publish_runtime.sh')], cwd=root,
                                    env=env, text=True, capture_output=True)
            return result, (root / 'created').exists(), (root / 'unexpected-mutation').exists()

    def test_existing_different_archive_is_never_overwritten(self):
        result, created, mutated = self.publish('different')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('different bytes', result.stdout)
        self.assertFalse(created or mutated)

    def test_identical_retry_preserves_all_existing_assets(self):
        result, created, mutated = self.publish('same')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(created or mutated)

    def test_new_version_creates_release(self):
        result, created, mutated = self.publish('new')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(created)
        self.assertFalse(mutated)
