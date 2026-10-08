"""One fixed MANTA epoch10 transfer inference over all579 oracle annotation ROIs.

Separate preflight snapshots this runner/tests/protocol. Actual inference requires
root approval. No training, tuning, detection, fallback, repeated attempt or product import.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCRIPT='scripts/v08/run_manta_transfer.py'
TEST='tests/test_manta_transfer_inference_v08.py'
PROTOCOL='docs/v0.8/MANTA_CLASSIFIER_CROSS_SOURCE_PROTOCOL_V1.md'
PREPARER='scripts/v08/prepare_manta_transfer.py'
PREPARER_SHA='cf68721a97e402cb21f721c65dd76072e1f5c945f75eeb20ed4e32e38e8ea560'
TRAINER='scripts/v08/train_manta_classifier.py'
TRAINER_SHA='5f3475a5b911cada936eb62fae24890b1f4096153307a6b64a7e5619bca9057c'
TRAINING_PLAN='test-results/v0.8-manta-classifier-training-preflight-v1/plan.json'
TRAINING_PLAN_SHA='8a178cb097792b6c2618b4dce86c343a3d799c870b4ed1ff7c658c6ffabb85d6'
LAYOUT_BINDINGS={
    'test-results/v0.8-manta-transfer-root-check-v1/machine-check.json':'283b02f1221db6d6072a0f24c93c23e639df0cf3374ec6cd16e76b4eb9e6567a',
    'test-results/v0.8-manta-transfer-root-check-v1/visual-review.json':'6b349d01f0e61dfbf7ee50702f907d99f0bc92fcb88fcede02c820a0259a585c',
}
CONFIG={'epoch':10,'device':'mps','precision':'float32','batch_size':32,'threshold':.9,
        'output_classes':['nut','yellow_green_washer'],'score_aliases':['nut','washer'],
        'mean':[.485,.456,.406],'std':[.229,.224,.225],'augment':False,'retries':0,'planned_forward_calls':19}


def require(condition,message):
    if not condition:raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_text())


def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:stream.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def load_module(path,name,expected):
    require(sha(path)==expected,'Unreviewed source module')
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def verify_prepared(root,prepared_path,expected,metadata_path):
    root,prepared_path,metadata_path=Path(root).resolve(),Path(prepared_path).resolve(),Path(metadata_path).resolve()
    require(sha(prepared_path)==expected,'Preparation receipt changed')
    receipt=read(prepared_path);base=prepared_path.parent
    for rel,bound in LAYOUT_BINDINGS.items():
        require(sha(root/rel)==bound and read(root/rel)['preparation_sha256']==expected,'Root input/layout evidence changed')
    require(receipt['schema']=='kitguard.v08.manta-transfer.preparation.v1' and receipt['status']=='prepared'
            and receipt['status_counts']=={'prepared':579} and receipt['integrity_error'] is None
            and receipt['models_called']==0 and receipt['independent_detection'] is False,'Preparation incomplete')
    require(sha(metadata_path)==sha(base/'metadata.json')==receipt['metadata_sha256'],'Metadata binding differs')
    meta=read(metadata_path)
    require(meta['source_snapshot'][PREPARER]==PREPARER_SHA,'Unreviewed preparer')
    prep=load_module(metadata_path.parent/'source_snapshot'/PREPARER,'frozen_transfer_preparer',PREPARER_SHA)
    prep.check_gate(metadata_path,receipt['metadata_sha256'],base/'approval.json',receipt['approval_sha256'])
    require(prep.pillow_runtime()==meta['runtime'],'Preparation dependencies changed')
    for rel, expected_sha in meta['bindings'].items():require(sha(prep.safe_path(root,rel))==expected_sha,'Original metadata changed')
    for rel, expected_sha in meta['source_snapshot'].items():require(sha(prep.safe_path(metadata_path.parent/'source_snapshot',rel))==expected_sha,'Preparer snapshot changed')
    require(sha(base/'records.json')==receipt['records_sha256'],'Prepared record list changed')
    rows=read(base/'records.json')
    require(len(rows)==len(meta['records'])==579,'ROI denominator differs')
    for row, original in zip(rows,meta['records'],strict=True):
        require(all(row.get(k)==v for k,v in original.items()) and row['status']=='prepared' and row['error'] is None,'ROI record differs')
        require(row['input_path']==f"inputs/{row['input_id']}.png" and row['input_size']==[224,224],'Prepared input differs')
        require(sha(prep.safe_path(base,row['input_path']))==row['input_sha256'],'Prepared input bytes changed')
    require(Counter(r['expected_identity'] for r in rows)=={'nut':168,'washer':12,'bolt':399},'Class denominator differs')
    approval=read(base/'approval.json')
    model=approval['classifier_checkpoint']
    training_plan_path=root/TRAINING_PLAN
    require(sha(training_plan_path)==TRAINING_PLAN_SHA,'Internal training plan changed')
    training_plan=read(training_plan_path)
    factory_path=training_plan_path.parent/'source_snapshot'/TRAINER
    require(training_plan['source_snapshot'][TRAINER]==TRAINER_SHA,'Training factory differs')
    factory=load_module(factory_path,'frozen_manta_factory',TRAINER_SHA)
    require(factory.runtime()==training_plan['runtime'],'Training/model dependencies changed')
    require(sha(training_plan['weights_path'])==training_plan['weights_sha256'],'Original COCO changed')
    return {'records':rows,'input_base':str(base),'classifier_checkpoint':model,
            'internal_audit':approval['internal_audit'],'internal_run':approval['internal_run'],
            'factory_path':str(factory_path),'factory_sha256':TRAINER_SHA,'coco_path':training_plan['weights_path'],
            'coco_sha256':training_plan['weights_sha256'],'runtime':factory.runtime(),
            'layout_evidence':LAYOUT_BINDINGS,'preparer':prep,'factory':factory}


def preflight(root,prepared,expected,metadata,output):
    root,output=Path(root).resolve(),Path(output).resolve()
    require(not output.exists(),'Preflight output exists')
    checked=verify_prepared(root,prepared,expected,metadata)
    output.mkdir(parents=True)
    sources={}
    for rel in (SCRIPT,TEST,PROTOCOL):
        target=output/'source_snapshot'/rel;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/rel,target);sources[rel]=sha(target)
        require(sha(root/rel)==sources[rel],'Source changed during preflight')
    plan={k:v for k,v in checked.items() if k not in ('preparer','factory')}
    plan.update(schema='kitguard.v08.manta-transfer.inference-plan.v1',status='prepared_not_authorized',
                created_at_utc=datetime.now(UTC).isoformat(),project_root=str(root),config=CONFIG,
                preparation_path=str(Path(prepared).resolve()),preparation_sha256=expected,
                metadata_path=str(Path(metadata).resolve()),metadata_sha256=sha(metadata),source_snapshot=sources,
                image_count=80,roi_count=579,identity_count=180,bolt_count=399,
                actual_images_decoded_by_preflight=0,models_called=0,production_change=False)
    write_new(output/'plan.json',plan)
    return {'plan':str(output/'plan.json'),'sha256':sha(output/'plan.json'),'status':plan['status']}


def validate_approval(plan_path,expected,approval_path,approval_sha):
    require(sha(plan_path)==expected and sha(approval_path)==approval_sha,'Plan/approval SHA changed')
    plan,approval=read(plan_path),read(approval_path)
    require(plan['schema']=='kitguard.v08.manta-transfer.inference-plan.v1' and plan['config']==CONFIG,'Wrong inference plan')
    require(approval['schema']=='kitguard.v08.manta-transfer.inference-approval.v1' and approval['status']=='approved'
            and approval['authorized_by']=='root' and approval['scope']=='infer_all579_oracle_rois_once'
            and approval['plan_sha256']==expected and approval['runner_sha256']==plan['source_snapshot'][SCRIPT]
            and approval['classifier_checkpoint_sha256']==plan['classifier_checkpoint']['sha256']
            and approval['allow_training'] is False and approval['production_change'] is False,'Separate root inference approval required')
    return plan


def verify_plan(plan_path,plan):
    base=Path(plan_path).parent
    require(Path(__file__).resolve()==base/'source_snapshot'/SCRIPT,'Run frozen source only')
    require(set(plan['source_snapshot'])=={SCRIPT,TEST,PROTOCOL},'Source inventory differs')
    for rel,expected in plan['source_snapshot'].items():require(sha(base/'source_snapshot'/rel)==expected,'Inference snapshot changed')
    checked=verify_prepared(plan['project_root'],plan['preparation_path'],plan['preparation_sha256'],plan['metadata_path'])
    for key in ('records','input_base','classifier_checkpoint','internal_audit','internal_run','factory_path','factory_sha256','coco_path','coco_sha256','runtime','layout_evidence'):
        require(checked[key]==plan[key],'Preflight data/model binding changed: '+key)
    return checked


def answer(prediction,forced=False):
    state=prediction['status']
    if state=='failed':return 'E',None
    if state=='not_attempted':return 'N',None
    require(state=='ok','Unexpected prediction status')
    values=prediction['probabilities']
    require(isinstance(values,list) and len(values)==2 and all(type(x) in (int,float) and math.isfinite(x) and 0<=x<=1 for x in values)
            and abs(sum(values)-1)<1e-5,'Invalid probabilities')
    chosen=0 if values[0]>=values[1] else 1
    if not forced and values[chosen]<.9:return 'U',None
    return 'accepted',CONFIG['output_classes'][chosen]


def subgroup(row):
    return {'source_group':row['source_group'],'identity':row['expected_identity'],
            'tiny':'lt16' if row['tiny'] else 'ge16',
            'author_clipped':{True:'true',False:'false',None:'unknown'}[row['author_aabb_clipped']]}


def group_tables(rows,predictions,forced=False,all_source_groups=None):
    panels=defaultdict(list)
    for row,pred in zip(rows,predictions,strict=True):
        state,choice=answer(pred,forced)
        if row['expected_identity']=='bolt':
            code={'nut':'accepted_nut','yellow_green_washer':'accepted_yellow_green_washer'}[choice] if state=='accepted' else state
        else:
            code=('C' if choice==CONFIG['output_classes'][row['class_index']] else 'W') if state=='accepted' else state
        labels=subgroup(row)
        keys=['all']+[f'{name}={value}' for name,value in labels.items()]
        keys += [f"source_group={labels['source_group']}|identity={labels['identity']}",
                 f"source_group={labels['source_group']}|identity={labels['identity']}|tiny={labels['tiny']}|author_clipped={labels['author_clipped']}"]
        for key in keys:panels[key].append((row,pred,code))
    result={}
    for key,items in sorted(panels.items()):
        codes=[item[2] for item in items]
        bolt=rows[0]['expected_identity']=='bolt'
        names=('accepted_nut','accepted_yellow_green_washer','U','E','N') if bolt else tuple('CWUEN')
        tally={name:codes.count(name) for name in names}
        result[key]={'denominator':len(items),'image_count':len({r['source_id'] for r,_,_ in items}),
                     'source_group_count':len({r['source_group'] for r,_,_ in items}),'counts':tally}
        if bolt:
            result[key]['false_acceptance_rate']=(tally['accepted_nut']+tally['accepted_yellow_green_washer'])/len(items)
        else:
            result[key]['correct_coverage']=tally['C']/len(items)
            result[key]['coverage']=(tally['C']+tally['W'])/len(items)
            columns=[]
            for _,prediction,_ in items:
                state,choice=answer(prediction,forced)
                columns.append(choice if state=='accepted' else {'U':'unknown','E':'error','N':'not_attempted'}[state])
            result[key]['confusion']={name:columns.count(name) for name in ('nut','yellow_green_washer','unknown','error','not_attempted')}
    # Fixed empty cross-cells remain explicit N/A instead of disappearing.
    bolt=rows[0]['expected_identity']=='bolt'
    names=('accepted_nut','accepted_yellow_green_washer','U','E','N') if bolt else tuple('CWUEN')
    identities=('bolt',) if bolt else ('nut','washer')
    for source in all_source_groups or sorted({r['source_group'] for r in rows}):
        for identity in identities:
            prefixes=[f'source_group={source}|identity={identity}']
            prefixes += [f'source_group={source}|identity={identity}|tiny={tiny}|author_clipped={clipped}'
                         for tiny in ('lt16','ge16') for clipped in ('true','false','unknown')]
            for key in prefixes:
                if key not in result:
                    entry={'denominator':0,'image_count':0,'source_group_count':0,'counts':{name:0 for name in names},
                           'status':'not_applicable_no_targets'}
                    if bolt:entry['false_acceptance_rate']=None
                    else:entry.update(correct_coverage=None,coverage=None,confusion={name:0 for name in ('nut','yellow_green_washer','unknown','error','not_attempted')})
                    result[key]=entry
    return result


def summarize(rows,predictions):
    require(len(rows)==len(predictions) and [r['input_id'] for r in rows]==[p['input_id'] for p in predictions],'Full ROI denominator/order changed')
    require(len({r['input_id'] for r in rows})==len(rows),'Repeated ROI')
    identity=[(r,p) for r,p in zip(rows,predictions,strict=True) if r['expected_identity']!='bolt']
    bolts=[(r,p) for r,p in zip(rows,predictions,strict=True) if r['expected_identity']=='bolt']
    require(identity and bolts,'Both fixed panels required')
    known_rows,known_preds=map(list,zip(*identity,strict=True));bolt_rows,bolt_preds=map(list,zip(*bolts,strict=True))
    source_groups=sorted({r['source_group'] for r in rows})
    result={name:{'identity':group_tables(known_rows,known_preds,forced,source_groups),'bolt_open_category':group_tables(bolt_rows,bolt_preds,forced,source_groups)}
            for name,forced in (('threshold_0_9',False),('forced_argmax',True))}
    for panel in result.values():
        table=panel['identity']
        classes=[v for k,v in table.items() if k.startswith('identity=') and v['denominator']]
        source_classes=[v for k,v in table.items() if k.startswith('source_group=') and k.count('|')==1 and v['denominator']]
        panel['identity_macros']={'class_count':len(classes),'class_macro_correct_coverage':sum(v['correct_coverage'] for v in classes)/len(classes),
                                  'class_macro_coverage':sum(v['coverage'] for v in classes)/len(classes),
                                  'nonempty_source_class_cells':len(source_classes),
                                  'source_class_macro_correct_coverage':sum(v['correct_coverage'] for v in source_classes)/len(source_classes),
                                  'source_class_macro_coverage':sum(v['coverage'] for v in source_classes)/len(source_classes)}
    result['constant_baselines']={name:{'identity':{'C':sum(r['class_index']==i for r in known_rows),
                                                  'W':sum(r['class_index']!=i for r in known_rows),'U':0,'E':0,'N':0,'class_macro_correct_coverage':.5},
                                     'bolt_open_category':{'accepted':len(bolt_rows),'U':0,'E':0,'N':0,'false_acceptance_rate':1.0}}
                                  for i,name in enumerate(CONFIG['output_classes'])}
    result['constant_baselines']['abstain_all']={'identity':{'C':0,'W':0,'U':len(known_rows),'E':0,'N':0,'class_macro_correct_coverage':0.0},
                                                'bolt_open_category':{'accepted':0,'U':len(bolt_rows),'E':0,'N':0,'false_acceptance_rate':0.0}}
    result['scope']='Oracle author-ROI identity transfer, previously exposed validation; no independent detection/counting/BOM or physical independence.'
    result['production_promotion']=False
    return result


def initial_predictions(rows):
    return [{k:r[k] for k in ('input_id','input_sha256','source_id','expected_identity','class_index','source_group','tiny','author_aabb_clipped')}
            | {'status':'not_attempted','logits':None,'probabilities':None,'error':None,
               'actual_forward_started':False,'actual_forward_returned':False,'model_output_class':None,'threshold_result':'N'} for r in rows]


def evaluate(model,rows,base,factory,output,state=None):
    import torch
    state=state if state is not None else {'predictions':initial_predictions(rows),'hashes':{},'batches':[]}
    predictions,hashes,batches=state['predictions'],state['hashes'],state['batches'];interrupted=None
    model.eval()
    with (output/'raw.jsonl').open('x') as stream:
        for start in range(0,len(rows),32):
            subset=rows[start:start+32];results=predictions[start:start+32]
            batch={'index':start//32,'input_ids':[r['input_id'] for r in subset], 'status':'attempted',
                   'actual_forward_started':False,'actual_forward_returned':False,'decode_tensor_seconds':None,'model_seconds':None}
            begin=time.perf_counter();model_started=None
            try:
                # The fixed factory tensor function receives only a path/size/SHA identity, no author labels or boxes.
                tensor_rows=[{k:r[k] for k in ('input_id','input_path','input_sha256')} for r in subset]
                inputs=torch.stack([factory.input_tensor(base,r,hashes) for r in tensor_rows])
                batch['decode_tensor_seconds']=time.perf_counter()-begin
                inputs=inputs.to('mps');torch.mps.synchronize()
                model_started=time.perf_counter();batch['actual_forward_started']=True
                with torch.inference_mode():
                    logits=model(inputs);batch['actual_forward_returned']=True
                    require(logits.shape==(len(subset),2) and torch.isfinite(logits).all().item(),'Invalid logits')
                    probabilities=logits.softmax(dim=1)
                torch.mps.synchronize();batch['model_seconds']=time.perf_counter()-model_started
                for result,values,probs in zip(results,logits.cpu().tolist(),probabilities.cpu().tolist(),strict=True):
                    result.update(status='ok',logits=values,probabilities=probs)
                    outcome,_=answer(result)
                    choice=CONFIG['output_classes'][0 if probs[0]>=probs[1] else 1]
                    result.update(model_output_class=choice,threshold_result=outcome)
                batch['status']='completed'
            except BaseException as error:  # noqa: BLE001 -- every failed batch retained, no fallback/retry
                batch.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
                for result in results:result.update(status='failed',error=batch['error'],model_output_class=None,threshold_result='E')
                if not isinstance(error,Exception):interrupted=error
            finally:
                if model_started is not None and batch['model_seconds'] is None:batch['model_seconds']=time.perf_counter()-model_started
                batch['wall_seconds']=time.perf_counter()-begin;batches.append(batch)
                for result in results:
                    result.update(batch_index=batch['index'],actual_forward_started=batch['actual_forward_started'],actual_forward_returned=batch['actual_forward_returned'])
                    stream.write(canonical(result)+'\n')
                stream.flush()
            if interrupted:break
        for result in predictions:
            if result['status']=='not_attempted':stream.write(canonical(result)+'\n')
    return predictions,batches,hashes,interrupted


def run(plan_path,expected,approval_path,approval_sha,output):
    start=time.perf_counter();plan_path,output=Path(plan_path).resolve(),Path(output).resolve()
    plan=validate_approval(plan_path,expected,approval_path,approval_sha)
    require(not output.exists(),'Run output exists')
    require(os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK','0')=='0','MPS fallback forbidden')
    output.mkdir(parents=True);shutil.copyfile(plan_path,output/'plan.json');shutil.copyfile(approval_path,output/'approval.json')
    predictions=initial_predictions(plan['records']);batches=[];hashes={};interrupted=None;model=None;stage='verification'
    result={'schema':'kitguard.v08.manta-transfer.inference-run.v1','status':'running','started_at_utc':datetime.now(UTC).isoformat(),
            'plan_sha256':expected,'approval_sha256':approval_sha,'model_initialization_started':False,
            'planned_roi_count':579,'planned_forward_calls':19,'actual_forward_calls_started':0,'actual_forward_calls_returned':0,
            'training_steps':0,'production_change':False,'new_holdout_claim':False}
    write_new(output/'started.json',result)
    try:
        checked=verify_plan(plan_path,plan)
        import torch
        require(torch.backends.mps.is_available(),'Pinned MPS unavailable')
        factory=checked['factory'];stage='model_initialization';result['model_initialization_started']=True
        model=factory.build_model(plan['coco_path'])
        checkpoint=torch.load(plan['classifier_checkpoint']['path'],map_location='cpu',weights_only=True)
        require(checkpoint['schema']=='kitguard.v08.manta-classifier.full-checkpoint.v1' and checkpoint['epoch']==10
                and checkpoint['plan_sha256']==TRAINING_PLAN_SHA and checkpoint['classes']=={'nut':0,'yellow_green_washer':1},'Wrong fixed classifier checkpoint')
        model.load_state_dict(checkpoint['model_state_dict'],strict=True)
        require(factory.state_digest(model.body)==checkpoint['body_state_sha256']
                and factory.state_digest(model.head)==checkpoint['head_state_sha256'],'Loaded classifier state differs')
        for parameter in model.parameters():parameter.requires_grad_(False)
        model=model.to('mps',dtype=torch.float32).eval();before=factory.state_digest(model)
        stage='inference'
        evidence={'predictions':predictions,'batches':batches,'hashes':hashes}
        predictions,batches,hashes,interrupted=evaluate(model,plan['records'],plan['input_base'],factory,output,evidence)
        require(factory.state_digest(model)==before,'Classifier mutated during inference')
        result.update(model_state_unchanged=True,model_state_sha256=before,
                      status='completed' if all(p['status']=='ok' for p in predictions) else 'completed_with_failures')
        if interrupted:result['status']='interrupted'
    except BaseException as error:  # noqa: BLE001 -- keep complete planned denominator even setup failure
        result.update(status='failed',failure_stage=stage,error={'type':type(error).__name__,'message':str(error)})
        if not isinstance(error,Exception):interrupted=error
    finally:
        try:
            verify_plan(plan_path,plan)
            require(sha(approval_path)==approval_sha,'Approval changed')
            result['final_integrity_passed']=True
        except Exception as error:  # noqa: BLE001 -- mutation invalidates completion
            result.update(status='failed_integrity',final_integrity_passed=False,integrity_error={'type':type(error).__name__,'message':str(error)})
        if not (output/'raw.jsonl').exists():
            with (output/'raw.jsonl').open('x') as stream:
                for pred in predictions:stream.write(canonical(pred)+'\n')
        write_new(output/'predictions.json',predictions);write_new(output/'batches.json',batches);write_new(output/'tensor_hashes.json',hashes)
        write_new(output/'analysis.json',summarize(plan['records'],predictions))
        result.update(actual_forward_calls_started=sum(b['actual_forward_started'] for b in batches),
                      actual_forward_calls_returned=sum(b['actual_forward_returned'] for b in batches),
                      status_counts=dict(Counter(p['status'] for p in predictions)),
                      timing={'wall_seconds':time.perf_counter()-start,'model_seconds':sum(b['model_seconds'] or 0 for b in batches),
                              'decode_tensor_seconds':sum(b['decode_tensor_seconds'] or 0 for b in batches),
                              'scope':'This standalone oracle-ROI component only; model includes MPS sync/softmax, total includes loading/hash/decode, not system end-to-end.'})
        inventory={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(output.iterdir()) if p.is_file()}
        write_new(output/'artifact_inventory.json',inventory)
        result.update(finished_at_utc=datetime.now(UTC).isoformat(),artifact_inventory_sha256=sha(output/'artifact_inventory.json'))
        write_new(output/'run.json',result)
    if interrupted:raise interrupted
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('preflight','run'))
    parser.add_argument('--project-root',type=Path,default=ROOT);parser.add_argument('--prepared',type=Path)
    parser.add_argument('--expected-prepared-sha256');parser.add_argument('--metadata',type=Path)
    parser.add_argument('--plan',type=Path);parser.add_argument('--expected-plan-sha256')
    parser.add_argument('--approval',type=Path);parser.add_argument('--expected-approval-sha256')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.command=='preflight':
        require(all((args.prepared,args.expected_prepared_sha256,args.metadata)),'Preparation binding required')
        result=preflight(args.project_root,args.prepared,args.expected_prepared_sha256,args.metadata,args.output)
    else:
        require(all((args.plan,args.expected_plan_sha256,args.approval,args.expected_approval_sha256)),'Bound root inference approval required')
        result=run(args.plan,args.expected_plan_sha256,args.approval,args.expected_approval_sha256,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['status'] in ('prepared_not_authorized','completed') else 1


if __name__=='__main__':raise SystemExit(main())
