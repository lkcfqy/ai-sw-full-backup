"""Synthetic saved-output contracts; no image pixels, torch or producer imports."""
from __future__ import annotations

import copy
import importlib.util
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('independent_transfer', ROOT/'scripts/v08/audit_manta_transfer.py')
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def record(index=0, label='nut', *, tiny=False, clipped=False):
    box = [0, 0, 10 if tiny else 20, 20]
    return {'index': index, 'input_id': f'roi-{index:04}', 'source_id': f'source-{index}',
                'annotation_id': index, 'source_group': 'synthetic', 'source_sha256': 'a'*64,
                'image_index': index, 'image_size': [100, 100], 'aabb_xyxy': box,
                'crop_xyxy': box, 'integer_crop_clamped': False, 'short_side': min(box[2:]),
                'tiny': tiny, 'author_aabb_clipped': clipped, 'expected_identity': label,
                'class_index': {'nut': 0, 'washer': 1, 'bolt': None}[label],
                'score_role': 'open_category_bolt' if label == 'bolt' else 'nut_washer_identity',
                'input_sha256': 'b'*64}


def prediction(row, p=.95):
    return {**{key: row[key] for key in ('source_id', 'expected_identity', 'class_index', 'source_group', 'tiny', 'author_aabb_clipped')},
            'input_id': row['input_id'], 'input_sha256': row['input_sha256'], 'status': 'ok',
                'logits': [math.log(p), math.log(1-p)], 'probabilities': [p, 1-p], 'error': None,
                'actual_forward_started': True, 'actual_forward_returned': True,
                'model_output_class': 'nut' if p >= .5 else 'yellow_green_washer',
                'threshold_result': 'accepted' if max(p, 1-p) >= .9 else 'U'}


@pytest.mark.parametrize(('p', 'expected'), [(.9, 'C'), (.9-1e-12, 'U'), (.95, 'C'), (.05, 'W'), (.5, 'U')])
def test_exact_threshold_and_direction(p, expected):
    row = record()
    assert AUDIT.result_code(row, prediction(row, p)) == expected


def test_tie_argmax_fixed_to_first_class():
    row = record(label='washer')
    assert AUDIT.result_code(row, prediction(row, .5), forced=True) == 'W'


def test_bolt_never_in_binary_wrong_denominator():
    rows = [record(0, 'nut'), record(1, 'washer'), record(2, 'bolt')]
    result = AUDIT.independent_score(rows, [prediction(r) for r in rows], full=False)
    assert result['threshold_0_9']['identity']['counts'] == {'C': 1, 'W': 1, 'U': 0, 'E': 0, 'N': 0}
    assert result['threshold_0_9']['bolt']['counts'] == {'accepted_nut': 1, 'accepted_washer': 0, 'U': 0, 'E': 0, 'N': 0}
    assert result['class_macro_correct_coverage'] == .5


def test_failure_and_unattempted_kept_even_with_partial_output():
    rows = [record(0, 'nut'), record(1, 'washer'), record(2, 'bolt')]
    preds = [prediction(r) for r in rows]
    preds[0].update(status='failed', error={'type': 'SyntheticFailure'})
    preds[1].update(status='not_attempted', logits=None, probabilities=None,
                    actual_forward_started=False, actual_forward_returned=False)
    preds[2].update(status='failed', error={'type': 'SyntheticFailure'})
    result = AUDIT.independent_score(rows, preds, full=False)
    assert result['threshold_0_9']['identity']['counts'] == {'C': 0, 'W': 0, 'U': 0, 'E': 1, 'N': 1}
    assert result['forced_argmax']['identity']['counts'] == {'C': 0, 'W': 0, 'U': 0, 'E': 1, 'N': 1}
    assert result['threshold_0_9']['bolt']['evaluated_fraction'] == 0
    assert result['threshold_0_9']['bolt']['counts']['E'] == 1
    assert result['analytic_baselines']['constant_nut']['identity']['counts']['E'] == 0


def test_unknown_clipped_separate_from_false_and_no_identity_for_empty_cell():
    rows = [record(0, 'washer', tiny=True, clipped=None), record(1, 'bolt', clipped=False)]
    result = AUDIT.independent_score(rows, [prediction(r) for r in rows], full=False)
    assert set(result['slices']['author_clipped']) == {'null', 'false'}
    assert result['slices']['author_clipped']['false']['identity']['correct_coverage'] is None
    assert result['slices']['author_clipped']['null']['identity']['denominator'] == 1


@pytest.mark.parametrize('change', ['nan', 'probabilities', 'order', 'input_sha', 'completed', 'class_name', 'missing', 'duplicate'])
def test_saved_evidence_tampering_rejected(change):
    rows = [record(0), record(1, 'washer')]
    preds = [prediction(r) for r in rows]
    if change == 'nan':
        preds[0]['logits'][0] = float('nan')
    elif change == 'probabilities':
        preds[0]['probabilities'] = [.5, .5]
    elif change == 'order':
        preds.reverse()
    elif change == 'input_sha':
        preds[0]['input_sha256'] = 'c'*64
    elif change == 'completed':
        preds[0]['actual_forward_started'] = False
    elif change == 'class_name':
        preds[1]['model_output_class'] = 'washer'
    elif change == 'missing':
        preds.pop()
    else:
        rows[1]['source_id'] = rows[0]['source_id']
        rows[1]['annotation_id'] = rows[0]['annotation_id']
    with pytest.raises(ValueError):
        AUDIT.independent_score(rows, preds, full=False)


def test_all_579_metadata_denominators_with_synthetic_outputs():
    path = ROOT/'datasets/manifests/v0.8/manta_transfer_candidate_v1/metadata.json'
    assert AUDIT.sha(path) == AUDIT.METADATA_SHA
    rows = copy.deepcopy(AUDIT.read(path)['records'])
    for row in rows:
        row['input_sha256'] = 'b'*64
    result = AUDIT.independent_score(rows, [prediction(r) for r in rows])
    assert result['threshold_0_9']['identity']['counts'] == {'C': 168, 'W': 12, 'U': 0, 'E': 0, 'N': 0}
    assert result['threshold_0_9']['bolt']['counts']['accepted_nut'] == 399
    assert result['class_macro_correct_coverage'] == .5
    assert result['source_class_macro_correct_coverage'] == pytest.approx(2/3)
    assert result['analytic_baselines']['all_unknown']['identity']['counts']['U'] == 180


def test_metadata_tiny_boundary_and_denominator_not_relaxed():
    row = record()
    row.update(aabb_xyxy=[0, 0, 16, 20], crop_xyxy=[0, 0, 16, 20], short_side=16)
    AUDIT.check_record_metadata([row], full=False)
    row['tiny'] = True
    with pytest.raises(ValueError, match='Tiny'):
        AUDIT.check_record_metadata([row], full=False)
    row['tiny'] = False
    with pytest.raises(ValueError, match='579'):
        AUDIT.check_record_metadata([row])


def test_import_does_not_load_models_or_images():
    # Test process may have preloaded plugins; this module has no such imports.
    source = Path(SPEC.origin).read_text()
    assert 'import torch' not in source and 'from PIL' not in source
    assert not any(name.startswith('mlx') for name in sys.modules)


def test_call_counts_are_batches_not_roi_count_and_timings_not_duplicated():
    rows = [record(i) for i in range(579)]
    preds = [prediction(r) for r in rows]
    batches = []
    for index, start in enumerate(range(0, 579, 32)):
        batches.append({'index': index, 'input_ids': [r['input_id'] for r in rows[start:start+32]],
                        'status': 'completed', 'actual_forward_started': True, 'actual_forward_returned': True,
                        'wall_seconds': 2, 'model_seconds': 1, 'decode_tensor_seconds': .5})
        for pred in preds[start:start+32]:
            pred['batch_index'] = index
    run = {'status': 'completed', 'actual_forward_calls_started': 19, 'actual_forward_calls_returned': 19,
           'timing': {'model_seconds': 19, 'decode_tensor_seconds': 9.5}}
    AUDIT.check_batches(rows, preds, batches, run)
    run['actual_forward_calls_started'] = 579
    with pytest.raises(ValueError, match='Actual call total'):
        AUDIT.check_batches(rows, preds, batches, run)
    run['actual_forward_calls_started'] = 19
    run['timing']['model_seconds'] = 579
    with pytest.raises(ValueError, match='timing total'):
        AUDIT.check_batches(rows, preds, batches, run)


def test_terminal_gate_precedes_any_prediction_or_plan_read(tmp_path):
    import json
    run = {'schema': 'kitguard.v08.manta-transfer.inference-run.v1', 'status': 'running', 'final_integrity_passed': True}
    (tmp_path/'run.json').write_text(json.dumps(run))
    with pytest.raises(ValueError, match='Nonterminal'):
        AUDIT.audit(tmp_path, tmp_path/'NONEXISTENT-plan', 'a'*64, tmp_path/'NONEXISTENT-approval', 'b'*64)


def test_native_output_name_and_threshold_trace_both_verified():
    row = record(label='washer')
    pred = prediction(row, .4)
    AUDIT.validate_raw([row], [pred])
    assert pred['model_output_class'] == 'yellow_green_washer' and pred['threshold_result'] == 'U'
    pred['threshold_result'] = 'accepted'
    with pytest.raises(ValueError, match='threshold answer'):
        AUDIT.validate_raw([row], [pred])


def test_empty_cross_cells_are_explicit_and_keep_unknown_clip():
    rows = [record(0, 'nut'), record(1, 'washer', clipped=None)]
    keys = AUDIT.expected_group_keys(rows, ['synthetic', 'empty_source'])
    assert keys['source_group=empty_source|identity=nut'] == []
    assert keys['source_group=empty_source|identity=washer|tiny=lt16|author_clipped=unknown'] == []
    assert keys['source_group=synthetic|identity=washer|tiny=ge16|author_clipped=unknown'] == [1]


def test_raw_truth_identity_cannot_override_frozen_join():
    row = record()
    pred = prediction(row)
    pred['expected_identity'] = 'washer'
    with pytest.raises(ValueError, match='Raw metadata'):
        AUDIT.validate_raw([row], [pred])
