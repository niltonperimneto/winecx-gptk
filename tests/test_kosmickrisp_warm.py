import unittest

from analyze_kosmickrisp_warm import native_ledger, shader_ledger, wait_ledger


def shader(key="key", namespace="ns", precomp="ir", state="state"):
    return {"event": "shader", "outcome": "shaders", "namespace": namespace,
            "key": key, "precomp": precomp, "stage": 4, "state": state}


def variant(phase, start, end, origin="prewarm", request="pso", parent=""):
    return {"event": "variant", "phase": phase, "start_ns": start,
            "end_ns": end, "origin": origin, "request_id": request,
            "parent_id": parent, "thread_id": 1 if origin == "draw" else 2}


class WarmLedgerTests(unittest.TestCase):
    def test_native_keys_compiled_after_checkpoint_were_not_persisted(self):
        events = [{"event": "pso", "outcome": "compiler_fallback",
                   "namespace": "ns", "key": "old", "time_ns": 1},
                  {"event": "pso", "outcome": "compiler_fallback",
                   "namespace": "ns", "key": "late", "time_ns": 20}]
        result = native_ledger(events, events, persisted_through=10)
        self.assertEqual(result["counts"], {
            "previous_native_key_without_archive_hit": 1,
            "previous_native_key_not_checkpointed": 1})

    def test_previous_archive_hit_is_already_persisted(self):
        event = {"event": "pso", "outcome": "compiler_fallback",
                 "namespace": "ns", "key": "key", "time_ns": 30}
        previous = {**event, "outcome": "archive_hit", "time_ns": 20}
        result = native_ledger([event], [previous], persisted_through=10)
        self.assertEqual(result["counts"], {
            "previous_native_key_without_archive_hit": 1})

    def test_older_process_compile_is_not_in_current_capture_dataset(self):
        event = {"event": "pso", "outcome": "compiler_fallback",
                 "namespace": "ns", "key": "key", "time_ns": 5}
        result = native_ledger([event], [event], persisted_through=30,
                               persisted_from=10)
        self.assertEqual(result["counts"], {
            "previous_native_key_not_checkpointed": 1})

    def test_compile_calls_group_stages_and_keep_failures(self):
        timing = {"pid": 1, "thread_id": 2, "start_ns": 10, "end_ns": 20}
        events = [{**shader(), **timing},
                  {**shader(key="fs"), **timing, "stage": 4},
                  {**shader(key="failed"), **timing, "start_ns": 30,
                   "outcome": "shaders_failed"}]
        result = shader_ledger(events, [])
        self.assertEqual(result["compilation_events"], 2)
        self.assertEqual(result["compilation_calls"], 2)
        self.assertEqual(len(result["failed_events"]), 1)

    def test_exact_key_recompiled(self):
        result = shader_ledger([shader()], [shader()])
        self.assertEqual(result["counts"], {"previously_accepted_key_recompiled": 1})

    def test_cached_partition_peer_is_not_a_cache_miss(self):
        result = shader_ledger([{**shader(), "outcome": "disk_hit"}, shader()],
                               [shader()])
        self.assertEqual(result["counts"], {"cached_partition_peer_recompiled": 1})
        self.assertEqual(result["ledger"][0]["lookup_outcome"], "disk_hit")

    def test_new_shader_and_changed_state(self):
        result = shader_ledger([shader(key="new", state="new"),
                                shader(key="other", precomp="new_ir")], [shader()])
        self.assertEqual(result["counts"], {"new_state": 1, "new_shader": 1})
        self.assertEqual(result["ledger"][0]["changed_components"], ["state"])

    def test_namespace_change(self):
        result = shader_ledger([shader(namespace="new")], [shader()])
        self.assertEqual(result["counts"], {"namespace_change": 1})

    def test_miss_is_not_previously_accepted(self):
        old = {**shader(), "outcome": "miss"}
        result = shader_ledger([shader()], [old])
        self.assertEqual(result["counts"], {"new_shader": 1})

    def test_key_changes_without_component_changes_remain_unexplained(self):
        result = shader_ledger([shader(key="new")], [shader()])
        self.assertEqual(result["counts"], {"unexplained_key_change": 1})

    def test_wait_owner_nested_work_and_queue(self):
        events = [variant("enqueue", 0, 0), variant("worker_start", 30, 30),
                  variant("pso_wait", 10, 100, origin="draw"),
                  variant("fs_prepare", 30, 60, request="fs", parent="pso"),
                  variant("native_create", 40, 60, request="fs", parent="pso"),
                  variant("native_create", 60, 90, request="native", parent="pso")]
        wait = wait_ledger(events)[0]
        self.assertEqual(wait["queue_delay_during_wait_ns"], 20)
        self.assertEqual(sum(wait["owner_work_ns"].values()), 60)
        self.assertEqual(wait["unattributed_ns"], 10)

    def test_shared_native_owner_is_found_across_recipe_parents(self):
        events = [variant("pso_wait", 10, 100, origin="draw"),
                  variant("pso_wait", 10, 100, request="native", parent="pso"),
                  variant("native_create", 0, 100, request="native", parent="other")]
        wait = wait_ledger(events)[0]
        self.assertEqual(wait["owner_work_ns"], {"native_create": 90})
        self.assertEqual(wait["unattributed_ns"], 0)

    def test_native_owner_has_a_distinct_archive_identity(self):
        events = [variant("pso_wait", 10, 100, origin="draw"),
                  variant("pso_wait", 10, 100, request="native", parent="pso"),
                  variant("pso_create", 0, 100, request="native", parent="other"),
                  variant("native_create", 0, 100, request="archive", parent="other")]
        wait = wait_ledger(events)[0]
        self.assertEqual(sum(wait["owner_work_ns"].values()), 90)
        self.assertEqual(wait["unattributed_ns"], 0)

    def test_queue_and_shared_native_work_count_once(self):
        events = [variant("enqueue", 0, 0), variant("worker_start", 50, 50),
                  variant("pso_wait", 10, 100, origin="draw"),
                  variant("native_create", 0, 100, request="native", parent="pso")]
        wait = wait_ledger(events)[0]
        self.assertEqual(sum(wait["owner_work_ns"].values()) +
                         wait["queue_delay_during_wait_ns"], 90)
        self.assertEqual(wait["unattributed_ns"], 0)

    def test_native_recompile_and_new_key(self):
        native = {"event": "pso", "outcome": "compiler_fallback",
                  "namespace": "ns", "key": "native"}
        result = native_ledger([native, {**native, "key": "new"}], [native])
        self.assertEqual(result["counts"],
                         {"previous_native_key_without_archive_hit": 1,
                          "new_native_key": 1})

    def test_wait_window_clips_nested_work(self):
        events = [variant("pso_wait", 0, 100, origin="draw"),
                  variant("native_create", 0, 100, request="native", parent="pso")]
        waits = wait_ledger(events, 20, 80)
        self.assertEqual(waits[0]["duration_ns"], 60)
        self.assertEqual(waits[0]["owner_work_ns"], {"native_create": 60})
        self.assertEqual(wait_ledger(events, 100, 200), [])

    def test_state_components_identify_the_changed_subsystem(self):
        old = {"event": "state_component", "namespace": "ns", "state": "state",
               "component": "multisampling", "hash": "old"}
        new = {**old, "state": "new", "hash": "new"}
        result = shader_ledger([new, shader(key="new", state="new")], [old, shader()])
        self.assertEqual(result["ledger"][0]["changed_state_components"],
                         ["multisampling"])


if __name__ == "__main__":
    unittest.main()
