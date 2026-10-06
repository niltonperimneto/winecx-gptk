import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zlib
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_kosmickrisp_variant_replay as replay
import run_kosmickrisp_gpl_batch as batch


def summaries():
    return {phase: {'event': 'variant_summary', 'phase': phase, 'count': 0,
        'duration_ns': 0, 'draw_count': 0, 'draw_duration_ns': 0}
        for phase in replay.BLOCKING_PHASES | {'ready_hit', 'first_demand'}}


def exercised_stats():
    stats = summaries()
    for phase in ('ready_hit', 'first_demand'):
        stats[phase]['count'] = stats[phase]['draw_count'] = 1
    return stats


class VariantReplayTests(unittest.TestCase):
    def test_ready_warm_draw_has_no_work(self):
        metrics = [{'kind': 'variant_readiness', 'ns': 20, 'ready': True}]
        self.assertEqual(replay.readiness_errors(metrics, exercised_stats(), [], True), [])

    def test_archive_reuse_at_draw_is_still_work(self):
        metrics = [{'kind': 'variant_readiness', 'ns': 20, 'ready': True}]
        errors = replay.readiness_errors(metrics, exercised_stats(),
            [{'kind': 'pso_archive', 'origin': 'draw', 'ns': 1}], True)
        self.assertTrue(any('pso_archive' in error for error in errors))

    def test_unknown_draw_work_cannot_escape_gate(self):
        errors = replay.readiness_errors([{'kind': 'variant_readiness', 'ready': True}],
            exercised_stats(), [{'kind': 'future_work', 'origin': 'draw'}], True)
        self.assertTrue(any('future_work' in error for error in errors))

    def test_pending_prediction_is_not_ready(self):
        stats = exercised_stats()
        stats['pso_wait']['count'] = stats['pso_wait']['draw_count'] = 1
        errors = replay.readiness_errors([{'kind': 'variant_readiness', 'ready': True}], stats, [], True)
        self.assertTrue(any('pso_wait' in error for error in errors))

    def test_missing_readiness_and_empty_draw_are_failures(self):
        errors = replay.readiness_errors([], summaries(), [], True)
        self.assertTrue(any('drain' in error for error in errors))
        self.assertTrue(any('exercised' in error for error in errors))

    def test_cold_and_immediate_draws_do_not_claim_zero(self):
        stats = exercised_stats()
        stats['native_create']['count'] = stats['native_create']['draw_count'] = 1
        self.assertEqual(replay.readiness_errors([], stats,
            [{'kind': 'pso', 'origin': 'draw'}], False), [])

    def test_incomplete_negative_and_duplicate_counters_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stats.jsonl'
            valid = list(exercised_stats().values())
            path.write_text(''.join(json.dumps(row) + '\n' for row in valid))
            self.assertEqual(len(replay.parse_stats(path)), len(valid))
            for rows in (valid[:-1], valid + valid[:1],
                [dict(valid[0], draw_count=-1)] + valid[1:]):
                path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
                with self.assertRaises(ValueError):
                    replay.parse_stats(path)

    def test_timeout_preserves_diagnostic_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(replay.subprocess, 'run', side_effect=subprocess.TimeoutExpired(
                'probe', 1, output=b'partial\n', stderr=b'hung\n')):
                result = replay.run_probe(root / 'probe', root / 'icd', root,
                    batch.scenario('timeout'), root / 'case', 'cold', 1)
            self.assertEqual(result['status'], 'fail')
            self.assertEqual((root / 'case/cold-stderr.log').read_text(), 'hung\n')

    def test_artificial_delay_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'Artificial'):
                replay.run_probe(root / 'probe', root / 'icd', root,
                    batch.scenario('delay', options={'KK_PROBE_PREWARM_DELAY_MS': '1'}),
                    root / 'case', 'cold', 1)

    def test_corruption_targets_history_and_preserves_other_cache_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / 'history'
            shader = root / 'shader'
            archive = root / 'archive'
            history.write_bytes(b'header' + zlib.compress(b'KKVHIST1' + bytes(48)))
            shader.write_bytes(b'header' + zlib.compress(b'MSL_SHADER'))
            archive.write_bytes(b'header' + zlib.compress(b'METAL_ARCHIVE'))
            original_shader, original_archive = shader.read_bytes(), archive.read_bytes()
            records = replay.corrupt_history(root)
            self.assertEqual([record['path'] for record in records], [str(history)])
            self.assertEqual(history.read_bytes(), b'KKVHIST1')
            self.assertEqual(shader.read_bytes(), original_shader)
            self.assertEqual(archive.read_bytes(), original_archive)

    def test_absent_history_cannot_claim_corruption_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'No isolated history'):
                replay.corrupt_history(Path(directory))

    def test_budget_not_ready_cannot_satisfy_zero_stall_gate(self):
        errors = replay.readiness_errors([{'kind': 'variant_readiness', 'ready': False, 'result': 1}],
            exercised_stats(), [], True)
        self.assertTrue(any('drain' in error for error in errors))

    def test_unseen_identity_uses_exact_recipe_ids(self):
        result = {'variant_events': [
            {'phase': 'first_demand', 'origin': 'draw', 'request_id': 'exact'},
            {'phase': 'enqueue', 'origin': 'prewarm', 'request_id': 'other'}]}
        self.assertEqual(replay.demands(result), {'exact'})

    def test_distinct_default_and_exact_prediction_can_both_be_prewarmed(self):
        events = [
            {'event': 'pso', 'origin': 'prewarm', 'key': 'default'},
            {'event': 'pso', 'origin': 'prewarm', 'key': 'exact'},
            {'event': 'pso', 'origin': 'draw', 'key': 'exact', 'outcome': 'prewarm_match'},
            {'event': 'pso', 'origin': 'draw', 'key': 'default', 'outcome': 'prewarm_unused'}]
        self.assertIsNone(batch.prewarm_check(events, 'distinct'))
        self.assertIsNotNone(batch.prewarm_check(events[1:3], 'distinct'))


if __name__ == '__main__':
    unittest.main()
