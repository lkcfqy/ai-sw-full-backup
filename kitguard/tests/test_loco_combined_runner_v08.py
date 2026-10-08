"""Synthetic CPU contracts only; never decode any LOCO24 source or call a model."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.v08 import run_loco_combined as r

ROOT = Path(__file__).resolve().parents[1]


def cases():
    return [{"id": f"case-{i+1:03d}", "source_sha256": f"{i+1:064x}",
             "ground_truth": dict(zip(r.PARTS, group, strict=True))}
            for i, group in enumerate(g for g in r.GROUPS for _ in range(6))]


def selection(include=False):
    return {"schema": "kitguard.v08.loco-combined-method-selection.v1", "status": "approved_for_freeze",
            "approved_by": "root_agent", "methods": [r.G, r.I] if include else [r.G],
            "identity_decision": {"include": include, "role": "failed_candidate_comparison" if include else "excluded", "reason": "Synthetic decision"},
            "no_loco24_model_results_used": True, "exposure_since_source_preflight": []}


@pytest.mark.parametrize("include", [False, True])
def test_selection_explicit_and_method_list_consistent(include):
    data = selection(include)
    assert r.validate_selection_payload(data) == data["methods"]
    data["methods"] = [r.G] if include else [r.G, r.I]
    with pytest.raises(ValueError, match="Methods differ"):
        r.validate_selection_payload(data)


@pytest.mark.parametrize("change", [{"status": "draft_pending_selection"}, {"approved_by": "human"},
                                    {"no_loco24_model_results_used": False}, {"exposure_since_source_preflight": None}])
def test_pending_or_missing_selection_fails_closed(change):
    with pytest.raises(ValueError):
        r.validate_selection_payload(selection() | change)


def test_24_or_48_materialized_before_attempt_balanced_order():
    single, paired = r.materialize_rows(cases(), [r.G]), r.materialize_rows(cases(), [r.G, r.I])
    assert len(single) == 24 and len(paired) == 48
    assert all(x["state"] == "not_attempted" and x["observation"] is None for x in paired)
    assert sum(x["within_case_position"] == 1 and x["mode"] == r.G for x in paired) == 12
    assert sum(x["within_case_position"] == 1 and x["mode"] == r.I for x in paired) == 12
    assert [x["mode"] for x in paired[:4]] == [r.G, r.I, r.I, r.G]


def test_full_denominator_panels_comparators_and_unmeasured_failure():
    rows = r.materialize_rows(cases(), [r.G, r.I])
    rows[0].update(state="error", error="synthetic load failure", latency_ms=5)
    result = r.analyze(cases(), rows, [r.G, r.I], "0"*64, {"records": {}})
    assert result["methods"][r.G]["outcomes"] == {"C": 0, "W": 0, "U": 0, "E": 1, "N": 23}
    assert result["methods"][r.G]["all_four_panel"]["unmeasured_images"] == 24
    assert result["methods"][r.G]["all_four_panel"]["planned_mismatched_orders"] == 6108
    assert result["methods"][r.G]["source_supported_panel"]["planned_mismatched_orders"] == 1500
    controls = result["analytical_comparators_not_model_calls"]
    assert controls["constant_normal"]["outcomes"]["W"] == 24
    assert controls["constant_normal"]["all_four_panel"]["observed_any_false_ready_images"] == 24
    assert controls["always_abstain"]["outcomes"]["U"] == 24
    assert result["model_calls_started"] == 0
    rows[1]["source_sha256"] = "f"*64
    with pytest.raises(ValueError, match="unplanned"):
        r.analyze(cases(), rows, [r.G, r.I], "0"*64, {"records": {}})


def metadata_fixture():
    deltas = [{"part": part, "delta": delta, "pixel_value": code, "defect_name": name,
               "mask": f"m/{n}.png", "mask_sha256": str(n)*64}
              for n, (part, delta, code, name) in enumerate([
                  ("nut", 2, 248, "2_additional_nuts"), ("washer", -2, 240, "2_missing_washers")], 1)]
    record = {"source_id": "synthetic", "source_path": "synthetic.png", "source_sha256": "a"*64,
              "actual_mask_count": 2, "deltas": deltas, "other_registered_defects": [],
              "proposed_author_derived_counts_not_frozen": dict(zip(r.PARTS, [2, 4, 0, 0], strict=True)),
              "within_order_scope_0_to_3": False}
    author = {"id": "synthetic", "path": "synthetic.png", "sha256": "a"*64,
              "label_status": "unresolved", "kitguard_counts": None,
              "source_masks": [{"path": d["mask"], "sha256": d["mask_sha256"],
                                "pixel_values": [d["pixel_value"]], "defect_names": [d["defect_name"]]} for d in deltas]}
    return record, author, {248: "2_additional_nuts", 240: "2_missing_washers"}


def test_author_distinct_category_delta_count4_preserved():
    record, author, defects = metadata_fixture()
    assert r.quantity_truth(record, author, defects) == {"bolt": 2, "nut": 4, "washer": 0, "bracket": 0}
    assert author["kitguard_counts"] is None


@pytest.mark.parametrize("mutate", [lambda x: x[0]["deltas"][1].update(part="nut"),
                                    lambda x: x[0]["proposed_author_derived_counts_not_frozen"].update(nut=3),
                                    lambda x: x[1]["source_masks"][0].update(pixel_values=[248, 249]),
                                    lambda x: x[0].update(other_registered_defects=["scratch"])])
def test_changed_or_ambiguous_quantity_metadata_rejected(mutate):
    fixture = metadata_fixture()
    mutate(fixture)
    with pytest.raises(ValueError):
        r.quantity_truth(*fixture)


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    stage = tmp_path_factory.mktemp("loco_synthetic") / "source_snapshot"
    hashes = r.prepare_sources(ROOT, stage)
    assert hashes["kitguard/vision.py"] == r.read(ROOT / r.I_FREEZE)["source_hashes"]["kitguard/vision.py"]
    assert "data/kitguard.sqlite3" not in hashes
    return stage


WORKER = r'''
import sys, os, json, copy
from pathlib import Path
from types import SimpleNamespace
stage, output, scenario = sys.argv[1:4]
sys.path.insert(0,stage)
root=Path(output); root.mkdir(parents=True,exist_ok=True)
os.environ['KITGUARD_DATA_DIR']=str(root/'runtime-app-data')
from PIL import Image
from kitguard import vision
from kitguard.schemas import Observation
from kitguard.app import decide
from scripts.v08 import run_loco_combined as r
from scripts.v08 import run_identity_reference_guarded as identity
for name,color in [('target','white'),('nut','red'),('washer','blue')]:
    image=Image.new('RGB',(200,160),color);image.putpixel((0,0),(0,255,0));image.save(root/(name+'.png'))
objects=[{'part':'nut','center':[.3,.5]},{'part':'washer','center':[.7,.5]}]
if scenario=='count4':objects=[{'part':'bolt' if i<2 else 'nut','center':[(i+1)/7,.5]} for i in range(6)]
spatial={'objects':objects,'uncertain_parts':[],'issues':[],'action':{'kind':'none','message':'fixture'}}
ident={'objects':[{'id':'p001','part':'nut','status':'independent_object','opening':'through_hole','issue':''},
                  {'id':'p002','part':'washer','status':'independent_object','opening':'through_hole','issue':''}]}
if scenario=='count4':ident={'objects':[{'id':f'p{i:03d}','part':o['part'],'status':'independent_object','opening':'through_hole','issue':''} for i,o in enumerate(objects,1) if o['part']=='nut']}
texts=[json.dumps(spatial),json.dumps(spatial),json.dumps(ident)]
if scenario=='invalid_json':texts[1]='not json'
if scenario=='wrong_id':texts[2]=texts[2].replace('p001','p999')
results={}
for mode in [r.G,r.I]:
    engine=r.guarded_observer() if mode==r.G else identity.observer()
    engine.artifact_dir=root/mode
    calls=[0];loads=[0]
    def generate(*args,**kwargs):
        index=calls[0];calls[0]+=1
        if scenario=='generate_failure' and index==2:raise RuntimeError('synthetic generate failure')
        return SimpleNamespace(text=texts[index],prompt_tokens=100,generation_tokens=20,peak_memory=.1,finish_reason='stop')
    def load():
        loads[0]+=1
        if scenario=='load_failure' and loads[0]==1:raise RuntimeError('synthetic load failure')
        return {'template':lambda *a,**kw:'fixture','processor':object(),'config':{},'grammar':lambda *a:object(),'generate':generate,'model':object()}
    engine._load=load
    observed=error=None
    refs={p:root/(p+'.png') for p in ('nut','washer')} if mode==r.I else {}
    try:
        observed=r.validate_observation(engine.observe(root/'target.png',dict.fromkeys(r.PARTS,1),refs))
    except Exception as exc:error=type(exc).__name__
    diag=engine.status()['last_observation_attempt']
    target=r.sha(root/'target.png')
    receipts={p:{'prepared_sha256':r.sha(root/(p+'.png'))} for p in ('nut','washer')}
    contract=r.stage_contract(mode,diag,target,root/mode,receipts,error is None)
    assert sum(c['model_call_started'] for c in diag['generation_calls'])==calls[0]
    assert sum(c['model_call_completed'] for c in diag['generation_calls'])==calls[0]-(scenario=='generate_failure')
    results[mode]={'observed':observed,'error':error,'calls':diag['generation_calls'],'contract':contract}
assert results[r.G]['error']==results[r.I]['error']
for a,b in zip(results[r.G]['calls'][:2],results[r.I]['calls'][:2],strict=True):
    for key in ('system','prompt','images','schema','json_schema_sha256','max_tokens'):
        assert a[key]==b[key]
# Complete schema accepts observed four; BOM remains <=3 and a mismatch is correct.
value={'observed':dict(zip(r.PARTS,[2,4,0,0])),'issues':[],'action':{'kind':'none','message':'fixture'}}
observation=Observation.model_validate(r.validate_observation(value))
assert decide({'id':'synthetic','revision':1,'requirements':dict(zip(r.PARTS,[2,3,0,0])),'checks':[]},observation,'photo',0)['decision']=='correct'
invalid=copy.deepcopy(value);invalid['action']['message']='x'*2001
try:r.validate_observation(invalid)
except Exception:pass
else:raise AssertionError('complete schema must reject projection-valid but invalid action')
assert not any(n=='mlx' or n.startswith('mlx.') for n in sys.modules)
assert not (Path(stage)/'data').exists()
json.dump(results,open(root/'result.json','w'))
'''


@pytest.mark.parametrize("scenario", ["success", "count4", "invalid_json", "wrong_id", "load_failure", "generate_failure"])
def test_actual_frozen_observer_stages_full_schema_and_call_flags(snapshot, tmp_path, scenario):
    done = subprocess.run([sys.executable, "-I", "-c", WORKER, str(snapshot), str(tmp_path), scenario], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    result = json.loads((tmp_path / "result.json").read_text())
    assert bool(result[r.G]["error"]) == (scenario not in {"success", "count4"})
    if scenario in {"success", "count4"}:
        assert len(result[r.G]["calls"][2]["images"]) == (5 if scenario == "count4" else 3)
        assert len(result[r.I]["calls"][2]["images"]) == (7 if scenario == "count4" else 5)
        old, new = copy.deepcopy(result[r.G]["observed"]), copy.deepcopy(result[r.I]["observed"])
        old.pop("latency_ms"); new.pop("latency_ms")
        assert old == new

RUN_WORKER = r'''
import sys, json
from pathlib import Path
from types import SimpleNamespace
stage, project, scenario = map(str,sys.argv[1:4])
sys.path.insert(0,stage)
from scripts.v08 import run_loco_combined as r
root=Path(project); root.mkdir(parents=True,exist_ok=True)
r.write(root/r.I_FREEZE,{})
cases=[{'id':f'case-{i+1:03d}','source_sha256':f'{i+1:064x}',
        'ground_truth':dict(zip(r.PARTS,g))} for i,g in enumerate(g for g in r.GROUPS for _ in range(6))]
inputs=[]
for c in cases:
    path=root/(c['id']+'.jpg');path.write_bytes(b'synthetic input never decoded')
    inputs.append({'case_id':c['id'],'normalized':r.ref(root,path),'prepared':{'path':'not-read','sha256':'a'*64}})
freeze=Path(stage).parent/'freeze.json'
manifest=freeze.parent/'manifest.json'
r.write(manifest,{'cases':cases})
frozen={'schema':'kitguard.v08.loco-combined.freeze.v1','cases':cases,'inputs':inputs,
        'source_hashes':r.inventory(Path(stage)),'manifest_sha256':r.sha(manifest),
        'methods':[{'mode':r.G}],'references':{},'historical_normal16':{'records':{}},'model':{}}
r.write(freeze,frozen)
class Engine:
    def __init__(self):self.diag=None
    def status(self):return {'loaded':False,'last_observation_attempt':self.diag}
    def observe(self,path,requirements,references):
        assert path.name.startswith('case-') and requirements==dict.fromkeys(r.PARTS,1) and references=={}
        self.diag={'source_sha256':r.sha(path),'generation_calls':[{'model_call_started':True,'model_call_completed':False}]}
        if scenario=='interrupt':raise KeyboardInterrupt('synthetic active-call interruption')
        return {'observed':dict(zip(r.PARTS,[2,4,0,0])),'issues':[],'action':{'kind':'none','message':'fixture'}}
engine=Engine()
r.verify_receipt=lambda *a:root
r.methods_identity=lambda *a:({r.G:engine},[])
r.legacy=lambda:SimpleNamespace(verify_model=lambda *a,**kw:None)
def check(mode,diagnostics,expected,artifacts,refs,completed):
    if scenario=='strict_stage_failure' and completed:raise ValueError('synthetic missing successful stage')
    return {'passed':True}
r.stage_contract=check
try:r.run(freeze,root/'run')
except KeyboardInterrupt:assert scenario=='interrupt'
meta=r.read(root/'run/run.json');rows=r.read(root/'run/predictions.json');analysis=r.read(root/'run/analysis.json')
if scenario=='interrupt':
    assert rows[0]['state']=='error' and 'KeyboardInterrupt' in rows[0]['error'] and rows[0]['latency_ms']>=0
    assert rows[0]['observation_diagnostics']['generation_calls'][0]['model_call_started']
    assert all(x['state']=='not_attempted' for x in rows[1:])
    assert analysis['methods'][r.G]['outcomes']=={'C':0,'W':0,'U':0,'E':1,'N':23}
    assert analysis['model_calls_started']==1 and meta['status']=='interrupted'
else:
    assert meta['status']=='failed_integrity' and meta['final_integrity_verified'] is False
    assert all(x['stage_contract']['successful_observation_stage_contract_failed'] for x in rows)
    assert analysis['methods'][r.G]['outcomes']['E']==24
assert not any(n=='mlx' or n.startswith('mlx.') for n in sys.modules)
'''


@pytest.mark.parametrize("scenario", ["interrupt", "strict_stage_failure"])
def test_attempted_interruption_and_strict_stage_failure_cannot_be_erased(snapshot, tmp_path, scenario):
    result = subprocess.run([sys.executable, "-I", "-c", RUN_WORKER, str(snapshot), str(tmp_path), scenario],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
