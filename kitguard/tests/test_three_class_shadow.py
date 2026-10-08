"""Pure shadow contracts: no Torch, real model, or dataset access."""
import copy
import subprocess
import sys

import pytest

from scripts.v08 import probe_three_class_shadow as m


def base(nut=0, washer=1):
    return {"observed": {"bolt": 1, "nut": nut, "washer": washer, "bracket": 0},
            "issues": [], "action": {"kind": "none"},
            "object_evidence": {"uncertain_parts": [], "objects": [{"part": "washer", "center": [.99, .99]}]}}


def raw(labels=(2,), scores=(.7,), boxes=None):
    return {"labels": list(labels), "scores": list(scores),
            "boxes": boxes or [[10, 10, 20, 20] for _ in labels]}


def test_import_never_loads_torch_pil_or_production():
    result = subprocess.run([sys.executable, '-I', '-c',
                             "import runpy,sys;runpy.run_path(sys.argv[1]);assert not any(x in sys.modules for x in ['torch','PIL','kitguard'])",
                             m.__file__], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_threshold_is_inclusive_and_all_low_boxes_retained_in_raw_summary():
    got = m.summarize(raw((1, 2, 3), (.1, .5, .7)), .5, (100, 100))
    assert got['counts'] == {'bolt': 0, 'nut': 1, 'washer': 1}
    assert len(got['predictions']) == 3 and not got['predictions'][0]['retained']
    assert 'bracket' not in got['counts']


def test_cross_class_same_box_not_suppressed():
    got = m.summarize(raw((2, 3), (.8, .9)), .5, (100, 100))
    assert got['counts']['nut'] == got['counts']['washer'] == 1
    assert got['cross_class_overlaps'] == [{'indices': [0, 1], 'iou': 1, 'both_retained': True}]


def test_conflict_ignores_vlm_point_and_only_nulls_two_counts():
    observation = base()
    before = copy.deepcopy(observation)
    effective, triggers = m.fuse(observation, m.summarize(raw(), .5, (100, 100)))
    assert observation == before
    assert effective['observed'] == {'bolt': 1, 'nut': None, 'washer': None, 'bracket': 0}
    assert effective['object_evidence'] == observation['object_evidence']
    assert triggers[0]['prediction_indices'] == [0]
    assert effective['issues'] == [m.ISSUE]


def test_equal_and_lower_count_do_not_trigger_or_repair():
    observation = base(nut=2, washer=None)
    observation['issues'] = ['existing uncertainty']
    effective, triggers = m.fuse(observation, m.summarize(raw(), .5, (100, 100)))
    assert effective == observation and triggers == []


def test_unknown_is_not_zero_but_other_known_class_can_trigger():
    observation = base(nut=None, washer=0)
    assert not m.fuse(observation, m.summarize(raw(), .5, (100, 100)))[1]
    effective, triggers = m.fuse(observation, m.summarize(raw((3,), (.9,)), .5, (100, 100)))
    assert [t['part'] for t in triggers] == ['washer']
    assert effective['observed']['nut'] is effective['observed']['washer'] is None


@pytest.mark.parametrize('bad', [raw((4,), (.7,)), raw((2,), (float('nan'),)),
                                raw((2,), (.7,), [[-1, 0, 10, 10]]),
                                {'labels': [2], 'scores': [], 'boxes': []},
                                raw((2,), (.7,), [[1, 1, 1, 2]])])
def test_invalid_raw_is_not_silently_dropped(bad):
    with pytest.raises(ValueError):
        m.summarize(bad, .5, (100, 100))


def test_count_equality_does_not_imply_localization_and_no_loco_boxes():
    case = {'ground_truth': {'bolt': 0, 'nut': 1, 'washer': 0, 'bracket': 0}}
    detector = m.summarize(raw(), .5, (100, 100))
    gt = {'available': True, 'objects': [{'label': 2, 'box': [70, 70, 80, 80]}]}
    got = m.detector_metrics(case, detector, gt)
    assert got['exact_count']
    assert got['box_metrics']['per_class']['nut']['fp'] == got['box_metrics']['per_class']['nut']['fn'] == 1
    got = m.detector_metrics(case, detector, {'available': False, 'reason': 'no author boxes'})
    assert got['box_metrics'] is None and not got['box_metrics_available']


def test_oriented_box_crop_scale_tracks_annotation_ids():
    case = {'subgroup': 'screws_author_safe_crop', 'source_image': 'a.png', 'crop_xyxy': [20, 20, 180, 180],
            'bbox_margin_px': 16, 'included_annotation_ids': [1],
            'ground_truth': {'bolt': 0, 'nut': 1, 'washer': 0, 'bracket': 0}}
    annotations = {'images': [{'file_name': 'a.png', 'id': 1, 'width': 200, 'height': 200}],
                   'annotations': [{'id': 1, 'image_id': 1, 'category_id': 7, 'bbox': [100, 100, 40, 20, 0]}]}
    got = m.author_boxes(case, annotations, [200, 200], [80, 80])
    assert got['objects'][0]['box'] == [30, 35, 50, 45]
    case['included_annotation_ids'] = [2]
    with pytest.raises(ValueError, match='Included'):
        m.author_boxes(case, annotations, [200, 200], [80, 80])


def test_full51_denominator_distinguishes_failed_call_from_not_attempted():
    items, records = [], []
    for i in range(51):
        observation = base(nut=1, washer=1)
        case = {'id': str(i), 'ground_truth': observation['observed'], 'subgroup': 'loco_normal_222',
                'supported_positive_classes': ['bolt', 'nut', 'washer']}
        item = {'case': case, 'baseline_attempt': i, 'base_observation': observation,
                'binding': {}, 'baseline_latency_ms': 1000}
        row = m.empty_record(item, i)
        if i < 49:
            row.update(detector_call_started=True, detector_call_completed=True,
                       effective_observation=copy.deepcopy(observation), status='ok')
        elif i == 49:
            row.update(detector_call_started=True, error='model failed', status='failed')
        else:
            row['error'] = 'setup/decode failed before call'
        items.append(item); records.append(row)
    got = m.analyze(items, records)
    assert got['outcomes'] == {'C': 49, 'W': 0, 'U': 0, 'E': 1, 'N': 1}
    assert got['risk_denominator'] == 51 and got['unmeasured_risk'] == 2
    assert not got['development_gate_passed']
    with pytest.raises(ValueError, match='Full51'):
        m.analyze(items, records[:-1])


def test_all_four_false_ready_not_replaced_by_source_supported():
    observation = base(nut=0, washer=1)
    case = {'ground_truth': {'bolt': 1, 'nut': 1, 'washer': 0, 'bracket': 0},
            'supported_positive_classes': ['bolt', 'nut']}
    got = m.panel(case, observation)
    assert got['all_four']['any_false_ready'] and not got['source_supported']['any_false_ready']


def test_canonical_handles_checkpoint_integer_keys_and_tuple_rank():
    assert m.canonical({'classes': {1: 'bolt'}, 'rank': (1, 2)}) == m.canonical({'classes': {'1': 'bolt'}, 'rank': [1, 2]})
