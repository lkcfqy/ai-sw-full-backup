"""Synthetic-only transfer execution/scoring contracts; no actual model or pixels."""
import importlib.util
import json
import math
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE=Path(__file__).resolve().parents[1]/'scripts/v08/run_manta_transfer.py'
spec=importlib.util.spec_from_file_location('transfer_inference_contract',SOURCE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def rows(count=579):
    result=[]
    for i in range(count):
        name='nut' if i<168 else 'washer' if i<180 else 'bolt'
        result.append({'input_id':f'roi-{i:04}','input_path':f'inputs/roi-{i:04}.png','input_sha256':str(i),
                       'source_id':f'synthetic:{i//10}','source_group':'synthetic_group','expected_identity':name,
                       'class_index':{'nut':0,'washer':1}.get(name),'tiny':i%3==0,'author_aabb_clipped':None if i%4==0 else i%2==0})
    return result


def prediction(row,probs=(.95,.05),status='ok'):
    value={**m.initial_predictions([row])[0],'status':status}
    if status=='ok':value.update(probabilities=list(probs),logits=[math.log(x) for x in probs])
    if status=='failed':value['error']={'type':'Synthetic','message':'planned contract failure'}
    return value


def test_import_has_no_torch_image_or_product_side_effects():
    code=f"import runpy,sys;runpy.run_path({str(SOURCE)!r});assert not any(x in sys.modules for x in ('torch','torchvision','PIL','mlx','kitguard'))"
    got=subprocess.run([sys.executable,'-I','-c',code],capture_output=True,text=True,check=False)
    assert got.returncode==0,got.stderr


@pytest.mark.parametrize(('prob','state','name'),[(.9,'accepted','nut'),(.9-1e-12,'U',None),(.1,'accepted','yellow_green_washer')])
def test_exact_threshold_original_output_names(prob,state,name):
    assert m.answer({'status':'ok','probabilities':[prob,1-prob]})==(state,name)


def test_full579_panels_cannot_hide_bolt_acceptance_in_identity_counts():
    records=rows();raw=[prediction(r) for r in records]
    result=m.summarize(records,raw)
    known=result['threshold_0_9']['identity']['all']
    bolts=result['threshold_0_9']['bolt_open_category']['all']
    assert known['denominator']==180 and known['counts']=={'C':168,'W':12,'U':0,'E':0,'N':0}
    assert known['confusion']['nut']==180
    assert bolts['denominator']==399 and bolts['counts']['accepted_nut']==399 and bolts['false_acceptance_rate']==1
    assert result['constant_baselines']['abstain_all']['identity']['U']==180
    assert result['constant_baselines']['abstain_all']['bolt_open_category']['U']==399
    assert not result['production_promotion']
    assert 'source_group=synthetic_group|identity=washer' in result['threshold_0_9']['identity']
    assert 'author_clipped=unknown' in result['threshold_0_9']['bolt_open_category']


def test_all_statuses_preserved_and_order_rejected():
    records=[rows()[0],rows()[168],rows()[180],rows()[181],rows()[182]]
    raw=[prediction(records[0],(.5,.5)),prediction(records[1],status='failed'),
         prediction(records[2],status='not_attempted'),prediction(records[3],(.01,.99)),prediction(records[4],(.5,.5))]
    got=m.summarize(records,raw)['threshold_0_9']
    assert got['identity']['all']['counts']=={'C':0,'W':0,'U':1,'E':1,'N':0}
    assert got['bolt_open_category']['all']['counts']=={'accepted_nut':0,'accepted_yellow_green_washer':1,'U':1,'E':0,'N':1}
    with pytest.raises(ValueError):m.summarize(records,raw[::-1])


class FakeInput:
    def __init__(self,values):self.values=values
    def to(self,_):return self


class FakeArray:
    def __init__(self,values,prob=False):self.values=values;self.shape=(len(values),2);self.prob=prob
    def softmax(self,dim):
        assert dim==1
        return FakeArray([[.6,.4] for _ in self.values],True)
    def cpu(self):return self
    def tolist(self):return self.values


@pytest.mark.parametrize('failure',['none','decode','forward','interrupt'])
def test_batches_only_image_inputs_and_no_retry_full_denominator(tmp_path,monkeypatch,failure):
    records=rows();calls=[];decoded=[]
    def input_tensor(base,row,hashes):
        assert set(row)=={'input_id','input_path','input_sha256'}
        decoded.append(row['input_id']);hashes[row['input_id']]='synthetic-tensor'
        if failure=='decode' and row['input_id']=='roi-0000':raise ValueError('synthetic decode failure')
        return row['input_id']
    factory=SimpleNamespace(input_tensor=input_tensor)
    torch=SimpleNamespace(stack=FakeInput,mps=SimpleNamespace(synchronize=lambda:None),inference_mode=nullcontext,
                          isfinite=lambda _:SimpleNamespace(all=lambda:SimpleNamespace(item=lambda:True)))
    monkeypatch.setitem(sys.modules,'torch',torch)
    class Model:
        def eval(self):return self
        def __call__(self,images):
            calls.append(list(images.values))
            if len(calls)==1:
                if failure=='forward':raise ValueError('synthetic forward error')
                if failure=='interrupt':raise KeyboardInterrupt('synthetic interrupt')
            return FakeArray([[.2,.1] for _ in images.values])
    predictions,batches,_,interrupted=m.evaluate(Model(),records,tmp_path,factory,tmp_path)
    assert len(predictions)==579
    assert len(calls)=={'none':19,'decode':18,'forward':19,'interrupt':1}[failure]
    assert sum(b['actual_forward_started'] for b in batches)==len(calls)
    assert sum(b['actual_forward_returned'] for b in batches)==len(calls)-(failure in ('forward','interrupt'))
    assert [json.loads(x) for x in (tmp_path/'raw.jsonl').read_text().splitlines()]==predictions
    if failure=='none':
        assert all(p['status']=='ok' and p['model_output_class']=='nut' and p['threshold_result']=='U' for p in predictions)
        assert len(calls[-1])==3 and len(decoded)==579
    elif failure=='interrupt':
        assert isinstance(interrupted,KeyboardInterrupt)
        assert sum(p['status']=='not_attempted' for p in predictions)==547
    else:
        assert all(p['status']=='failed' for p in predictions[:32])
        assert all(p['status']=='ok' for p in predictions[32:])


def test_inference_setup_failure_is_all_N_and_zero_forward(tmp_path,monkeypatch):
    records=rows();plan={'records':records}
    path=tmp_path/'plan.json';m.write_new(path,plan)
    approval=tmp_path/'approval.json';m.write_new(approval,{'synthetic':True})
    monkeypatch.setattr(m,'validate_approval',lambda *_:plan)
    def fail(*_):raise ValueError('synthetic changed input')
    monkeypatch.setattr(m,'verify_plan',fail)
    before='torch' in sys.modules
    got=m.run(path,m.sha(path),approval,m.sha(approval),tmp_path/'out')
    assert got['status']=='failed_integrity' and got['actual_forward_calls_started']==0
    assert got['status_counts']=={'not_attempted':579}
    assert ('torch' in sys.modules)==before
    assert len(m.read(tmp_path/'out'/'predictions.json'))==579
    assert len(m.read(tmp_path/'out'/'artifact_inventory.json'))==8


def test_separate_approval_binds_snapshot_and_checkpoint(tmp_path):
    plan={'schema':'kitguard.v08.manta-transfer.inference-plan.v1','config':m.CONFIG,
          'source_snapshot':{m.SCRIPT:'runner'},'classifier_checkpoint':{'sha256':'final10'}}
    path=tmp_path/'plan.json';m.write_new(path,plan)
    approval={'schema':'kitguard.v08.manta-transfer.inference-approval.v1','status':'approved','authorized_by':'root',
              'scope':'infer_all579_oracle_rois_once','plan_sha256':m.sha(path),'runner_sha256':'runner',
              'classifier_checkpoint_sha256':'final10','allow_training':False,'production_change':False}
    apath=tmp_path/'approval.json';m.write_new(apath,approval)
    assert m.validate_approval(path,m.sha(path),apath,m.sha(apath))==plan
    approval['classifier_checkpoint_sha256']='earlier7';bad=tmp_path/'bad.json';m.write_new(bad,approval)
    with pytest.raises(ValueError):m.validate_approval(path,m.sha(path),bad,m.sha(bad))


def test_class_macros_and_zero_source_cross_cells_are_explicit():
    records=rows()
    for row in records[180:]:row['source_group']='bolt_only_group'
    result=m.summarize(records,[prediction(r) for r in records])['threshold_0_9']
    assert result['identity_macros']['class_macro_correct_coverage']==.5
    assert result['identity_macros']['source_class_macro_correct_coverage']==.5
    assert result['identity_macros']['nonempty_source_class_cells']==2
    empty=result['identity']['source_group=bolt_only_group|identity=washer|tiny=lt16|author_clipped=unknown']
    assert empty['denominator']==0 and empty['correct_coverage'] is None and empty['status']=='not_applicable_no_targets'
    empty_bolt=result['bolt_open_category']['source_group=synthetic_group|identity=bolt|tiny=ge16|author_clipped=false']
    assert empty_bolt['denominator']==0 and empty_bolt['false_acceptance_rate'] is None
