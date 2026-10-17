import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import contextlib
import io
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "hades", Path(__file__).resolve().parents[1] / "runtime/kosmickrisp/hades.py")
hades = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hades)


class HadesTests(unittest.TestCase):
    def fixture(self, root, body):
        wine = root / "Wine with spaces"
        (wine / "bin").mkdir(parents=True)
        script = '''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
if sys.argv[1:] == ['--version']:
    print('wine-fixture')
elif 'wineboot.exe' in sys.argv:
    (Path(os.environ['WINEPREFIX']) / 'drive_c/users/test').mkdir(parents=True, exist_ok=True)
else:
    (Path(os.environ['WINEPREFIX']) / 'arguments.json').write_text(json.dumps(sys.argv[1:]))
''' + body
        (wine / "bin/wine64").write_text(script)
        (wine / "bin/wine64").chmod(0o755)
        (wine / "bin/wineserver").write_text('#!/bin/sh\nexit 0\n')
        (wine / "bin/wineserver").chmod(0o755)
        (wine / "bin/wine-kosmickrisp").symlink_to("wine64")
        bundle = wine / "lib/kosmickrisp"
        bundle.mkdir(parents=True)
        for name in ("libvulkan.1.dylib", "libvulkan_kosmickrisp.dylib", "kosmickrisp_icd.json"):
            (bundle / name).touch()
        game = root / "Game with spaces"
        (game / "x64Vk").mkdir(parents=True)
        (game / "Content").mkdir()
        (game / "x64Vk/Hades.exe").touch()
        return ['hades.py', '--wine', str(wine), '--game-dir', str(game),
                '--prefix', str(root / 'prefix'), '--output', str(root / 'evidence'),
                '--backend', 'kosmickrisp']

    def test_command_preserves_arguments_and_reports_exit_without_claiming_gameplay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            argv = self.fixture(root, '    sys.exit(7)\n') + ['--', 'argument with spaces', 'a;b']
            with patch('sys.argv', argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(hades.main(), 7)
            report = json.loads((root / 'evidence/result.json').read_text())
            self.assertEqual(report['exit_code'], 7)
            self.assertFalse(report['gameplay_verified'])
            arguments = json.loads((root / 'prefix/arguments.json').read_text())
            self.assertEqual(arguments[1:], ['argument with spaces', 'a;b'])

    def test_missing_game_rejected_before_prefix_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            argv = self.fixture(root, '')
            (root / 'Game with spaces/x64Vk/Hades.exe').unlink()
            with patch('sys.argv', argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    hades.main()
            self.assertEqual(error.exception.code, 2)
            self.assertFalse((root / 'prefix').exists())

    def test_timeout_captures_evidence_and_terminates_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            argv = self.fixture(root, '    time.sleep(60)\n') + ['--timeout', '10']
            with patch('sys.argv', argv), patch.object(hades, 'sample_process') as sample, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(hades.main(), 124)
            report = json.loads((root / 'evidence/result.json').read_text())
            self.assertEqual(report['status'], 'timed_out')
            self.assertEqual(sample.call_count, 2)
            with self.assertRaises(ProcessLookupError):
                os.kill(report['pid'], 0)

    def test_backend_environment_does_not_inherit_disabled_mscoree_or_driver(self):
        with patch.dict(os.environ, {"WINEDLLOVERRIDES": "mscoree=", "VK_DRIVER_FILES": "/wrong",
                                     "CX_LIBVULKAN": "/wrong", "WINE_VULKAN_LIBRARY": "/wrong"}):
            env = hades.environment(Path("/prefix with spaces"), "kosmickrisp")
        self.assertEqual(env["WINEDLLOVERRIDES"], "mshtml,nvapi,nvapi64=")
        self.assertEqual(env["WINEPREFIX"], "/prefix with spaces")
        self.assertNotIn("CX_LIBVULKAN", env)
        self.assertNotIn("VK_DRIVER_FILES", env)
        self.assertNotIn("WINE_VULKAN_LIBRARY", env)

    def test_legacy_override_is_explicit(self):
        env = hades.environment(Path("/prefix"), "legacy-kosmickrisp", Path("/bundle with spaces"))
        self.assertEqual(env["CX_LIBVULKAN"], "/bundle with spaces/libvulkan.1.dylib")
        self.assertEqual(env["VK_DRIVER_FILES"], "/bundle with spaces/kosmickrisp_icd.json")

    def test_refuses_personal_prefix_and_concurrent_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "prefix"
            prefix.mkdir()
            (prefix / "user.reg").touch()
            with self.assertRaises(ValueError):
                hades.claim_prefix(prefix)
            owned = Path(tmp) / "owned"
            with hades.claim_prefix(owned):
                with self.assertRaises(ValueError):
                    hades.claim_prefix(owned)
            with hades.claim_prefix(owned):
                pass

    def test_save_isolation_unlinks_without_touching_original_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            documents = root / "personal"
            documents.mkdir()
            (documents / "keep.txt").write_text("untouched")
            prefix = root / "prefix"
            user = prefix / "drive_c/users/crossover"
            user.mkdir(parents=True)
            (user / "Documents").symlink_to(documents)
            hades.isolate_saves(prefix)
            self.assertFalse((user / "Documents").is_symlink())
            self.assertTrue((user / "Documents/Saved Games/Hades").is_dir())
            self.assertEqual(list(documents.iterdir()), [documents / "keep.txt"])

    def test_cleanup_targets_only_selected_prefix(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(hades.subprocess, "run") as run:
            env = {"WINEPREFIX": "/isolated prefix"}
            hades.stop_prefix(Path("/runtime"), env, Path(tmp))
            self.assertEqual(run.call_args.args[0], ["/runtime/bin/wineserver", "-k"])
            self.assertIs(run.call_args.kwargs["env"], env)


if __name__ == "__main__":
    unittest.main()
