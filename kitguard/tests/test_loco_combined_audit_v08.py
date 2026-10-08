"""Independent scoring/raw-replay CPU contracts. No actual LOCO photo reads."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.v08 import audit_loco_combined as a

ROOT = Path(__file__).resolve().parents[1]


def cases():
    return [{"id": f"case-{i+1:03d}", "source_sha256": f"{i+1:064x}", "ground_truth": dict(zip(a.PARTS, g, strict=True))}
            for i, g in enumerate(g for g in a.GROUPS for _ in range(6))]


def rows(observed=None, state="completed"):
    return [{"case_id": c["id"], "source_sha256": c["source_sha256"], "state": state,
             "observation": {"observed": dict(c["ground_truth"] if observed is None else observed), "issues": [], "action": {"kind": "none"}},
             "error": None} for c in cases()]


def test_true_count4_full_population_and_distinct_order_domain():
    result = a.summarize(cases(), rows())
    assert result["outcomes"] == {"C": 24, "W": 0, "U": 0, "E": 0, "N": 0}
    assert result["matched_order_applicable"] == result["matched_order_not_applicable"] == 12
    assert result["matched_order_correct_ready"] == 12 and result["normal_order_correct_adjustment"] == 24
    assert result["all_four_panel"]["planned_mismatched_orders"] == 6108
    assert result["source_supported_panel"]["planned_mismatched_orders"] == 1500
    assert result["all_four_panel"]["observed_any_false_ready_images"] == 0


def test_constant_normal_and_abstention_have_different_failure_costs():
    normal = a.summarize(cases(), rows(a.NORMAL))
    assert normal["outcomes"]["W"] == normal["all_four_panel"]["observed_any_false_ready_images"] == 24
    unknown = rows(dict.fromkeys(a.PARTS))
    abstain = a.summarize(cases(), unknown)
    assert abstain["outcomes"]["U"] == 24 and abstain["outcomes"]["C"] == 0
    assert abstain["all_four_panel"]["observed_any_false_ready_images"] == 0
    assert abstain["all_four_panel"]["measured_images"] == 24


def test_error_and_not_attempted_remain_unmeasured_risk():
    ledger = rows()
    ledger[0].update(state="error", error="synthetic runtime failure", observation=None)
    ledger[1].update(state="not_attempted", observation=None)
    result = a.summarize(cases(), ledger)
    assert result["outcomes"] == {"C": 22, "W": 0, "U": 0, "E": 1, "N": 1}
    assert result["all_four_panel"]["unmeasured_images"] == 2
    assert result["cases"][0]["all_four_panel"]["any_false_ready"] is None
    assert result["cases"][1]["all_four_panel"]["false_ready_orders"] is None


@pytest.mark.parametrize("mutation", ["duplicate", "wrong_source", "drop_group"])
def test_population_corruption_is_integrity_error_not_wrong_prediction(mutation):
    source, ledger = cases(), rows()
    if mutation == "duplicate":
        ledger.append(copy.deepcopy(ledger[0]))
    elif mutation == "wrong_source":
        ledger[0]["source_sha256"] = "f"*64
    else:
        source.pop()
    with pytest.raises(a.AuditError):
        a.summarize(source, ledger)


def test_unfinished_run_rejected_before_predictions_read(tmp_path):
    (tmp_path / "run.json").write_text(json.dumps({"status": "running"}))
    (tmp_path / "predictions.json").write_text("DO NOT READ")
    with pytest.raises(a.AuditError, match="predictions deliberately unread"):
        a.completed_metadata(tmp_path)


WORKER = r'''
import sys,os,json,copy,importlib.util
from pathlib import Path
from types import SimpleNamespace
root,stage,output,scenario=map(Path,sys.argv[1:5]); scenario=scenario.name
# Load independent module before frozen project modules, with no import of candidate analyze/scorer.
spec=importlib.util.spec_from_file_location('independent_loco',root/'scripts/v08/audit_loco_combined.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
os.environ['KITGUARD_DATA_DIR']=str(output/'runtime-app-data')
frozen=a.H.load_frozen_modules(stage)
from scripts.v08 import run_loco_combined as r
from PIL import Image
output.mkdir(parents=True,exist_ok=True)
image=Image.new('RGB',(160,120),'white');image.putpixel((0,0),(255,0,0));image.save(output/'target.png')
objects=[{'part':'bolt' if i<2 else 'nut','center':[(i+1)/7,.5]} for i in range(6)]
inventory={'objects':objects,'uncertain_parts':[],'issues':[],'action':{'kind':'none','message':'synthetic'}}
identity={'objects':[{'id':f'p{i:03d}','part':o['part'],'status':'independent_object','opening':'through_hole','issue':''} for i,o in enumerate(objects,1) if o['part']=='nut']}
if scenario=='wrong_id':identity['objects'][0]['id']='p999'
texts=[json.dumps(inventory),json.dumps(inventory),json.dumps(identity)]
if scenario=='invalid_json':texts[1]='invalid json'
engine=r.guarded_observer();engine.artifact_dir=output/'case'
index=[0];loads=[0]
def generate(*args,**kwargs):
    n=index[0];index[0]+=1
    if scenario=='runtime_failure' and n==2:raise RuntimeError('synthetic device failure')
    return SimpleNamespace(text=texts[n],prompt_tokens=99,generation_tokens=9,peak_memory=.1,finish_reason='stop')
def load():
    loads[0]+=1
    if scenario=='load_failure' and loads[0]==1:raise RuntimeError('synthetic unavailable device')
    return {'template':lambda *args,**kw:'fixture','processor':object(),'config':{},'grammar':lambda *args:object(),'generate':generate,'model':object()}
engine._load=load
row={'state':'completed','error':None,'observation':None}
try:row['observation']=r.validate_observation(engine.observe(output/'target.png',dict.fromkeys(a.PARTS,1),{}))
except Exception as exc:row.update(state='error',error=f'{type(exc).__name__}: {exc}')
row['observation_diagnostics']=engine.status()['last_observation_attempt'];row['observer_status_after']=engine.status()
expected_failure=False
if scenario=='raw_tamper':
    c=row['observation_diagnostics']['generation_calls'][0];c['raw_text']=c['raw_text'].replace('"nut"','"washer"',1)
    (output/'case/call-01/generation.json').write_text(json.dumps(c))
    expected_failure=True
if scenario=='role_tamper':
    c=row['observation_diagnostics']['generation_calls'][0];c['input_roles'][0]['role']='category_reference'
    (output/'case/call-01/generation.json').write_text(json.dumps(c))
    expected_failure=True
if scenario=='flag_tamper':
    c=row['observation_diagnostics']['generation_calls'][0];c['model_call_completed']=False
    (output/'case/call-01/generation.json').write_text(json.dumps(c))
    expected_failure=True
if scenario=='input_tamper':
    c=row['observation_diagnostics']['generation_calls'][0]
    path=output/'case'/c['images'][0]['path'];path.write_bytes(b'bad bytes')
    expected_failure=True
before=a.A.inventory(output/'case')
try:
    counts,opaque=a.replay(r.guarded_observer(),output/'target.png',output/'case',row,frozen)
    checked=a.check_stages(row['observation_diagnostics'],a.sha(output/'target.png'),output/'case',row['state']=='completed',frozen)
    assert not expected_failure, 'Corruption passed'
    assert counts['actual_model_calls_started']==index[0]
    assert counts['actual_model_calls_completed']==index[0]-(scenario=='runtime_failure')
    assert bool(opaque)==(scenario in {'load_failure','runtime_failure'})
    assert checked['no_reference_inputs']
except a.AuditError:
    assert expected_failure
assert a.A.inventory(output/'case')==before
assert not any(n=='mlx' or n.startswith('mlx.') for n in sys.modules)
assert 'scripts.v08.score_loco_combined' not in sys.modules
assert not (stage/'data').exists()
# Pure mathematical panel matches actual frozen decide for 6 observations *255 BOMs.
from kitguard.app import decide
for observed,issues,kind in [(dict(zip(a.PARTS,[2,4,0,0])),[],'none'),(dict(a.NORMAL),[],'none'),
                           (dict.fromkeys(a.PARTS),[],'none'),(dict(a.NORMAL),['unclear'],'none'),
                           (dict(a.NORMAL),[],'recapture'),(dict(a.NORMAL),[],'manual')]:
    projection={'observed':observed,'issues':issues,'action':{'kind':kind}}
    obs=frozen.schemas.Observation.model_validate({'observed':observed,'issues':issues,'action':{'kind':kind,'message':'fixture'}})
    for counts in __import__('itertools').product(range(4),repeat=4):
        if not any(counts):continue
        requirements=dict(zip(a.PARTS,counts))
        actual=decide({'id':'fixture','revision':1,'requirements':requirements,'checks':[],'photos':[]},obs,'photo',0)['decision']
        assert actual==a.decide(projection,requirements)
'''


@pytest.mark.parametrize("scenario", ["success", "wrong_id", "invalid_json", "load_failure", "runtime_failure",
                                      "raw_tamper", "role_tamper", "flag_tamper", "input_tamper"])
def test_frozen_raw_replay_and_actual_rule_parity(tmp_path, scenario):
    # Use the actual pinned69-file source snapshot, without reading any run/image artifacts.
    stage = ROOT / a.FREEZE_REL
    stage = stage.parent / "source_snapshot"
    result = subprocess.run([sys.executable, "-I", "-c", WORKER, str(ROOT), str(stage), str(tmp_path), scenario],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("code,part,delta,label", [
    (249, "nut", 1, "1_additional_nut"), (248, "nut", 2, "2_additional_nuts"),
    (247, "washer", 1, "1_additional_washer"), (246, "washer", 2, "2_additional_washers"),
    (243, "nut", -1, "1_missing_nut"), (242, "nut", -2, "2_missing_nuts"),
    (241, "washer", -1, "1_missing_washer"), (240, "washer", -2, "2_missing_washers"),
])
def test_all_eight_actual_author_quantity_labels_without_pixel_reads(code, part, delta, label):
    path = ROOT / "datasets/raw/mvtec_loco_ad/screw_bag/defects_config.json"
    assert a.sha(path) == "99d2f93ac25f632d594ec0e4e610d30c157b8f4985cd3bd76828375103bdaacd"
    definitions = {d["pixel_value"]: d["defect_name"] for d in a.read(path)}
    assert definitions[code] == label
    assert a.author_quantity_delta(code, label, definitions) == (part, delta)


@pytest.mark.parametrize("code,label", [(249, "1_additional_nuts"), (248, "2_additional_nut"),
                                       (241, "1_missing_washers"), (240, "2_missing_washer"),
                                       (240, "3_missing_washers"), (240, "2_missing_bolts"),
                                       (100, "2_missing_washers")])
def test_quantity_parser_rejects_wrong_grammar_or_nonregistered_category(code, label):
    with pytest.raises(a.AuditError):
        a.author_quantity_delta(code, label, {code: label})


def test_quantity_parser_rejects_different_author_code_label():
    with pytest.raises(a.AuditError):
        a.author_quantity_delta(249, "1_additional_nut", {249: "1_missing_nut"})
