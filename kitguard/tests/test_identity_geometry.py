"""The geometry guard must block uncertainty without changing integer counts."""

import copy

import pytest
from pydantic import ValidationError
from test_identity_probe import base_observation

from scripts import probe_identity_geometry as probe


@pytest.mark.parametrize('opening,accepted', [
    ('through_hole', True), ('closed_recess', False),
    ('uncertain', False), ('not_applicable', False),
])
def test_washer_requires_positive_opening_evidence(opening, accepted):
    base = base_observation()
    before = copy.deepcopy(base)
    targets = probe.select_targets(base)
    response = probe.IdentityResponse.model_validate({'objects': [
        {'id': t['id'], 'part': t['original_part'], 'status': 'independent_object',
         'opening': opening, 'issue': ''} for t in targets
    ]})
    result, guard = probe.apply_guard(base, targets, response)
    assert base == before
    assert result['observed']['washer'] == (1 if accepted else None)
    assert result['observed']['nut'] == 1
    assert result['observed']['bolt'] == 1
    assert guard['integer_counts_reassigned'] is False
    assert guard['status'] == ('confirmed_candidates' if accepted else 'blocked')


def test_drive_class_conflict_blocks_both_affected_categories():
    base = base_observation([{'part': 'washer', 'center': [.5, .5]}])
    targets = probe.select_targets(base)
    response = probe.IdentityResponse.model_validate({'objects': [{
        'id': targets[0]['id'], 'part': 'bolt', 'status': 'independent_object',
        'opening': 'closed_recess', 'issue': ''
    }]})
    result, _ = probe.apply_guard(base, targets, response)
    assert result['observed'] == {'bolt': None, 'nut': 0, 'washer': None, 'bracket': 0}
    assert result['action']['kind'] == 'recapture'


@pytest.mark.parametrize('opening', [None, 'looks_like_hole', 1])
def test_missing_or_invalid_geometry_cannot_bypass_gate(opening):
    with pytest.raises(ValidationError):
        probe.IdentityResponse.model_validate({'objects': [{
            'id': 'p001', 'part': 'washer', 'status': 'independent_object',
            'opening': opening, 'issue': ''
        }]})
