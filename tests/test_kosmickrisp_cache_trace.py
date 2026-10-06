import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_kosmickrisp_cache as module


def shader(**changes):
    event = dict(event="shader", outcome="miss", stage=0, namespace="ns", precomp="source",
                 flags="flags", partition="partition", layout="layout", state="state", key="key",
                 start_ns=0, end_ns=0)
    event.update(changes)
    return event


def component(state="state", name="vertex_input", value="value"):
    return dict(event="state_component", namespace="ns", stages=1,
                state=state, component=name, hash=value)


class CacheTraceTests(unittest.TestCase):
    def compare(self, before, after):
        return module.compare_traces(before, after)

    def test_reordering_does_not_change_keys(self):
        events = [shader(precomp="a", key="a"), shader(precomp="b", key="b")]
        report = self.compare(events, list(reversed(events)))
        self.assertEqual(report["summary"]["stable_keys"], 2)
        self.assertEqual(report["key_changes"], [])

    def test_multiple_variants_match_as_sets(self):
        events = [shader(state="a", key="a"), shader(state="b", key="b")]
        report = self.compare(events, list(reversed(events)))
        self.assertEqual(report["summary"]["stable_keys"], 2)
        self.assertEqual(report["unpaired_variants"], [])

    def test_one_changed_variant_is_identified_after_exact_matches(self):
        before = [shader(state="same", key="same"), shader(state="old", key="old")]
        after = [shader(state="new", key="new"), shader(state="same", key="same")]
        report = self.compare(before, after)
        self.assertEqual(report["summary"]["stable_keys"], 1)
        self.assertEqual(report["summary"]["key_changes"], 1)

    def test_ambiguous_variants_are_not_arbitrarily_paired(self):
        report = self.compare([shader(state="a", key="a"), shader(state="b", key="b")],
                              [shader(state="c", key="c"), shader(state="d", key="d")])
        self.assertEqual(report["key_changes"], [])
        self.assertEqual(report["unpaired_variants"][0]["reason"], "ambiguous variants")

    def test_state_component_reports_first_semantic_difference(self):
        report = self.compare([shader(), component()],
                              [shader(state="new", key="new"), component("new", value="new")])
        self.assertEqual(report["key_changes"][0]["first_difference"], "state.vertex_input")

    def test_flags_layout_partition_and_unexplained_changes(self):
        for field in ("flags", "layout", "partition"):
            with self.subTest(field=field):
                report = self.compare([shader()], [shader(**{field: "new", "key": "new"})])
                self.assertEqual(report["key_changes"][0]["first_difference"], field)
        report = self.compare([shader()], [shader(key="new")])
        self.assertEqual(report["key_changes"][0]["first_difference"], "key (unexplained by logged components)")

    def test_namespace_change_does_not_become_stable_key_miss(self):
        report = self.compare([shader()], [shader(namespace="new")])
        self.assertTrue(report["namespace_diff"]["changed"])
        self.assertEqual(report["stable_key_misses"], [])
        self.assertEqual(report["key_changes"][0]["first_difference"], "namespace")

    def test_namespace_change_preserves_matching_of_multiple_variants(self):
        report = self.compare([shader(state="a", key="a"), shader(state="b", key="b")],
                              [shader(namespace="new", state="b", key="b"),
                               shader(namespace="new", state="a", key="a")])
        self.assertEqual(report["summary"]["stable_keys"], 2)
        self.assertEqual(report["unpaired_variants"], [])

    def test_empty_log_is_not_a_clean_cache_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_text("")
            with self.assertRaisesRegex(ValueError, "no shader trace events"):
                module.read_trace(path)

    def test_stable_key_misses_and_hits_are_distinct(self):
        report = self.compare([shader()], [shader(), shader(outcome="shaders", start_ns=5, end_ns=10)])
        self.assertEqual(report["summary"]["stable_key_misses"], 1)
        self.assertEqual(report["after_counts"]["compiler_intervals"], 1)
        report = self.compare([shader()], [shader(outcome="disk_hit")])
        self.assertEqual(report["stable_key_misses"], [])

    def test_rejected_cache_entry_is_reported(self):
        report = self.compare([shader()], [shader(outcome="deserialize_failed"), shader()])
        self.assertEqual(report["cache_rejects"][0]["rejects"], {"deserialize_failed": 1})
        self.assertEqual(report["summary"]["stable_key_misses"], 1)

    def test_generic_rejection_joins_the_semantic_shader_without_spurious_variants(self):
        report = self.compare([shader()], [shader(stage=6, outcome="cache_deserialize_rejected", precomp="zero",
                                                  flags="zero", partition="zero", layout="zero", state="zero"),
                                          shader(), shader(outcome="shaders")])
        self.assertEqual(report["cache_rejects"][0]["shader_stages"], [0])
        self.assertEqual(report["key_changes"], [])
        self.assertEqual(report["unpaired_variants"], [])
        self.assertEqual(report["summary"]["stable_key_misses"], 1)

    def test_generic_rejection_without_a_shader_keeps_the_key(self):
        report = self.compare([], [shader(stage=6, outcome="cache_deserialize_rejected", key="rejected")])
        self.assertEqual(report["cache_rejects"][0]["key"], "rejected")
        self.assertEqual(report["cache_rejects"][0]["shader_stages"], [])
        self.assertEqual(report["unpaired_variants"], [])

    def test_shared_compilation_interval_is_counted_once(self):
        report = self.compare([], [shader(outcome="shaders", start_ns=1, end_ns=2),
                                  shader(stage=4, outcome="shaders", start_ns=1, end_ns=2)])
        self.assertEqual(report["after_counts"]["compiler_shader_events"], 2)
        self.assertEqual(report["after_counts"]["compiler_intervals"], 1)

    def test_unknown_events_and_missing_optional_timings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_text(json.dumps({"event": "future_extension"}) + "\n" +
                            json.dumps({key: value for key, value in shader().items()
                                        if key not in ("start_ns", "end_ns")}) + "\n")
            self.assertEqual(len(module.read_trace(path)), 1)

    def test_invalid_json_and_shader_fields_fail_with_line_number(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            for content in ("{bad", json.dumps({"event": "shader", "stage": 0}),
                            json.dumps(shader(start_ns=5, end_ns=4)), "[]"):
                path.write_text(content)
                with self.assertRaisesRegex(ValueError, r":1:"):
                    module.read_trace(path)

    def test_cli_writes_machine_readable_report(self):
        with tempfile.TemporaryDirectory() as directory:
            before, after, output = (Path(directory) / name for name in ("before", "after", "report"))
            before.write_text(json.dumps(shader()) + "\n")
            after.write_text(json.dumps(shader(outcome="disk_hit")) + "\n")
            self.assertEqual(module.main([str(before), str(after), "--out", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())["summary"]["stable_keys"], 1)


if __name__ == "__main__":
    unittest.main()
