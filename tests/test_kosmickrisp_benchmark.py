import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('benchmark', Path(__file__).resolve().parents[1] / 'runtime/kosmickrisp/benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fixed scene campaign ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.runtime = self.root / 'runtime'
        self.bundle = self.root / 'bundle'
        self.bottle = self.root / 'bottle'
        self.output = self.root / 'campaign'
        self.scene = self.root / 'scene.json'
        self.fixture = self.root / 'scene.dem'
        self.fixture.write_bytes(b'recorded scene')
        for path in (self.runtime / 'Wine/bin/wine64', self.runtime / 'DXVK3/x32/d3d9.dll',
                     self.bundle / 'libvulkan_kosmickrisp.dylib', self.bundle / 'libvulkan.1.dylib',
                     self.bottle / 'drive_c/Program Files (x86)/Steam/steamapps/common/Portal 2/portal2.exe'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(path.name.encode())
        self.scene.write_text(json.dumps({'game': 'portal2-d3d9', 'id': 'fixed-demo',
            'arguments': ['+timedemo', 'scene'], 'reproduction': 'Replay recorded scene without input.',
            'fixtures': [str(self.fixture)]}))

    def create(self, output=None, stage='gpl'):
        return benchmark.make_plan(self.runtime, self.bundle, self.bottle, 'portal2-d3d9',
                                   self.scene, output or self.output, stage)

    def test_balanced_order_and_cache_isolation(self):
        plan = self.create()
        self.assertEqual(len(plan['jobs']), 9)
        self.assertEqual(len({j['work'] for j in plan['jobs']}), 9)
        firsts = [plan['jobs'][i]['condition'] for i in (0, 3, 6)]
        self.assertEqual(len(set(firsts)), 3)
        for job in plan['jobs']:
            self.assertTrue((self.output / job['work'] / 'dxvk.conf').is_file())
        benchmark.verify(plan)

    def test_replaced_shader_or_fixture_invalidates_campaign(self):
        plan = self.create()
        self.fixture.write_bytes(b'changed scene')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            benchmark.verify(plan)

    def test_no_fixture_is_rejected(self):
        self.scene.write_text(json.dumps({'game': 'portal2-d3d9', 'id': 'free-play',
                                         'arguments': [], 'reproduction': 'Uncontrolled input.'}))
        with self.assertRaisesRegex(ValueError, 'fixture'):
            self.create()
        self.assertFalse(self.output.exists())

    def test_stage_keeps_other_settings_fixed(self):
        rows = benchmark.conditions('threads', 'True')
        self.assertEqual([r[1]['dxvk.numCompilerThreads'] for r in rows], ['0', '2', '4'])
        self.assertTrue(all(r[1]['dxvk.enableGraphicsPipelineLibrary'] == 'True' for r in rows))
        self.assertTrue(all('dxvk.numCompilerThreads' not in r[1] for r in benchmark.conditions('gpl')))

    def test_vi_stage_changes_only_the_fetch_path(self):
        rows = benchmark.conditions('vi')
        names = [r[0] for r in rows]
        self.assertEqual(len(names), 5)
        self.assertTrue(all('MESA_KK_DEBUG' in r[2] for r in rows))
        controlled = [r for r in rows if r[0] != 'vi-shipping-default']
        self.assertTrue(all(r[1] == {'dxvk.enableGraphicsPipelineLibrary': 'False'} for r in controlled))
        flags = {r[0]: set(filter(None, r[2]['MESA_KK_DEBUG'].split(','))) for r in rows}
        for dynamic, control in benchmark.VI_EFFECTS:
            self.assertIn(dynamic, names)
            self.assertIn(control, names)
            # Each pair differs by exactly the dynamic_vi flag.
            self.assertEqual(flags[dynamic] ^ flags[control], {'dynamic_vi'})
        self.assertTrue(all(r[2] == {} for r in benchmark.conditions('gpl')))

    def test_vi_report_is_complete_with_effects(self):
        plan = self.create(stage='vi')
        self.assertEqual(len(plan['jobs']), 15)
        self.make_results(plan, fps={'vi-dynamic-inline': 45})
        report = benchmark.analyze(self.output / 'plan.json')
        self.assertTrue(report['complete'], report['invalid'])
        self.assertEqual(len(report['rows']), 15)
        inline = [e for e in report['effects'] if e['dynamic'] == 'vi-dynamic-inline' and e['cache_state'] == 'warm']
        self.assertEqual(inline[0]['control'], 'vi-static-nohelpers')
        self.assertEqual(inline[0]['delta']['mean_fps']['difference'], -15)
        self.assertEqual(inline[0]['delta']['mean_fps']['percent'], -25)

    def test_vi_run_without_requested_debug_flags_is_invalid(self):
        plan = self.create(stage='vi')
        self.make_results(plan)
        job = next(j for j in plan['jobs'] if j['condition'] == 'vi-dynamic-inline')
        path = self.output / job['work'] / 'runs/warm/summary.json'
        data = json.loads(path.read_text())
        data['meta']['env'] = {}
        path.write_text(json.dumps(data))
        report = benchmark.analyze(self.output / 'plan.json')
        self.assertFalse(report['complete'])
        self.assertIn('environment not recorded', str(report['invalid']))

    def test_run_passes_condition_environment_to_stutter(self):
        plan = self.create(stage='vi')
        commands = []

        def fake_run(command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0)

        with mock.patch.object(benchmark.subprocess, 'run', fake_run):
            benchmark.run(self.output / 'plan.json', host=self.cool_ac, sleep=lambda s: None)
        self.assertEqual(len(commands), len(plan['jobs']))
        for job, command in zip(plan['jobs'], commands):
            pairs = [command[i + 1] for i, arg in enumerate(command) if arg == '--env']
            self.assertIn('MESA_KK_DEBUG=' + job['env']['MESA_KK_DEBUG'], pairs)

    @staticmethod
    def cool_ac():
        return {'power': 'ac', 'thermal': 'nominal'}

    def run_with(self, host, **kwargs):
        sleeps = []
        with mock.patch.object(benchmark.subprocess, 'run',
                               lambda command, **kw: subprocess.CompletedProcess(command, 0)):
            benchmark.run(self.output / 'plan.json', host=host, sleep=sleeps.append, **kwargs)
        return sleeps

    def test_run_refuses_battery_unless_allowed(self):
        self.create(stage='vi')
        battery = lambda: {'power': 'battery', 'thermal': 'nominal'}
        with self.assertRaisesRegex(ValueError, 'battery'):
            self.run_with(battery)
        self.assertFalse((self.output / 'execution.json').exists())
        self.run_with(battery, allow_battery=True)
        execution = json.loads((self.output / 'execution.json').read_text())
        self.assertTrue(all(r['host']['before']['power'] == 'battery' for r in execution))

    def test_run_cools_down_between_jobs_and_waits_out_thermal_pressure(self):
        plan = self.create(stage='vi')
        states = iter(['nominal', 'serious', 'serious', 'fair'] + ['nominal'] * 100)
        sleeps = self.run_with(lambda: {'power': 'ac', 'thermal': next(states)}, cooldown=30)
        # One cooldown before every job but the first, plus two thermal polls.
        self.assertEqual(sleeps.count(30), len(plan['jobs']) - 1)
        self.assertEqual(sleeps.count(10), 2)

    def test_hot_or_battery_jobs_are_invalid(self):
        plan = self.create(stage='vi')
        self.make_results(plan)
        records = [dict(job, returncode=0, host={'before': self.cool_ac(), 'after': self.cool_ac()})
                   for job in plan['jobs']]
        records[0]['host']['after'] = {'power': 'ac', 'thermal': 'serious'}
        records[1]['host']['before'] = {'power': 'battery', 'thermal': 'nominal'}
        (self.output / 'execution.json').write_text(json.dumps(records))
        report = benchmark.analyze(self.output / 'plan.json')
        self.assertFalse(report['complete'])
        self.assertIn('thermal pressure', str(report['invalid']))
        self.assertIn('battery', str(report['invalid']))
        records[0]['host']['after'] = self.cool_ac()
        records[1]['host']['before'] = self.cool_ac()
        (self.output / 'execution.json').write_text(json.dumps(records))
        self.assertTrue(benchmark.analyze(self.output / 'plan.json')['complete'])

    def test_unexpected_dxvk_build_is_invalid(self):
        (self.runtime / 'DXVK3/SOURCE.txt').write_text('DXVK_VERSION=3.1.1\n')
        plan = self.create(stage='vi')
        self.assertEqual(plan['dxvk_version'], '3.1.1')
        self.make_results(plan)
        self.assertTrue(benchmark.analyze(self.output / 'plan.json')['complete'])
        job = plan['jobs'][0]
        path = self.output / job['work'] / 'runs/warm/summary.json'
        data = json.loads(path.read_text())
        data['dxvk']['version'] = 'v2.3-valve'
        path.write_text(json.dumps(data))
        report = benchmark.analyze(self.output / 'plan.json')
        self.assertFalse(report['complete'])
        self.assertIn("not the runtime's 3.1.1", str(report['invalid']))

    def make_results(self, plan, fps=None):
        for job in plan['jobs']:
            for label in ('cold', 'warm', 'warm2'):
                path = self.output / job['work'] / 'runs' / label
                path.mkdir(parents=True)
                mean_fps = (fps or {}).get(job['condition'], 60)
                data = {'frames': {'mean_fps': mean_fps, 'p99_ms': 20, 'hitches': 1, 'one_percent_low_fps': 40},
                        'dxvk': {'backend_verified': True, 'errors': 0, 'rejections': [], 'version': 'v3.1.1',
                                 'gpl': True, 'effective_configuration': job['settings']},
                        'meta': {'label': label, 'env': dict(job.get('env', {})),
                                 'driver_sha256': plan['hashes'][str(self.bundle / 'libvulkan_kosmickrisp.dylib')],
                                 'scene': {'sha256': plan['hashes'][str(self.scene)]},
                                 'termination': {'reason': 'natural_exit', 'returncode': 0}}}
                (path / 'summary.json').write_text(json.dumps(data))

    def test_summary_requires_all_repetitions_and_review(self):
        plan = self.create()
        report = benchmark.analyze(self.output / 'plan.json')
        self.assertFalse(report['complete'])
        self.make_results(plan)
        report = benchmark.analyze(self.output / 'plan.json')
        self.assertTrue(report['complete'])
        self.assertFalse(report['performance_claim_eligible'])
        self.assertEqual(report['rows'][0]['metrics']['p99_ms']['median'], 20)

    def test_wrong_driver_or_duplicate_results_are_invalid(self):
        plan = self.create()
        self.make_results(plan)
        path = self.output / plan['jobs'][0]['work'] / 'runs/cold/summary.json'
        data = json.loads(path.read_text())
        data['meta']['driver_sha256'] = '0' * 64
        path.write_text(json.dumps(data))
        report = benchmark.analyze(self.output / 'plan.json')
        self.assertFalse(report['complete'])
        self.assertIn('driver differs', str(report['invalid']))

    def test_ignored_configuration_is_rejected(self):
        plan = self.create()
        self.make_results(plan)
        path = self.output / plan['jobs'][0]['work'] / 'runs/cold/summary.json'
        data = json.loads(path.read_text())
        data['dxvk']['effective_configuration'] = {}
        path.write_text(json.dumps(data))
        report = benchmark.analyze(self.output / 'plan.json')
        self.assertFalse(report['complete'])
        self.assertIn('configuration not verified', str(report['invalid']))


if __name__ == '__main__':
    unittest.main()
