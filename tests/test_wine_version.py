import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/build/wine_version.sh'


class AssembledWineVersionTests(unittest.TestCase):
    def version(self, output, status=0):
        with tempfile.TemporaryDirectory(prefix='runtime assembly ') as directory:
            executable = Path(directory) / 'wine64'
            executable.write_text(f'#!/bin/sh\nprintf "%s\\n" "{output}"\nexit {status}\n')
            executable.chmod(0o755)
            return subprocess.run(['bash', str(SCRIPT), str(executable)], cwd=directory,
                                  capture_output=True, text=True)

    def test_reads_relocated_binary_without_source_checkout(self):
        for version in ('11.19', '11.0.1', '11.19-rc1'):
            result = self.version(f'wine-{version}')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, version + '\n')

    def test_rejects_failed_or_malformed_version(self):
        for output, status in [('wine-11.19', 42), ('', 0), ('unexpected', 0),
                               ('wine-11.19/invalid', 0), ('wine-11.19\nextra', 0)]:
            result = self.version(output, status)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
