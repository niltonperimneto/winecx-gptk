import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime/kosmickrisp"))
from game import extract_archive, run_game
from readiness import blockers
from validate import parse_capabilities, run_probe, verify_manifest


class ValidationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def make_manifest(self):
        (self.root / "probe.exe").write_bytes(b"probe")
        manifest = {"formatVersion": 1, "files": [{"path": "probe.exe", "size": 5,
                    "sha256": hashlib.sha256(b"probe").hexdigest()}]}
        (self.root / "RuntimeManifest.json").write_text(json.dumps(manifest))
        return manifest

    def test_manifest_accepts_exact_payload(self):
        self.make_manifest()
        verify_manifest(self.root)

    def test_manifest_rejects_corruption(self):
        self.make_manifest()
        (self.root / "probe.exe").write_bytes(b"wrong")
        with self.assertRaises(ValueError):
            verify_manifest(self.root)

    def test_manifest_rejects_undeclared_files(self):
        self.make_manifest()
        (self.root / "extra.dll").touch()
        with self.assertRaises(ValueError):
            verify_manifest(self.root)

    def test_manifest_rejects_traversal(self):
        manifest = self.make_manifest()
        manifest["files"][0]["path"] = "../escape"
        (self.root / "RuntimeManifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            verify_manifest(self.root)

    def test_probe_timeout_is_a_failure(self):
        code, _, text = run_probe([sys.executable, "-c", "import time; time.sleep(5)"],
                                  os.environ, self.root / "timeout.log", timeout=0.1)
        self.assertEqual(code, 124)
        self.assertIn("Timed out", text)

    def test_capabilities_preserve_real_values(self):
        parsed = parse_capabilities("geometryShader=0 tessellationShader=1\r\nextension=VK_KHR_swapchain\r\n")
        self.assertEqual(parsed["geometryShader"], "0")
        self.assertNotIn("VK_EXT_transform_feedback", parsed["extensions"])

    def test_readiness_rejects_missing_evidence(self):
        self.assertTrue(blockers({"schema": 1, "passed": True}))

    def test_readiness_rejects_known_missing_features(self):
        report = {"schema": 1, "passed": True,
                  "checks": {key: {"status": "passed"} for key in
                             ("macos26", "manifest", "host", "loader-override-negative", "wine-x86_64", "wine-i686")},
                  "migration": {key: {"status": "passed"} for key in ("dxvk", "shader_correctness", "game")}}
        self.assertFalse(blockers(report))
        report["migration"]["dxvk"]["known_missing"] = ["geometryShader"]
        self.assertTrue(blockers(report))

    def test_unconfigured_game_is_blocked_not_passed(self):
        config = self.root / "game.json"
        config.write_text("null")
        self.assertEqual(run_game(config, None, {}, self.root, None)["status"], "blocked")

    def test_selected_hades_does_not_run_without_provisioning(self):
        config = Path(__file__).resolve().parents[1] / "runtime/kosmickrisp/game.json"
        with patch("game.urllib.request.urlopen") as download:
            result = run_game(config, None, {}, self.root, None)
        download.assert_not_called()
        self.assertEqual(result["benchmark"], "Hades")
        self.assertEqual(result["renderer"], "Vulkan")
        self.assertEqual(result["status"], "blocked")

    def test_archive_rejects_traversal(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("../escape.exe", b"bad")
        with self.assertRaises(ValueError):
            extract_archive(data.getvalue(), self.root)

    def run_fake_game(self, output):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("benchmark.exe", b"fixture")
        archive = data.getvalue()
        config = {"name": "fixture", "archive_url": "https://example.invalid/benchmark.zip",
                  "archive_sha256": hashlib.sha256(archive).hexdigest(), "executable": "benchmark.exe",
                  "arguments": [], "timeout_seconds": 10, "success_pattern": "REPLAY PASS",
                  "driver_pattern": "KosmicKrisp", "metric_pattern": "fps=([0-9.]+)", "minimum_metric": 30}
        path = self.root / "game.json"
        path.write_text(json.dumps(config))
        with patch("game.urllib.request.urlopen", return_value=io.BytesIO(archive)):
            return run_game(path, self.root / "launcher", {}, self.root,
                            lambda *args, **kwargs: (0, 1.0, output))

    def test_game_requires_backend_evidence(self):
        self.assertEqual(self.run_fake_game("REPLAY PASS fps=60")["status"], "failed")

    def test_game_enforces_performance_threshold(self):
        self.assertEqual(self.run_fake_game("KosmicKrisp REPLAY PASS fps=20")["status"], "failed")

    def test_game_accepts_complete_evidence(self):
        self.assertEqual(self.run_fake_game("KosmicKrisp REPLAY PASS fps=60")["status"], "passed")


if __name__ == "__main__":
    unittest.main()
