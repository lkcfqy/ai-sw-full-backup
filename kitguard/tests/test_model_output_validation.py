"""Validate actual adapter output boundaries without importing/loading MLX."""

import json
from copy import deepcopy

import pytest

from kitguard.vision import ModelOutputError, _Observation, _parse_json, _Proposal

OBSERVATION = {
    "observed": {"bolt": 2, "nut": 2, "washer": 2, "bracket": 1},
    "issues": [],
    "action": {"kind": "none", "message": "Synthetic parser test", "region": None},
}


@pytest.mark.parametrize(
    "raw",
    [
        'Here is the result: {"observed": {}}',
        "```json\n" + json.dumps(OBSERVATION) + "\n```",
        json.dumps(OBSERVATION) + json.dumps(OBSERVATION),
        json.dumps(OBSERVATION).replace('"bolt": 2', '"bolt": 2, "bolt": 0'),
        json.dumps(OBSERVATION).replace('"bolt": 2', '"bolt": NaN'),
        json.dumps(OBSERVATION).replace('"bolt": 2', '"bolt": Infinity'),
        json.dumps({**OBSERVATION, "decision": "ready"}),
        '"ready"',
        "[]",
    ],
)
def test_observer_json_rejects_ambiguous_or_injected_payload(raw):
    with pytest.raises(ModelOutputError):
        _parse_json(raw, _Observation)


@pytest.mark.parametrize("bad_count", [True, -1, 13, "2", 2.5])
def test_observer_counts_are_not_coerced(bad_count):
    payload = deepcopy(OBSERVATION)
    payload["observed"]["bolt"] = bad_count
    with pytest.raises(ModelOutputError):
        _parse_json(json.dumps(payload), _Observation)


@pytest.mark.parametrize("region", [[0.8, 0.2, 0.3, 0.5], [0.1, 0.2, 1.1, 0.9], [0.0, 0.0, 0.0, 0.0]])
def test_observer_region_must_be_valid_normalized_rectangle(region):
    payload = deepcopy(OBSERVATION)
    payload["action"]["region"] = region
    with pytest.raises(ModelOutputError):
        _parse_json(json.dumps(payload), _Observation)


def test_unobservable_count_requires_an_evidence_or_manual_action():
    payload = deepcopy(OBSERVATION)
    payload["observed"]["bolt"] = None
    with pytest.raises(ModelOutputError):
        _parse_json(json.dumps(payload), _Observation)


def test_excess_observed_quantity_is_legal_evidence_not_an_order_constraint():
    payload = deepcopy(OBSERVATION)
    payload["observed"]["bolt"] = 4
    result = _parse_json(json.dumps(payload), _Observation)
    assert result.observed.bolt == 4


def test_unresolved_revision_proposal_is_explicit():
    result = _parse_json(json.dumps({"requirements": None, "explanation": "Need clarification"}), _Proposal)
    assert result.requirements is None
