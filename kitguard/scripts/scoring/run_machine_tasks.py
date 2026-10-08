"""Prospective live machine tasks, separate from human and image-accuracy studies.

The unversioned control replays the same saved model observations. It is a
workflow ablation, not a competitor or an independent visual model.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import httpx

from kitguard.digital_review_state import current_digital_check
from kitguard.public_demo_catalog import CATALOG

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'test-results/scoring-v1/machine-tasks'
PROTOCOL={'name':'five_machine_goal_tasks_v1','classification':'prospective_engineering_tasks_on_exposed_images',
 'human_participants':0,'physical_completions':0,'new_image_accuracy_denominator':0,
 'observer':'unchanged spatial_guarded_1536 MLX Qwen3.6-27B-4bit',
 'control':'CPU workflow ablation: latest stored check without version binding, using the same real saved MLX observations. Not an independent model or service.',
 'timing':'Whole mission server monotonic; control replay time is not compared to model inference or a human.',
 'cases':[{'id':'quantity','sample':'mixed-screws','bom':{'bolt':2,'nut':0,'washer':0,'bracket':0},'expected':'quantity_difference'},
          {'id':'uncertain','sample':'small-part','bom':{'bolt':2,'nut':1,'washer':0,'bracket':0},'expected':'needs_more_evidence'},
          {'id':'matching','sample':'bag-revision','bom':{'bolt':2,'nut':2,'washer':2,'bracket':0},'expected':'quantities_match'},
          {'id':'changed_bom','sample':'bag-revision','bom':{'bolt':3,'nut':2,'washer':2,'bracket':0},'expected':'reject_stale_goal_then_fresh_check'},
          {'id':'physical_source','sample':None,'bom':{'bolt':1,'nut':0,'washer':0,'bracket':0},'expected':'reject_physical_goal'}],
 'success':'Predeclared workflow outcome matches expected routing/refusal, every attempted case retained. Not ground-truth image accuracy.',
 'limits':['Only 3 known source photos. Goals do not receive author truth.','One deterministic ablation exposes the binding mechanism, not market-wide superiority.','No human productivity, willingness-to-pay, repeated deployment or statistical population claim.']}

def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def binding(order,key):return {'scenario':'order','request_key':key,'order_id':order['id'],'expected_revision':order['revision'],'expected_evidence_epoch':order['evidence_epoch'],'expected_photo_id':order['photos'][-1]['id']}

def upload(client,spec):
 catalog=next(s for s in CATALOG if s['sample_id']==spec['sample'])
 raw=(ROOT/'datasets'/catalog['image']).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=catalog['source_sha256']:raise RuntimeError('Public source hash mismatch')
 metadata={'title':'[MACHINE TASK] '+spec['id'],'requirements':spec['bom'],'confirmed_digital_only':True,
 'source_note':'Automated engineering use of an exposed public development photo; not a user study. '+catalog['source_case_id'],
 'source_url':catalog['source_url'],'license_note':catalog['license']}
 r=client.post('/api/photo-documents',data={'metadata':json.dumps(metadata)},files={'photo':('public.png',raw,'image/png')});r.raise_for_status();return r.json()['order']

def wait(client,run_id):
 for _ in range(1800):
  r=client.get('/api/autonomous-missions/'+run_id);r.raise_for_status();run=r.json()['run']
  if run['status']!='running':return run
  time.sleep(.4)
 raise RuntimeError('Mission exceeded 12 minutes')

def run_one(client,spec,order,index):
 r=client.post('/api/autonomous-missions',json=binding(order,'machine_goal_v1_'+spec['id']));r.raise_for_status()
 run=wait(client,r.json()['run']['id']);save(OUT/(spec['id']+'-run.json'),run)
 case=run['cases'][0];result={'id':spec['id'],'status':run['status'],'mission_id':run['id'],'order_id':order['id'],
 'finding':case['finding'],'planned_checks':run['planned_checks'],'actual_checks':len(case['checks']),'elapsed_ms':run['elapsed_ms'],
 'workflow_success':run['status']=='completed' and case['finding']==spec['expected']}
 index.append(result);save(OUT/'progress.json',index);return run

def main():
 parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['prepare','finish']);args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
 with httpx.Client(base_url='http://127.0.0.1:8765',timeout=20) as client:
  if args.phase=='prepare':
   if (OUT/'protocol.json').exists():raise RuntimeError('Protocol already locked; do not silently overwrite or reset trials')
   save(OUT/'protocol.json',PROTOCOL);(OUT/'protocol.sha256').write_text(hashlib.sha256((OUT/'protocol.json').read_bytes()).hexdigest()+'\n')
   order=upload(client,PROTOCOL['cases'][0]);save(OUT/'quantity-input.json',order)
   print('Prepared G1 order',order['id'],'start once through the browser; protocol locked before execution.')
   return
  protocol=json.loads((OUT/'protocol.json').read_text());assert protocol==PROTOCOL
  first=json.loads((OUT/'quantity-input.json').read_text());runs=client.get('/api/autonomous-missions').json()['runs']
  found=[]
  for row in runs:
   candidate=client.get('/api/autonomous-missions/'+row['id']).json()['run']
   if candidate['cases'][0].get('order_id')==first['id']:found.append(candidate)
  if len(found)!=1:raise RuntimeError('Exactly one browser-started G1 is required')
  g1=wait(client,found[0]['id']);save(OUT/'quantity-run.json',g1)
  index=[{'id':'quantity','status':g1['status'],'mission_id':g1['id'],'order_id':first['id'],'finding':g1['cases'][0]['finding'],'planned_checks':1,'actual_checks':len(g1['cases'][0]['checks']),'elapsed_ms':g1['elapsed_ms'],'workflow_success':g1['status']=='completed' and g1['cases'][0]['finding']=='quantity_difference'}]
  for spec in PROTOCOL['cases'][1:3]:
   order=upload(client,spec);run=run_one(client,spec,order,index);print(spec['id'],run['status'],run['cases'][0]['finding'],flush=True)
   if spec['id']=='matching':matching=run
  original=matching['cases'][0]['snapshot'];spec=PROTOCOL['cases'][3]
  r=client.post('/api/orders/'+original['id']+'/revise',json={'expected_revision':original['revision'],'requirements':spec['bom'],'instruction':'PREDECLARED MACHINE TASK: incoming R2, not AI-derived correction'});r.raise_for_status();changed=r.json()['order']
  # Same-pixels replay is explicit digital simulation, never a new photo/capture.
  stale=client.post('/api/autonomous-missions',json=binding(original,'machine_stale_goal_v1'))
  before={'stale_request_status':stale.status_code,'stale_request_detail':stale.json(),'order':changed,
          'unversioned_control_accepts_old_ready':changed['latest_check']['decision']=='ready',
          'version_aware_guard_accepts_old_ready':current_digital_check(changed) is not None}
  save(OUT/'changed-bom-before.json',before)
  r=client.post('/api/orders/'+original['id']+'/public-replay',json={'expected_revision':changed['revision'],'expected_photo_id':changed['photos'][-1]['id'],'expected_evidence_epoch':changed['evidence_epoch'],'confirmed_no_physical_capture':True,'idempotency_key':'machine_R2_replay_v1'});r.raise_for_status();changed=r.json()['order']
  revised_spec={**spec,'expected':'quantity_difference'};run=run_one(client,revised_spec,changed,index)
  index[-1]['workflow_success'] &= stale.status_code==409 and before['version_aware_guard_accepts_old_ready'] is False
  index[-1]['stale_refusal']=stale.status_code;save(OUT/'progress.json',index)
  spec=PROTOCOL['cases'][4];r=client.post('/api/orders',json={'title':'[MACHINE TASK] excluded physical scope','requirements':spec['bom']});r.raise_for_status();physical=r.json()['order']
  request={'scenario':'order','request_key':'machine_physical_refusal_v1','order_id':physical['id'],'expected_revision':1,'expected_evidence_epoch':0,'expected_photo_id':'no-digital-photo'}
  r=client.post('/api/autonomous-missions',json=request);save(OUT/'physical-source-refusal.json',{'request':request,'status':r.status_code,'response':r.json()})
  index.append({'id':'physical_source','status':'policy_refused','mission_id':None,'order_id':physical['id'],'finding':None,'planned_checks':0,'actual_checks':0,'elapsed_ms':None,'workflow_success':r.status_code==409})
  save(OUT/'progress.json',index)
  result={'protocol_sha256':hashlib.sha256((OUT/'protocol.json').read_bytes()).hexdigest(),'planned_tasks':5,'tasks':index,'workflow_outcomes_met':sum(x['workflow_success'] for x in index),'real_mlx_checks':sum(x['actual_checks'] for x in index),'new_image_accuracy_denominator':0,'human_participants':0,'physical_completions':0,'ablation':{k:v for k,v in before.items() if k!='order'},'limits':PROTOCOL['limits']}
  save(OUT/'RESULTS.json',result);print(json.dumps({k:v for k,v in result.items() if k in ['planned_tasks','workflow_outcomes_met','real_mlx_checks']},ensure_ascii=False))
if __name__=='__main__':main()
