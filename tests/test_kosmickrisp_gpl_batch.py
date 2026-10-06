import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location("gpl_batch", Path(__file__).with_name("run_kosmickrisp_gpl_batch.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GplBatchTests(unittest.TestCase):
    def test_percentiles_use_interpolation(self):
        result = module.summarize([1000000, 2000000, 3000000, 4000000])
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["median_ms"], 2.5)
        self.assertAlmostEqual(result["p95_ms"], 3.85)

    def test_unrelated_output_is_not_a_metric(self):
        metrics = module.parse_metrics('device=test\nMETRIC {"kind":"draw_record","ns":3,"pass":0}\nPASS\n')
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0]["ns"], 3)

    def test_negative_and_non_integer_timings_are_rejected(self):
        for value in [-1, 1.5, True, None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.parse_metrics("METRIC " + json.dumps({"kind": "draw_record", "ns": value}))

    def test_first_draw_is_separate_from_reused_draws(self):
        rows = [{"name": "native", "phase": "cold", "status": "pass", "compiler_events": None,
                 "metrics": [{"kind": "draw_record", "ns": 10000000, "pass": 0},
                             {"kind": "draw_record", "ns": 1000, "pass": 1}]}]
        result = module.benchmark_summary(rows)
        self.assertEqual(result["native/cold/draw_record/first"]["median_ms"], 10)
        self.assertEqual(result["native/cold/draw_record/reuse"]["median_ms"], .001)
        self.assertFalse(any("driver/" in key for key in result))

    def test_failed_runs_do_not_enter_benchmarks(self):
        rows = [{"status": "fail", "name": "bad", "phase": "cold",
                 "metrics": [{"kind": "draw_record", "ns": 1, "pass": 0}]}]
        self.assertEqual(module.benchmark_summary(rows), {})

    def test_comparison_rejects_different_workloads(self):
        with self.assertRaisesRegex(ValueError, "different workload"):
            module.compare_reports({"workload_sha256": "a"}, {"workload_sha256": "b"})

    def test_comparison_reports_faster_and_slower_measurements(self):
        current = {"workload_sha256": "same", "benchmarks": {"draw": {"median_ms": 8, "p95_ms": 24}}}
        previous = {"workload_sha256": "same", "benchmarks": {"draw": {"median_ms": 10, "p95_ms": 20}}}
        result = module.compare_reports(current, previous)["draw"]
        self.assertAlmostEqual(result["median_change_percent"], -20)
        self.assertAlmostEqual(result["p95_change_percent"], 20)

    def test_environment_does_not_inherit_probe_options(self):
        with patch.dict(os.environ, {"KK_PROBE_LTO": "1", "MESA_SHADER_CACHE_DISABLE": "true", "MESA_KK_DEBUG": "gpl_nir"}):
            env = module.clean_env()
        self.assertNotIn("KK_PROBE_LTO", env)
        self.assertNotIn("MESA_SHADER_CACHE_DISABLE", env)
        self.assertNotIn("MESA_KK_DEBUG", env)

    def test_compiler_intervals_and_missing_instrumentation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            self.assertIsNone(module.parse_compiles(path))
            path.write_text("pso,prewarm,100,200\n")
            self.assertEqual(module.parse_compiles(path), [{"kind": "pso", "origin": "prewarm", "ns": 100}])
            path.write_text("pso,draw,200,100\n")
            with self.assertRaises(ValueError):
                module.parse_compiles(path)

    def test_timeouts_preserve_output_and_are_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(module.subprocess, "run", side_effect=subprocess.TimeoutExpired("probe", 1, output=b"partial\n", stderr=b"hung\n")):
                result = module.run_probe(root / "probe", root / "icd", root,
                                          module.scenario("timeout"), root / "case", 1)
            self.assertEqual(result["status"], "fail")
            self.assertIn("timeout", result["reasons"])
            self.assertEqual((root / "case/cold-stderr.log").read_text(), "hung\n")

    def test_disk_warm_does_not_load_the_application_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case"
            case.mkdir()
            (case / "pipeline.cache").write_bytes(b"application cache")
            completed = subprocess.CompletedProcess("probe", 0, 'METRIC {"kind":"draw_record","ns":1,"pass":0}\n', "")
            with patch.object(module.subprocess, "run", return_value=completed) as run:
                module.run_probe(root / "probe", root / "icd", root,
                                 module.scenario("disk"), case, 1, phase="disk-warm", benchmark=True)
            env = run.call_args.kwargs["env"]
            self.assertNotEqual(env["KK_PROBE_CACHE"], str(case / "pipeline.cache"))
            self.assertFalse(Path(env["KK_PROBE_CACHE"]).exists())
            self.assertNotIn("MESA_SHADER_CACHE_DISABLE", env)

    def test_unsupported_features_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(module.subprocess, "run", return_value=subprocess.CompletedProcess("probe", 77, "", "")):
                result = module.run_probe(root / "probe", root / "icd", root,
                                          module.scenario("unsupported"), root / "case", 1)
            self.assertEqual(result["status"], "skip")

    def test_success_without_measurements_is_not_a_benchmark_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(module.subprocess, "run", return_value=subprocess.CompletedProcess("probe", 0, "", "")):
                result = module.run_probe(root / "probe", root / "icd", root,
                                          module.scenario("empty"), root / "case", 1)
            self.assertEqual(result["status"], "fail")
            self.assertIn("Missing probe timing records", result["reasons"])


if __name__ == "__main__":
    unittest.main()
