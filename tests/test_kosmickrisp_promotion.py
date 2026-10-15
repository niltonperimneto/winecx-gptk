import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('promotion', Path(__file__).resolve().parents[1] /
                                              'runtime/kosmickrisp/promotion.py')
promotion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(promotion)


class PromotionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.record = self.file('evidence', b'DXVK on KosmicKrisp')
        self.frames = self.file('frames.json', json.dumps([10] * 3000).encode())
        self.run = dict(focused=True, awake=True, capture_valid=True, rendering_correct=True,
                        visual_evidence=self.record, frame_times=self.frames)
        self.lane = dict(runtime_sha256='a' * 64,
                         warmups=[dict(completed=True, log=self.record)] * 2,
                         measured=[self.run] * 3)
        self.validation = dict(manifest_sha256='b' * 64, archive_sha256='a' * 64, os='26.1')
        self.campaign = dict(schema=1, manifest_sha256='b' * 64, os='26.1', hardware='fixture GPU', cases=[])
        for title in promotion.TITLES:
            self.campaign['cases'].append(dict(id=title, resolution=[1280, 720], vsync=False,
                settings=self.record, scene=self.record, harness=self.record, game_build=self.record,
                gameplay_confirmed=True, candidate_backend_log=self.record, visual_evidence=self.record,
                gpu_compositing=True, game_backend_preserved=True,
                baseline=dict(copy.deepcopy(self.lane), runtime_sha256='c' * 64), candidate=copy.deepcopy(self.lane)))

    def file(self, name, data):
        (self.root / name).write_bytes(data)
        return dict(path=name, sha256=hashlib.sha256(data).hexdigest())

    def blocked(self):
        return promotion.campaign_blockers(self.campaign, self.root, self.validation)

    def test_complete_matching_campaign_passes(self):
        self.assertEqual(self.blocked(), [])

    def test_missing_game_or_wrong_runtime_blocks(self):
        self.campaign['cases'].pop()
        self.assertTrue(self.blocked())
        self.campaign['manifest_sha256'] = 'c' * 64
        self.assertTrue(self.blocked())

    def test_corrupt_evidence_blocks(self):
        (self.root / 'frames.json').write_text('[1]')
        self.assertTrue(self.blocked())

    def test_unfocused_measurement_and_missing_warmup_block(self):
        case = next(c for c in self.campaign['cases'] if c['id'] != 'steam-cef')
        case['candidate']['measured'][0]['focused'] = False
        self.assertTrue(self.blocked())
        case['candidate']['measured'][0]['focused'] = True
        case['candidate']['warmups'].pop()
        self.assertTrue(self.blocked())

    def test_repeatable_fps_or_tail_regression_blocks(self):
        case = next(c for c in self.campaign['cases'] if c['id'] != 'steam-cef')
        slower = self.file('slower.json', json.dumps([12] * 3000).encode())
        for run in case['candidate']['measured']:
            run['frame_times'] = slower
        self.assertTrue(self.blocked())

    def test_missing_physical_campaigns_block(self):
        self.assertTrue(promotion.blockers(self.root))

    def test_steam_software_fallback_cannot_qualify(self):
        case = next(c for c in self.campaign['cases'] if c['id'] == 'steam-cef')
        case['gpu_compositing'] = False
        self.assertTrue(self.blocked())

    def test_evidence_cannot_escape_campaign(self):
        self.record['path'] = '../outside'
        self.assertTrue(self.blocked())
