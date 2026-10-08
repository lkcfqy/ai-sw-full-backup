"""Replay saved development results through the integrated contract, without MLX."""

import copy
import json
from pathlib import Path

import pytest

from kitguard.identity import IdentityResponse
from kitguard.schemas import Observation
from kitguard.spatial import SpatialInventory
from kitguard.vision import LocalVision

ROOT = Path(__file__).resolve().parents[1]
RUNS = ['v03_screws_identity_geometry_v2', 'v03_loco_identity_geometry_v2']


def saved_rows(name):
    return [json.loads(line) for line in (ROOT/'evaluation-runs'/name/'predictions.jsonl').read_text().splitlines()]


def integrated(row):
    value = copy.deepcopy(row['observation'])
    value['verification'] = row['base_observation']['verification']
    if row['model_called']:
        value['identity_verification'] = {
            'protocol': 'identity_geometry_v2', 'same_model_correlated_calls': True,
            'response': row['identity_response'],
            'blocked_categories': row['experimental_identity_guard']['blocked_categories'],
            'source_sha256': row['normalized_input_sha256'],
            'full_input_sha256': row['inputs'][0]['sha256'], 'crops': row['crops'],
        }
    return value


@pytest.mark.parametrize('run', RUNS)
def test_all_saved_development_observations_preserve_results(run):
    for row in saved_rows(run):
        validated = Observation.model_validate(integrated(row))
        assert validated.observed.model_dump() == row['observation']['observed']
        assert validated.verification.passes[0].objects


@pytest.mark.parametrize('mutation', ['restore_count', 'hide_block', 'fake_crop', 'wrong_full_hash',
                                      'wrong_crop_source', 'hide_action', 'remove_passes'])
def test_response_cannot_forge_count_or_evidence(mutation):
    data = integrated(saved_rows(RUNS[0])[-1])
    review = data['identity_verification']
    if mutation == 'restore_count':
        data['observed'] = data['verification']['passes'][0]['observed']
    elif mutation == 'hide_block':
        review['blocked_categories'] = []
    elif mutation == 'fake_crop':
        review['crops'][0]['center'] = [0.7, 0.7]
    elif mutation == 'wrong_full_hash':
        review['full_input_sha256'] = '0' * 64
    elif mutation == 'wrong_crop_source':
        review['crops'][0]['source_sha256'] = '0' * 64
    elif mutation == 'hide_action':
        data['issues'] = []
        data['action']['kind'] = 'none'
    elif mutation == 'remove_passes':
        data.pop('verification')
    with pytest.raises(ValueError):
        Observation.model_validate(data)


@pytest.mark.parametrize('index', [0, 1, 3, 11])
def test_full_cpu_adapter_replay_uses_same_inputs_prompt_and_guard(index):
    row = saved_rows(RUNS[0])[index]
    passes = row['base_observation']['verification']['passes']
    responses = [SpatialInventory.model_validate({
        'objects': p['objects'], 'uncertain_parts': p['uncertain_parts'],
        'issues': p['issues'], 'action': {'kind': p['action']['kind'], 'message': p['action']['message']},
    }) for p in passes]
    if row['model_called']:
        responses.append(IdentityResponse.model_validate(row['identity_response']))
    calls = []
    engine = LocalVision(observation_mode='spatial_guarded', image_max_side=1536)

    def generate(system, prompt, images, schema, *, max_tokens):
        calls.append({'prompt': prompt, 'images': images, 'max_tokens': max_tokens})
        engine._last_inference = {'seconds': 0.001}
        return responses[len(calls)-1]

    engine._generate = generate
    source = ROOT/'evaluation-runs/v03_screws_development_v1/normalized_inputs'/f'{index+1:03d}.jpg'
    if (ROOT / 'SOURCE_MANIFEST.json').is_file() and not source.is_file():
        pytest.skip('Source-only distribution excludes photographs; restore the declared development inputs')
    result = engine.observe(source, {'bolt': 1, 'nut': 0, 'washer': 0, 'bracket': 0}, {})
    validated = Observation.model_validate(result)
    assert validated.observed.model_dump() == row['observation']['observed']
    assert len(calls) == (3 if row['model_called'] else 2)
    if row['model_called']:
        assert calls[-1]['prompt'] == row['prompt']
        assert calls[-1]['max_tokens'] == 1800
        assert [c.crop_sha256 for c in validated.identity_verification.crops] == [c['crop_sha256'] for c in row['crops']]
