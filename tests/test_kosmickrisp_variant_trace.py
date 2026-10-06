import unittest

from analyze_kosmickrisp_variants import analyze, union_and_exclusive


def event(phase, start, end=None, thread=1, request="pso", origin="draw"):
    return {"event": "variant", "phase": phase, "start_ns": start,
            "end_ns": start if end is None else end, "thread_id": thread,
            "request_id": request, "origin": origin}


class VariantTraceTest(unittest.TestCase):
    def test_nested_dependency_waits_are_exclusive(self):
        report = analyze([event("pso_wait", 10, 100),
                          event("fs_wait", 20, 50),
                          event("archive_load", 60, 90)])
        self.assertEqual(report["blocking_thread_total_ns"], 90)
        self.assertEqual(report["draw_threads"]["1"]["exclusive_ns"],
                         {"pso_wait": 30, "fs_wait": 30, "archive_load": 30})

    def test_overlap_and_separate_threads(self):
        report = analyze([event("pso_wait", 10, 100),
                          event("fs_wait", 50, 120),
                          event("pso_wait", 10, 100, thread=2)])
        self.assertEqual(report["draw_threads"]["1"]["blocking_union_ns"], 110)
        self.assertEqual(report["blocking_thread_total_ns"], 200)

    def test_worker_queue_delay_and_first_demand(self):
        report = analyze([event("enqueue", 10, origin="prewarm"),
                          event("worker_start", 80, origin="prewarm"),
                          event("complete", 150, origin="prewarm"),
                          event("first_demand", 100)])
        self.assertEqual(report["requests"]["pso"],
                         {"queue_delay_ns": 70, "ready_at_first_demand": False,
                          "readiness_delay_ns": 50})

    def test_ready_before_first_demand(self):
        report = analyze([event("complete", 50, origin="prewarm"),
                          event("first_demand", 100)])
        self.assertTrue(report["requests"]["pso"]["ready_at_first_demand"])
        self.assertEqual(report["blocking_thread_total_ns"], 0)

    def test_background_work_is_not_draw_blocking(self):
        report = analyze([event("archive_load", 10, 100, origin="prewarm"),
                          event("fs_prepare", 10, 200, origin="prewarm")])
        self.assertEqual(report["blocking_thread_total_ns"], 0)
        self.assertEqual(report["event_counts"]["fs_prepare"], 1)

    def test_draw_compilation_and_archive_io_are_blocking(self):
        report = analyze([event("fs_prepare", 0, 10),
                          event("pso_create", 10, 40),
                          event("archive_lookup", 10, 15),
                          event("archive_load", 15, 25),
                          event("native_create", 25, 40)])
        self.assertEqual(report["blocking_thread_total_ns"], 40)
        self.assertEqual(report["draw_threads"]["1"]["exclusive_ns"],
                         {"fs_prepare": 10, "archive_lookup": 5,
                          "archive_load": 10, "native_create": 15})

    def test_failure_without_completion_not_ready(self):
        report = analyze([event("failure", 50), event("first_demand", 100)])
        self.assertNotIn("pso", report["requests"])

    def test_dependencies_join_by_parent(self):
        dependency = event("fs_prepare", 10, 90, thread=2, request="fs",
                           origin="prewarm")
        dependency["parent_id"] = "pso"
        report = analyze([event("enqueue", 0), dependency,
                          event("first_demand", 100)])
        self.assertEqual(report["requests"]["pso"]["dependencies"], ["fs"])
        self.assertEqual(report["requests"]["pso"]["dependency_work_ns"],
                         {"fs": {"fs_prepare": 80}})
        self.assertEqual(report["blocking_thread_total_ns"], 0)

    def test_invalid_interval_rejected(self):
        with self.assertRaises(ValueError):
            analyze([event("fs_wait", 20, 10)])

    def test_empty_union(self):
        self.assertEqual(union_and_exclusive([]), (0, {}))


if __name__ == "__main__":
    unittest.main()
