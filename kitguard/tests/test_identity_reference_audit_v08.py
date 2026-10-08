"""CPU synthetic replay contracts. No actual candidate ledger reads or model calls."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.v08 import audit_identity_reference_guarded as a
from scripts.v08 import run_identity_reference_guarded as r
from tests.test_identity_reference_guarded_v08 import WORKER

ROOT = Path(__file__).resolve().parents[1]

AUDIT_WORKER = WORKER.replace("except Exception as exc:error=type(exc).__name__",
                            "except Exception as exc:error=f'{type(exc).__name__}: {exc}'")
AUDIT_WORKER = AUDIT_WORKER.replace("candidate=perform(r.observer()", """original_prepare = vision._prepare_image
if scenario == 'reference_prepare_failure':
    def failed_prepare(source, target, size):
        if Path(source).name == 'nut.png': raise OSError('synthetic reference preparation failed')
        return original_prepare(source, target, size)
    vision._prepare_image = failed_prepare
candidate=perform(r.observer()""")
AUDIT_WORKER += r'''
vision._prepare_image = original_prepare
import importlib.util, importlib
spec = importlib.util.spec_from_file_location('new_independent_auditor',sys.argv[4])
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
frozen=SimpleNamespace(vision=vision,schemas=importlib.import_module('kitguard.schemas'),
                      probe=importlib.import_module('scripts.probe_selective_identity'))
row={'observation':candidate['observation'],'error':candidate['error'],
     'observation_diagnostics':candidate['diagnostics'],'observer_status':candidate['status']}
counts,opaque=a.replay(r.observer(),root/'target.png',refs,root/'candidate',row,frozen)
stage=a.stage_contract(candidate['diagnostics'],receipts,base['calls'][0]['images'][0]['sha256'],
                       root/'candidate',candidate['error'] is None)
assert stage == (r.check_reference_stages(d,receipts,root/'candidate',candidate['error'] is None)
                 | r.check_target_stages(d,base['calls'][0]['images'][0]['sha256'],root/'candidate',receipts))
assert counts['actual_model_calls_started'] == sum(c['model_call_started'] for c in candidate['calls'])
assert counts['actual_model_calls_completed'] == sum(c['model_call_completed'] for c in candidate['calls'])
assert not any(x.startswith(('mlx','torch','transformers')) for x in sys.modules)
json.dump({'counts':dict(counts),'opaque':opaque,'stage':stage},open(root/'audit.json','w'))
'''

TAMPER_WORKER = AUDIT_WORKER.replace(
    "counts,opaque=a.replay(r.observer(),root/'target.png',refs,root/'candidate',row,frozen)",
    r'''
call = row['observation_diagnostics']['generation_calls'][2]
if scenario == 'tamper_schema':call['json_schema_sha256']='0'*64
elif scenario == 'tamper_prompt':call['prompt']+=' changed'
elif scenario == 'tamper_roles':call['input_roles'][-1]['counted']=True
elif scenario == 'tamper_reference':
    im=call['images'][-1];path=root/'candidate'/im['path']
    changed=Image.open(path).convert('RGB');changed.putpixel((0,0),(8,7,6));changed.save(path)
    im['sha256']=a.sha(path)
else:raise AssertionError('unknown mutation')
json.dump(call,open(root/'candidate/call-03/generation.json','w'))
try:a.replay(r.observer(),root/'target.png',refs,root/'candidate',row,frozen)
except a.AuditError as error:
    json.dump({'rejected':True,'error':str(error)},open(root/'tamper-audit.json','w'))
    raise SystemExit(0)
raise AssertionError('Consistent mutation unexpectedly accepted')
''')


@pytest.fixture(scope="module")
def source_snapshot(tmp_path_factory):
    folder = tmp_path_factory.mktemp("identity_ref_audit") / "source_snapshot"
    r.prepare_sources(ROOT, folder)
    return folder


@pytest.mark.parametrize("scenario", ["confirmed", "blocked", "disagree", "no_candidates", "first_invalid",
                                      "second_invalid", "identity_invalid", "wrong_id", "missing_id",
                                      "first_load_failure", "identity_load_failure", "identity_generate_failure",
                                      "identity_grammar_failure", "reference_prepare_failure"])
def test_exact_replay_failed_skipped_and_actual_call_boundaries(source_snapshot, tmp_path, scenario):
    result = subprocess.run([sys.executable, "-I", "-c", AUDIT_WORKER, str(source_snapshot), str(tmp_path),
                             scenario, str(Path(a.__file__).resolve())], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    outcome = json.loads((tmp_path / "audit.json").read_text())
    if scenario in {"identity_load_failure", "identity_grammar_failure"}:
        assert outcome["counts"]["calls"] == 3 and outcome["counts"]["actual_model_calls_started"] == 2
    if scenario == "reference_prepare_failure":
        assert outcome["counts"]["calls"] == 2 and outcome["opaque"]


def test_completed_only_before_any_prediction_read(tmp_path):
    (tmp_path / "run.json").write_text('{"status":"running"}')
    with pytest.raises(a.AuditError, match="incomplete"):
        a.completed_metadata(tmp_path)


@pytest.mark.parametrize("scenario", ["tamper_schema", "tamper_prompt", "tamper_roles", "tamper_reference"])
def test_consistent_record_and_file_tampering_rejected(source_snapshot, tmp_path, scenario):
    result = subprocess.run([sys.executable, "-I", "-c", TAMPER_WORKER, str(source_snapshot), str(tmp_path),
                             scenario, str(Path(a.__file__).resolve())], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads((tmp_path / "tamper-audit.json").read_text())["rejected"] is True


@pytest.mark.parametrize("record", [
    {"status": "parsed", "raw_text": "{}", "model_call_started": False, "model_call_completed": False},
    {"status": "failed", "raw_text": "bad", "model_call_started": True, "model_call_completed": False},
    {"status": "failed", "raw_text": None, "model_call_started": False, "model_call_completed": True},
])
def test_stage_record_cannot_claim_impossible_actual_model_flags(record):
    with pytest.raises(a.AuditError):
        a.call_flags(record)


def test_source_snapshot_has_no_blank_database_exception(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/kitguard.sqlite3").write_bytes(b"extra")
    with pytest.raises(a.AuditError, match="runtime DB forbidden"):
        a.snapshot_runtime_files(tmp_path, {})


def test_actual_legacy_runtime_database_remains_outside_snapshot(source_snapshot, tmp_path):
    worker = AUDIT_WORKER + r'''
receipt=a.runtime_database(root,{'runtime_app_data':str(root/'runtime-app-data')})
assert len(receipt['table_rows'])==7 and not any(receipt['table_rows'].values())
assert not (Path(sys.argv[1])/'data').exists()
'''
    result = subprocess.run([sys.executable, "-I", "-c", worker, str(source_snapshot), str(tmp_path),
                             "confirmed", str(Path(a.__file__).resolve())], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_full_denominator_gate_and_actual_call_counts_are_separate():
    from tests.test_reference_guarded_v08 import candidate, items
    dataset = items()
    rows = [candidate(i) for i in dataset[:-1]]
    rows[0].update(error="synthetic failure", observation=None, counts_exact=False, actionable_counts=False)
    rows[0]["observation_diagnostics"] = {"generation_calls": [
        {"model_call_started": False, "model_call_completed": False},
        {"model_call_started": True, "model_call_completed": False}]}
    result = a.summarize(dataset, rows)
    assert sum(result["outcomes"].values()) == 51
    assert result["outcomes"]["E"] == result["outcomes"]["N"] == 1
    assert result["unmeasured_risk"] == 2
    assert result["generation_attempt_records"] == 2
    assert result["model_calls_started"] == 1 and result["model_calls_completed"] == 0
    assert not result["development_gate_count_conditions_passed"]
