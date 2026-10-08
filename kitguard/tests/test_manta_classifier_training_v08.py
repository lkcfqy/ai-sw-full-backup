"""Synthetic contracts only: no Torch import, prepared pixels or model execution."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/v08/train_manta_classifier.py'
spec = importlib.util.spec_from_file_location('manta_training_contract', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def population():
    originals, rows, groups = [], [], []
    for label, name in enumerate(m.CLASSES):
        for block in range(16):
            role = 'train' if block < 12 else 'validation'
            group_id = f'{name}-{block}'
            members = []
            for offset in range(32):
                index = label * 512 + block * 32 + offset
                original = {'input_id': f'record-{index:04}', 'class_name': name, 'label': label,
                            'member_path': f'{name}/train/good/{block * 32 + offset + 1:05}.png',
                            'author_split': 'train', 'author_condition': 'good',
                            'initial_role': role, 'previously_exposed': block == 0 and offset < 2,
                            'visual_qa_selected': offset == 15 or (block == 0 and offset < 2)}
                originals.append(original)
                rows.append({**original, 'status': 'prepared', 'error': None, 'role': role,
                             'input_path': f"inputs/{original['input_id']}.png", 'input_sha256': str(index),
                             'input_size': [224, 224], 'source_mode': 'RGB', 'exif': {}, 'view_index': 0,
                             'structural_layout_check': 'passed', 'final_group': group_id})
                members.append(original['input_id'])
            groups.append({'group_id': group_id, 'members': members, 'role': role})
    return rows, originals, {'groups': groups, 'label_conflict_groups': 0}


def layout(rows):
    selected = [r for r in rows if r['visual_qa_selected']]
    sheets = [{'path': f'qa-{i}.png', 'sha256': str(i), 'record_ids': [r['input_id'] for r in selected[i*6:(i+1)*6]]}
              for i in range(6)]
    prepared = {'records_sha256': 'records', 'grouping_sha256': 'groups', 'qa_sheets': sheets}
    review = {'schema': 'kitguard.v08.manta-classifier.visual-review.v1', 'status': 'passed',
              'training_authorized': False, 'reviewer': {'kind': 'AI', 'human_participants': 0},
              'freeze_sha256': m.FREEZE_SHA, 'preparation_sha256': 'prep', 'records_sha256': 'records',
              'grouping_sha256': 'groups', 'sheets': copy.deepcopy(sheets),
              'reviewed_records': [{**{k: r[k] for k in ('input_id', 'member_path', 'role', 'input_sha256')},
                                    'accepted': True} for r in selected]}
    return prepared, review


def test_import_is_metadata_only():
    code = f"import runpy,sys;runpy.run_path({str(SOURCE)!r});assert not any(x in sys.modules for x in ('torch','torchvision','mlx','PIL'))"
    result = subprocess.run([sys.executable, '-I', '-c', code], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(('probabilities', 'expected'), [([.9, .1], 'C'), ([.1, .9], 'W'),
                                                        ([.899999, .100001], 'U'), ([.5, .5], 'U')])
def test_fixed_threshold_without_tolerance(probabilities, expected):
    assert m.score_row({'label': 0}, {'status': 'ok', 'probabilities': probabilities})[0] == expected


@pytest.mark.parametrize('values', [[float('nan'), .5], [True, 0], [.9, .2], [-.1, 1.1], [1]])
def test_invalid_probabilities_are_not_scored(values):
    with pytest.raises(ValueError):
        m.score_row({'label': 0}, {'status': 'ok', 'probabilities': values})


def test_group_macro_and_all_failure_denominators():
    rows = [{'input_id': str(i), 'label': 0 if i < 4 else 1,
             'class_name': 'nut' if i < 4 else 'yellow_green_washer',
             'final_group': 'a' if i < 3 else 'b' if i == 3 else 'c'} for i in range(7)]
    predictions = [{'input_id': str(i), 'status': 'ok', 'probabilities': probs}
                   for i, probs in enumerate([[.9, .1], [.9, .1], [.9, .1], [.1, .9], [.5, .5]])]
    predictions += [{'input_id': '5', 'status': 'failed'}, {'input_id': '6', 'status': 'not_attempted'}]
    got = m.summarize(rows, predictions)
    assert got['threshold_0_9']['CWUEN'] == {'C': 3, 'W': 1, 'U': 1, 'E': 1, 'N': 1}
    nut = got['threshold_0_9']['classes']['nut']
    assert nut['group_macro_correct_coverage'] == .5
    assert nut['record_correct_coverage'] == .75
    assert got['forced_argmax']['CWUEN'] == {'C': 3, 'W': 2, 'U': 0, 'E': 1, 'N': 1}
    assert got['constant_identity_baselines']['nut'] == {'C': 4, 'W': 3, 'U': 0, 'E': 0, 'N': 0}
    assert not got['continuation_gate'] and not got['production_promotion']
    with pytest.raises(ValueError):
        m.summarize(rows, predictions[::-1])


def test_complete_population_and_layout_accepted():
    rows, originals, groups = population()
    m.validate_population(rows, originals, groups)
    prepared, review = layout(rows)
    m.validate_layout(prepared, 'prep', rows, review)


@pytest.mark.parametrize('change', ['missing', 'failed', 'exposure', 'test', 'label', 'neutral_path', 'group_split', 'small_partition', 'conflict'])
def test_population_fail_closed(change):
    rows, originals, groups = population()
    if change == 'missing':
        rows.pop()
    elif change == 'failed':
        rows[0]['status'] = 'failed'
    elif change == 'exposure':
        rows[0]['role'] = 'validation'
    elif change == 'test':
        rows[0]['author_split'] = 'test'
    elif change == 'label':
        rows[0]['label'] = 1
    elif change == 'neutral_path':
        rows[0]['input_path'] = 'nut.png'
    elif change == 'group_split':
        groups['groups'][1]['role'] = 'validation'
    elif change == 'small_partition':
        for r in rows:
            if r['class_name'] == 'nut' and r['role'] == 'validation':
                r['role'] = 'train'
        for g in groups['groups']:
            if g['group_id'].startswith('nut-'):
                g['role'] = 'train'
    else:
        groups['label_conflict_groups'] = 1
    with pytest.raises(ValueError):
        m.validate_population(rows, originals, groups)


@pytest.mark.parametrize('change', ['missing', 'reject', 'authorized', 'role', 'binding', 'sheet'])
def test_layout_is_bound_and_never_training_approval(change):
    rows, _, _ = population()
    prepared, review = layout(rows)
    if change == 'missing':
        review['reviewed_records'].pop()
    elif change == 'reject':
        review['reviewed_records'][0]['accepted'] = False
    elif change == 'authorized':
        review['training_authorized'] = True
    elif change == 'role':
        review['reviewed_records'][0]['role'] = 'validation'
    elif change == 'binding':
        review['preparation_sha256'] = 'different'
    else:
        review['sheets'][0]['record_ids'][0] = 'other'
    with pytest.raises(ValueError):
        m.validate_layout(prepared, 'prep', rows, review)


def approval_files(tmp_path):
    plan = {'schema': 'kitguard.v08.manta-classifier.training-plan.v1', 'status': 'prepared_not_authorized', 'preparation_sha256': 'prep',
            'visual_review_sha256': 'visual', 'source_snapshot': {m.SCRIPT: 'source', m.TEST: 'test-source'},
            'config': m.CONFIG, 'classes': m.CLASSES, 'freeze_sha256': m.FREEZE_SHA}
    path = tmp_path / 'plan.json'
    m.write_new(path, plan)
    approval = {'schema': 'kitguard.v08.manta-classifier.training-approval.v1', 'status': 'approved',
                'authorized_by': 'root', 'plan_sha256': m.sha(path), 'freeze_sha256': m.FREEZE_SHA,
                'preparation_sha256': 'prep', 'visual_review_sha256': 'visual',
                'training_source_sha256': 'source', 'epochs': 10, 'production_change': False}
    apath = tmp_path / 'approval.json'
    m.write_new(apath, approval)
    return path, apath, plan, approval


def test_separate_approval_and_no_overwrite(tmp_path):
    path, apath, plan, approval = approval_files(tmp_path)
    assert m.validate_approval(path, m.sha(path), apath, m.sha(apath)) == plan
    with pytest.raises(FileExistsError):
        m.write_new(apath, approval)
    approval['training_source_sha256'] = 'another-source'
    changed = tmp_path / 'other-approval.json'
    m.write_new(changed, approval)
    with pytest.raises(ValueError):
        m.validate_approval(path, m.sha(path), changed, m.sha(changed))


def test_setup_failure_preserves_full_final_denominator_without_model(tmp_path, monkeypatch):
    path, apath, plan, _ = approval_files(tmp_path)
    rows, _, _ = population()
    plan['records'] = rows
    monkeypatch.setattr(m, 'validate_approval', lambda *args: plan)
    def fail(*_):
        raise ValueError('synthetic input SHA mismatch')
    monkeypatch.setattr(m, 'verify_plan', fail)
    before = 'torch' in sys.modules
    output = tmp_path / 'run'
    result = m.train(path, m.sha(path), apath, m.sha(apath), output)
    assert ('torch' in sys.modules) == before
    assert result['status'] == 'failed_integrity' and result['failure_stage'] == 'preflight'
    assert not result['model_initialization_started'] and result['epochs_completed'] == 0
    assert m.read(output / 'analysis.json')['threshold_0_9']['CWUEN'] == {'C': 0, 'W': 0, 'U': 0, 'E': 0, 'N': 256}
    assert len(m.read(output / 'final_predictions.json')) == 256
    assert m.read(output / 'history.json') == []
    assert m.sha(output / 'plan.json') == m.sha(path)
    assert m.read(output / 'run.json') == result


@pytest.mark.parametrize('interrupt', [False, True])
def test_validation_error_and_interrupt_preserve_rows(tmp_path, monkeypatch, interrupt):
    rows, _, _ = population()
    selected = rows[:35]
    fake_tensor = SimpleNamespace(to=lambda _: object())
    fake_torch = SimpleNamespace(stack=lambda _: fake_tensor, mps=SimpleNamespace(synchronize=lambda: None),
                                 inference_mode=nullcontext)
    monkeypatch.setitem(sys.modules, 'torch', fake_torch)
    monkeypatch.setattr(m, 'input_tensor', lambda *_: object())
    class FailureModel:
        def __init__(self):
            self.calls = 0
        def eval(self):
            pass
        def __call__(self, _):
            self.calls += 1
            if interrupt:
                raise KeyboardInterrupt('synthetic interruption')
            raise ValueError('synthetic model failure')
    model = FailureModel()
    output = tmp_path / 'raw.jsonl'
    predictions, interruption = m.evaluate(model, selected, tmp_path, 'mps', {}, output)
    assert model.calls == (1 if interrupt else 2)
    assert sum(p['status'] == 'failed' for p in predictions) == (32 if interrupt else 35)
    assert sum(p['status'] == 'not_attempted' for p in predictions) == (3 if interrupt else 0)
    assert isinstance(interruption, KeyboardInterrupt) if interrupt else interruption is None
    assert [json.loads(line) for line in output.read_text().splitlines()] == predictions
    assert all(p['label'] == r['label'] and p['final_group'] == r['final_group']
               for p, r in zip(predictions, selected, strict=True))


def test_safe_path_rejects_symlink_and_parent_escape(tmp_path):
    (tmp_path / 'input.txt').write_text('synthetic')
    (tmp_path / 'alias.txt').symlink_to(tmp_path / 'input.txt')
    assert m.safe_path(tmp_path, 'input.txt') == tmp_path / 'input.txt'
    for path in ('../input.txt', 'alias.txt', str(tmp_path / 'input.txt')):
        with pytest.raises(ValueError):
            m.safe_path(tmp_path, path)
