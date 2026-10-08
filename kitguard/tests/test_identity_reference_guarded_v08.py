"""Synthetic isolated v0.7 CPU contracts; never import MLX or run a real model."""
import copy
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.v08 import run_identity_reference_guarded as r

ROOT = Path(__file__).resolve().parents[1]

WORKER = r'''
import sys, os, json, copy
from pathlib import Path
from types import SimpleNamespace
stage, output, scenario = map(str, sys.argv[1:4])
sys.path.insert(0,stage)
os.environ['KITGUARD_DATA_DIR'] = str(Path(output)/'runtime-app-data')
from PIL import Image
from kitguard import vision
from kitguard.evaluation import score_case
from scripts.probe_selective_identity import SelectiveIdentityVision
from scripts.v08 import run_identity_reference_guarded as r
root=Path(output); root.mkdir(parents=True,exist_ok=True)
for name,color in [('target','white'),('nut','red'),('washer','blue')]:
    im=Image.new('RGB',(200,160),color);im.putpixel((0,0),(0,255,0));im.save(root/(name+'.png'))
refs={p:root/(p+'.png') for p in r.REF_PARTS}
objects=[{'part':'nut','center':[.3,.5]},{'part':'washer','center':[.7,.5]}]
if scenario=='no_candidates':objects=[{'part':'bolt','center':[.4,.5]}]
def inventory(objects):
    return {'objects':objects,'uncertain_parts':[],'issues':[],'action':{'kind':'none','message':'fixture'}}
second=copy.deepcopy(objects)
if scenario=='disagree':second[0]['part']='washer'
ident={'objects':[{'id':'p001','part':'nut','status':'independent_object','opening':'through_hole','issue':''},
                  {'id':'p002','part':'washer','status':'independent_object','opening':'through_hole','issue':''}]}
if scenario=='blocked':ident['objects'][0].update(part='unknown',status='uncertain',opening='uncertain',issue='fixture unclear')
if scenario=='wrong_id':ident['objects'][0]['id']='p999'
if scenario=='missing_id':ident['objects'].pop()
texts=[json.dumps(inventory(objects)), json.dumps(inventory(second)),json.dumps(ident)]
if scenario=='first_invalid':texts[0]='not json'
if scenario=='second_invalid':texts[1]='not json'
if scenario=='identity_invalid':texts[2]='not json'
class Baseline(vision.LocalVision):
    _generate=SelectiveIdentityVision._generate

def perform(engine,directory,refmap):
    engine.artifact_dir=directory
    counter=[0]
    loads=[0]
    schemas=[]
    def generate(*args,**kwargs):
        n=counter[0];counter[0]+=1
        if scenario=='identity_generate_failure' and n==2:raise RuntimeError('synthetic generate failure')
        return SimpleNamespace(text=texts[n],prompt_tokens=100,generation_tokens=20,peak_memory=.1,finish_reason='stop')
    def grammar(tokenizer,schema):
        schemas.append(schema)
        if scenario=='identity_grammar_failure' and len(schemas)==3:raise RuntimeError('synthetic grammar failure')
        return object()
    def load():
        loads[0]+=1
        if (scenario=='first_load_failure' and loads[0]==1) or (scenario=='identity_load_failure' and loads[0]==3):
            raise RuntimeError('synthetic load failure')
        return {'template':lambda *a,**kw:'synthetic template', 'processor':object(),'config':{},
                'grammar':grammar,'generate':generate,'model':object()}
    engine._load=load
    result=error=None
    try:result=engine.observe(root/'target.png',dict.fromkeys(r.PARTS,1),refmap)
    except Exception as exc:error=type(exc).__name__
    return {'observation':result,'error':error,'calls':engine.status()['last_observation_attempt']['generation_calls'],
            'diagnostics':engine.status()['last_observation_attempt'],'status':engine.status(),
            'schemas':schemas,'attempts':counter[0]}
base=perform(Baseline(observation_mode='spatial_guarded',image_max_side=1536),root/'base',{})
candidate=perform(r.observer(),root/'candidate',refs)
d=candidate['diagnostics']
receipts={p:{'prepared_sha256':r.sha(refs[p])} for p in r.REF_PARTS}
# The actual _prepare_image output is PNG re-encoded RGB (same bytes for these fixtures).
r.check_reference_stages(d,receipts,root/'candidate',candidate['error'] is None)
r.check_target_stages(d,base['calls'][0]['images'][0]['sha256'],root/'candidate',receipts)
assert not any(x.startswith(('mlx','torch','transformers')) for x in sys.modules)
assert not (Path(stage)/'data').exists()
json.dump({'base':base,'candidate':candidate,'sources_unchanged':r.sources(Path(stage))},open(root/'result.json','w'))
'''


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    destination = tmp_path_factory.mktemp("identity_ref_source") / "source_snapshot"
    expected = r.prepare_sources(ROOT, destination)
    assert "data/kitguard.sqlite3" not in expected
    assert expected["kitguard/vision.py"] == r.read(ROOT / r.BASE_SOURCE_FREEZE)["source_hashes"]["kitguard/vision.py"]
    return destination, expected


@pytest.mark.parametrize("scenario", ["confirmed", "blocked", "disagree", "no_candidates", "first_invalid",
                                      "second_invalid", "identity_invalid", "wrong_id", "missing_id", "first_load_failure",
                                      "identity_load_failure", "identity_grammar_failure", "identity_generate_failure"])
def test_frozen_base_calls_roles_schema_failure_and_veto(snapshot, tmp_path, scenario):
    stage, expected = snapshot
    done = subprocess.run([sys.executable, "-I", "-c", WORKER, str(stage), str(tmp_path), scenario],
                          text=True, capture_output=True, check=False)
    assert done.returncode == 0, done.stderr
    data = r.read(tmp_path / "result.json")
    assert data["sources_unchanged"] == expected
    base, new = data["base"], data["candidate"]
    assert base["error"] == new["error"]
    assert base["attempts"] == new["attempts"] <= 3
    assert sum(c["model_call_started"] for c in new["calls"]) == new["attempts"]
    assert sum(c["model_call_completed"] for c in new["calls"]) == new["attempts"] - (scenario == "identity_generate_failure")
    for old_call, call in zip(base["calls"][:2], new["calls"][:2], strict=True):
        for key in ("system", "prompt", "schema", "max_tokens", "raw_text", "images"):
            assert old_call[key] == call[key]
        assert len(call["images"]) == 1 and call["max_tokens"] == 900
    assert base["schemas"] == new["schemas"]
    if len(new["calls"]) == 3:
        old_call, call = base["calls"][2], new["calls"][2]
        assert call["images"][:-2] == old_call["images"]
        assert call["max_tokens"] == 1800
        assert "Each later image is an unmarked crop" not in call["system"]
        assert "reference for nut; do NOT count it" in call["prompt"]
        assert "reference for washer; do NOT count it" in call["prompt"]
        assert old_call["system"].split("Point IDs", 1)[1] == call["system"].split("Point IDs", 1)[1]
        assert [v["role"] for v in call["input_roles"]][-2:] == ["category_reference"] * 2
        assert call["input_roles"][-2]["part"] == "nut" and call["input_roles"][-1]["part"] == "washer"
        assert call["experiment_protocol_sha256"] == new["status"]["observer_protocol_sha256"]
    if new["observation"]:
        first, second = copy.deepcopy(base["observation"]), copy.deepcopy(new["observation"])
        first.pop("latency_ms");second.pop("latency_ms")
        assert first == second
        if scenario == "blocked":
            assert second["observed"]["nut"] is None and second["observed"]["washer"] == 1
    else:
        assert new["diagnostics"]["status"] == "failed"
        assert (new["calls"][-1]["raw_text"] is None) == scenario.endswith("failure")
    assert new["status"]["observation_mode"] == r.MODE
    assert new["status"]["observer_protocol_sha256"] != new["status"]["base_observer_protocol_sha256"]
    trace = new["diagnostics"]["experimental_reference_inputs"]
    assert trace["identity_stage_status"] == new["diagnostics"].get("identity", {}).get("status", "not_reached")
    if scenario in {"disagree", "no_candidates", "first_invalid", "second_invalid", "first_load_failure"}:
        assert trace["identity_reference_indices"] == [] and trace["identity_generation_status"] == "not_called"
    if scenario in {"wrong_id", "missing_id"}:
        assert trace["identity_generation_status"] == "parsed" and trace["identity_stage_status"] == "failed"


def test_current_product_observer_cannot_be_used_accidentally():
    with pytest.raises(ValueError, match="legacy source bundle"):
        r.observer()


def test_source_staging_refuses_overwrite(snapshot):
    with pytest.raises(ValueError, match="already exists"):
        r.prepare_sources(ROOT, snapshot[0])


def test_real51_source_binding_supports_uncropped_loco_metadata():
    cases = r.read(ROOT / r.BASE / "manifest.json")["cases"]
    historical = r.read(ROOT / "docs/v0.8/reference_guarded_freeze_v1/freeze.json")["cases"]
    source_refs = {item["case"]["id"]: item["source"] for item in historical}
    assert sum("source_image" not in case for case in cases) == 16
    assert len(cases) == len(source_refs) == 51
    for case in cases:
        assert r.case_source_ref(case) == source_refs[case["id"]]


@pytest.mark.parametrize("change", ["schema", "policy"])
def test_freeze_rejects_receipt_protocol_changes_before_any_model_access(tmp_path, change):
    receipt = {"schema": "kitguard.v08.identity-reference-guarded.preflight.v1", "policy": r.POLICY}
    receipt[change] = "changed"
    with pytest.raises(ValueError, match="schema/policy changed"):
        r.create_freeze(receipt, tmp_path / "freeze")
    assert not (tmp_path / "freeze").exists()


def test_unchanged_gate_and_full_failure_denominator():
    # Reuse synthetic fixtures only, not previous observed cases.
    from tests.test_reference_guarded_v08 import candidate, items
    dataset = items()
    rows = [candidate(i) | {"mode": r.MODE} for i in dataset[:-1]]
    rows[0]["error"] = "synthetic failed case"
    a = r.analyze(dataset, rows)
    assert sum(a["outcomes"].values()) == 51 and a["outcomes"]["N"] == a["outcomes"]["E"] == 1
    assert not a["development_gate_count_conditions_passed"]
    assert a["concurrent_latency_comparison"] is False and a["automatic_promotion"] is False
    with pytest.raises(ValueError, match="51-case"):
        r.analyze(dataset[:50], [])
