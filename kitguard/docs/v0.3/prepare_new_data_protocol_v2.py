"""CPU-only, annotation-derived candidate audit. Does not load any model or modify v0.2.
Sources are unchanged author images and labels. Only writes v0.3 manifests/docs.
Creates lossless derived crops only after all author-box inclusion rules pass; raw files remain untouched.
"""
from __future__ import annotations
import collections
import datetime as dt
import hashlib
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'datasets/manifests/v0.3/source_grouped_v2'
OUT.mkdir(parents=True,exist_ok=True)
DERIVED = ROOT / 'datasets/derived/v0.3/screws_views'
DERIVED.mkdir(parents=True,exist_ok=True)
from PIL import Image
SEED = 'KitGuard-v0.3-source-grouped-crops-20260926-v2'
PARTS = ('bolt','nut','washer','bracket')
SIZES = ((768,576),(960,720),(1152,864),(1440,1080))
STRIDE, MARGIN = 64, 16
sha = lambda b: hashlib.sha256(b).hexdigest()
def load(p): return json.loads((ROOT/p).read_text())
def dump(name, obj):
    p=OUT/name
    if p.exists(): raise RuntimeError(f'Refuse to overwrite frozen v0.3 file {p}')
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    return {'path':str(p.relative_to(ROOT)),'sha256':sha(p.read_bytes())}
def key(*parts): return sha('|'.join((SEED,*map(str,parts))).encode())
def vec(c): return tuple(c[p] for p in PARTS)
def values(x):
    if isinstance(x,dict):
        for v in x.values(): yield from values(v)
    elif isinstance(x,list):
        for v in x: yield from values(v)
    elif isinstance(x,str): yield x

lpath='datasets/manifests/mvtec_loco_screw_bag/manifest.json'
spath='datasets/manifests/mvtec_screws/manifest.json'
oldpath='datasets/manifests/mvtec_loco_screw_bag/benchmark_v2.json'
loco,screws,old=load(lpath),load(spath),load(oldpath)
all_images=loco['images']+screws['images']
by_sha={x['sha256']:x for x in all_images}
assert len(by_sha)==len(all_images), 'Duplicate original file SHA across sources'
old64={x['sha256'] for x in old['cases']}
prior=collections.defaultdict(set)
# Strict exposure audit: identifiers only; no ranking by predictions or error outcomes.
for f in sorted((ROOT/'evaluation-runs').rglob('*.json*')):
    if '/source_snapshot/' in str(f): continue
    try:
        content=[json.loads(x) for x in f.read_text().splitlines() if x] if f.suffix=='.jsonl' else json.loads(f.read_text())
    except (ValueError,UnicodeError): continue
    for s in values(content):
        if s in by_sha: prior[s].add(str(f.relative_to(ROOT)))
        if 'screws_' in s:
            for im in screws['images']:
                if s.endswith('/'+Path(im['path']).name) or s==Path(im['path']).name:
                    prior[im['sha256']].add(str(f.relative_to(ROOT)))
# Prior figures/inspection: explicitly known observed original, not inference result selection.
viewed=[x for x in screws['images'] if Path(x['path']).name=='screws_022.png']
for x in viewed: prior[x['sha256']].add('docs/DATA_PROVENANCE.md: prior visually inspected example')
excluded=old64|set(prior)
remaining_loco=[x for x in loco['images'] if x['kitguard_eligible'] and x['sha256'] not in excluded]
normal=[x for x in remaining_loco if x['upstream_kind']=='good']
anomaly=[x for x in remaining_loco if x['upstream_kind']!='good']
# Last clear quantity anomalies are reserved; balanced normal set from untouched official test.
normal_test=sorted((x for x in normal if x['upstream_split']=='test'),key=lambda x:key('loco',x['sha256']))
anomaly=sorted(anomaly,key=lambda x:key('loco',x['sha256']))
loco_hold=[x for pair in itertools.zip_longest(normal_test[:len(anomaly)],anomaly) for x in pair if x]
loco_cases=[]
for x in loco_hold:
    loco_cases.append({'id':'v03-new-loco-'+x['id'].replace('/','-'),'image':x['path'].removeprefix('datasets/'),
    'sha256':x['sha256'],'source_id':'mvtec-loco-ad:'+x['id'],'split':'holdout','ground_truth':x['kitguard_counts'],
    'upstream_split':x['upstream_split'],'upstream_kind':x['upstream_kind'],
    'subgroup':'normal_constant_222' if x['upstream_kind']=='good' else 'quantity_anomaly',
    'ground_truth_basis':x['ground_truth_basis'],'source_masks':x['source_masks'],
    'nominal_requirements':dict(zip(PARTS,(2,2,2,0))), 'v03_new_source':True})

coco=load(screws['upstream_annotation_path'])
ann_by_image=collections.defaultdict(list)
for a in coco['annotations']: ann_by_image[a['image_id']].append(a)
images_by_name={x['file_name']:x for x in coco['images']}
assert len(images_by_name)==384 and len(coco['annotations'])==4427
mapping={int(k):v for k,v in screws['category_mapping'].items()}
# README defines row/col center, full width/height, mathematical positive angle.
def author_box(a):
    row,col,w,h,phi=a['bbox']
    assert all(math.isfinite(v) for v in a['bbox']) and w>0 and h>0
    dx=abs(math.cos(phi))*w/2+abs(math.sin(phi))*h/2
    dy=abs(math.sin(phi))*w/2+abs(math.cos(phi))*h/2
    return (col-dx,row-dy,col+dx,row+dy)
def coords(end): return sorted(set(range(0,end+1,STRIDE))|{end})
catalog=[]; rejected_sources=[]; original_stats=[]
for im in screws['images']:
    cname=Path(im['path']).name; c=images_by_name[cname]
    anns=ann_by_image[c['id']]
    boxes=[(a,author_box(a)) for a in anns]
    causes=[]
    if im['sha256'] in excluded: causes.append('prior_v02_exposure')
    if any(b[0]<0 or b[1]<0 or b[2]>c['width'] or b[3]>c['height'] for _,b in boxes): causes.append('author_box_extends_outside_original')
    if causes:
        rejected_sources.append({'source_image':im['path'],'source_sha256':im['sha256'],'reasons':causes})
        continue
    # Deduplicate by retained annotation identities. Larger context wins before SHA tie-break.
    chosen={}; accepted_rectangles=0
    for cw,ch in SIZES:
        for left in coords(c['width']-cw):
            for top in coords(c['height']-ch):
                right,bottom=left+cw,top+ch; included=[]; unsafe=False
                for a,b in boxes:
                    padded=(b[0]-MARGIN,b[1]-MARGIN,b[2]+MARGIN,b[3]+MARGIN)
                    inside=padded[0]>=left and padded[1]>=top and padded[2]<=right and padded[3]<=bottom
                    outside=padded[2]<=left or padded[0]>=right or padded[3]<=top or padded[1]>=bottom
                    if inside: included.append(a)
                    elif not outside: unsafe=True; break
                if unsafe or not included: continue
                cnt=dict.fromkeys(PARTS,0)
                for a in included: cnt[mapping[a['category_id']]]+=1
                if max(cnt.values())>3 or not 1<=sum(cnt.values())<=12: continue
                ids=tuple(sorted(a['id'] for a in included)); crop=(left,top,right,bottom)
                rank=(-cw*ch,key(im['sha256'],*crop))
                if ids in chosen and chosen[ids][0]<=rank: continue
                accepted_rectangles+=1
                rec={'id':'v03-screws-'+Path(cname).stem+'-'+key(im['sha256'],*crop)[:12],
                  'source_image':im['path'].removeprefix('datasets/'),'source_sha256':im['sha256'],
                  'source_id':'mvtec-screws:'+cname,'source_width':c['width'],'source_height':c['height'],
                  'upstream_split':im['upstream_split'],'proposed_split':'development' if int(key('source-split',im['sha256']),16)%2==0 else 'holdout',
                  'crop_xyxy':list(crop),'width':cw,'height':ch,'included_annotation_ids':list(ids),
                  'excluded_annotation_ids':[a['id'] for a in anns if a['id'] not in ids],
                  'ground_truth':cnt,'category_counts':dict(collections.Counter(str(a['category_id']) for a in included)),
                  'real_source_photo':True,'derived_view':True,'pixel_transform':'axis-aligned integer crop only; no resize/rotation/compositing/deletion',
                  'ground_truth_basis':'Count of wholly contained original author oriented boxes after taxonomy projection; every other padded AABB wholly outside crop',
                  'annotation_source':screws['upstream_annotation_path'],'annotation_sha256':screws['upstream_annotation_sha256'],
                  'all_source_annotations':[{'id':a['id'],'category_id':a['category_id'],'bbox_row_col_width_height_phi':a['bbox'],'conservative_aabb_xyxy':list(b)} for a,b in boxes]}
                chosen[ids]=(rank,rec)
    rows=[r for _,r in chosen.values()]
    catalog.extend(rows)
    original_stats.append({'source_image':im['path'],'source_sha256':im['sha256'],'upstream_split':im['upstream_split'],
      'unique_instance_subsets':len(rows),'count_vectors':sorted(set(vec(r['ground_truth']) for r in rows))})
# Select at most one derived view per original. Balance supported count vectors without using images or model outcomes.
def balanced_select(pool,target,tag):
    by_vector=collections.defaultdict(list)
    for r in pool: by_vector[vec(r['ground_truth'])].append(r)
    for v in by_vector: by_vector[v].sort(key=lambda r:key(tag,r['source_sha256'],r['id']))
    selected=[]; used=set(); histogram=collections.Counter()
    while len(selected)<target:
        available=[v for v,rows in by_vector.items() if any(r['source_sha256'] not in used for r in rows)]
        if not available: break
        v=min(available,key=lambda x:(histogram[x],key(tag,'count-vector',*x)))
        r=next(r for r in by_vector[v] if r['source_sha256'] not in used)
        selected.append(r); used.add(r['source_sha256']); histogram[v]+=1
    return sorted(selected,key=lambda r:key(tag,'final-order',r['source_sha256']))
sdev=balanced_select([r for r in catalog if r['proposed_split']=='development'],12,'development')
shold=balanced_select([r for r in catalog if r['proposed_split']=='holdout'],32,'holdout')
assert not ({r['source_sha256'] for r in sdev}&{r['source_sha256'] for r in shold})
assert len({r['source_sha256'] for r in sdev+shold})==len(sdev+shold)
assert not ({r['source_sha256'] for r in sdev+shold}|{r['sha256'] for r in loco_cases}) & excluded
# Independently recheck label/source joins and each complete-box inclusion for selected views.
for r in sdev+shold:
    left,top,right,bottom=r['crop_xyxy']; counts=dict.fromkeys(PARTS,0)
    for a in r['all_source_annotations']:
        x1,y1,x2,y2=a['conservative_aabb_xyxy']
        inside=x1-MARGIN>=left and y1-MARGIN>=top and x2+MARGIN<=right and y2+MARGIN<=bottom
        outside=x2+MARGIN<=left or x1-MARGIN>=right or y2+MARGIN<=top or y1-MARGIN>=bottom
        assert inside or outside
        assert inside==(a['id'] in r['included_annotation_ids'])
        if inside: counts[mapping[a['category_id']]]+=1
    assert counts==r['ground_truth']
    assert sha((ROOT/'datasets'/r['source_image']).read_bytes())==r['source_sha256']
for r in loco_cases:
    assert sha((ROOT/'datasets'/r['image']).read_bytes())==r['sha256']
    for m in r['source_masks']: assert sha((ROOT/m['path']).read_bytes())==m['sha256']

pixel_hashes={}; pixel_groups=collections.defaultdict(list)
for x in all_images:
    with Image.open(ROOT/x['path']) as im:
        im.load(); rgb=im.convert('RGB'); digest=sha(str(rgb.size).encode()+b'|RGB|'+rgb.tobytes())
    pixel_hashes[x['sha256']]=digest
    pixel_groups[digest].append(x['sha256'])
old_pixels={pixel_hashes[h] for h in excluded}
selected_originals={r['source_sha256'] for r in sdev+shold}|{r['sha256'] for r in loco_cases}
assert not {pixel_hashes[h] for h in selected_originals}&old_pixels, 'Exact decoded-pixel overlap with v0.2'
assert len({pixel_hashes[h] for h in selected_originals})==len(selected_originals), 'Duplicate selected source pixel content'
materialized=[]
for r in sdev+shold:
    p=DERIVED/(r['id']+'.png')
    if p.exists(): raise RuntimeError(f'Refuse to overwrite derived image {p}')
    with Image.open(ROOT/'datasets'/r['source_image']) as im:
        im.load(); view=im.convert('RGB').crop(r['crop_xyxy']); pixel_bytes=view.tobytes()
        view.save(p,format='PNG',compress_level=6)
    with Image.open(p) as stored:
        stored.load(); assert stored.mode=='RGB' and stored.size==(r['width'],r['height']) and stored.tobytes()==pixel_bytes
    materialized.append({'id':r['id'],'image':str(p.relative_to(ROOT/'datasets')),'sha256':sha(p.read_bytes()),
      'source_id':r['source_id'],'split':r['proposed_split'],'ground_truth':r['ground_truth'],
      'subgroup':'screws_author_safe_crop','source_image':r['source_image'],'source_sha256':r['source_sha256'],
      'source_decoded_rgb_sha256':pixel_hashes[r['source_sha256']],'crop_xyxy':r['crop_xyxy'],
      'crop_pixel_sha256':sha(pixel_bytes),'original_pixel_equality_verified':True,'derived_view':True,
      'included_annotation_ids':r['included_annotation_ids'],'upstream_split':r['upstream_split'],
      'ground_truth_basis':r['ground_truth_basis'],'annotation_source':r['annotation_source'],
      'annotation_sha256':r['annotation_sha256'],'bbox_margin_px':MARGIN})
now=dt.datetime.now(dt.timezone.utc).isoformat()
common={'created_at_utc':now,'selection_seed':SEED,'license':'CC BY-NC-SA 4.0',
 'status':'data_selection_only_no_v03_model_inference','prior_model_results_used_for_selection':False}
receipts={}
receipts['exclusion']=dump('prior_exposure_exclusions.json',{**common,'v02_loco_manifest':oldpath,'v02_loco_manifest_sha256':sha((ROOT/oldpath).read_bytes()),'v02_loco_64_sha256':sorted(old64),'prior_source_records':[{'sha256':h,'source_path':by_sha[h]['path'],'evidence_files':sorted(v)} for h,v in sorted(prior.items())],'excluded_unique_sources':len(excluded)})
receipts['loco_pool']=dump('loco_unused_candidate_inventory.json',{**common,'source_manifest':lpath,'source_manifest_sha256':sha((ROOT/lpath).read_bytes()),'images':remaining_loco})
receipts['loco_holdout']=dump('loco_new_holdout_v1.json',{**common,'schema_version':1,'name':'v0.3 unseen-by-team LOCO source holdout','dataset_root':'datasets','selection_frozen_at_utc':now,'cases':loco_cases,'limitations':['Same acquisition domain as v0.2, not independent factory/scene sampling.','Public-model pretraining overlap unknown.','Only 16 unused quantity anomalies; no remaining 2/3/2 case.','Normal images have constant 2/2/2/0 composition; report separately.']})
receipts['pixel_audit']=dump('decoded_pixel_duplicate_audit.json',{**common,'images_checked':len(all_images),'method':'SHA256(width,height encoded + RGB mode marker + decoded RGB pixels); detects exact content only, not near duplicate scenes','duplicate_groups':{h:v for h,v in pixel_groups.items() if len(v)>1},'selected_source_overlap_with_old_pixels':0,'selected_sources_unique_pixel_content':len(selected_originals),'all_original_pixel_hashes':pixel_hashes})
receipts['runner_manifest']=dump('screws_safe_crops_benchmark_v1.json',{**common,'schema_version':1,'name':'v0.3 source-grouped exact-pixel Screws crops','dataset_root':'datasets','selection_frozen_at_utc':now,'cases':materialized,'split_rule':'Before crop generation: SHA256(seed|source-split|source_image_SHA) integer modulo 2; even development, odd holdout; original official split retained for disclosure','limitations':['Derived views from public original photos, not new independent scenes or full original-image performance.','One view per source. No original source or exact original pixels overlap between new splits or any prior v0.2 listed source.','No washer or bracket positives; broad screw/nut class projection, not SKU verification.','Source images share acquisition domain and possibly session/objects; source IDs alone do not establish population independence.','No author nominal order exists; do not fabricate a manufacturer BOM or nominal-order anomaly metric.']})
receipts['crop_catalog']=dump('screws_crop_candidate_catalog.json',{**common,'schema':'kitguard.author-annotation-crop-spec.v1','ordinary_benchmark_compatible':False,'materialized':False,'source_manifest':spath,'source_manifest_sha256':sha((ROOT/spath).read_bytes()),'sizes':SIZES,'grid_stride':STRIDE,'bbox_margin_px':MARGIN,'bbox_format':'author row,col,width,height,phi radians; not standard COCO xywh','rejected_sources':rejected_sources,'source_counts':original_stats,'views':catalog})
for name,rows in [('screws_new_development_crop_specs_v1.json',sdev),('screws_new_holdout_crop_specs_v1.json',shold)]:
 receipts[name]=dump(name,{**common,'schema':'kitguard.author-annotation-crop-spec.v1','ordinary_benchmark_compatible':False,'materialized':False,'selection_frozen_at_utc':now,'one_view_per_original_source':True,'views':rows,'materialization_required':'Before benchmark, create exact integer RGB crops, store crop hash and raw-pixel equality check, then write a runner-compatible manifest. Source path is never a cropped-image input.'})
summary={**common,'sources':{'loco':{'author_url':loco['author_page'],'archive_sha256':loco['archive_sha256']},'screws':{'author_url':screws['author_page'],'archive_sha256':screws['archive_sha256'],'annotation_sha256':screws['upstream_annotation_sha256']}},
 'loco_unused':{'images':len(remaining_loco),'normal':len(normal),'quantity_anomaly':len(anomaly),'count_vectors':{str(k):v for k,v in collections.Counter(vec(x['kitguard_counts']) for x in remaining_loco).items()},'new_holdout_images':len(loco_cases)},
 'screws':{'prior_source_excluded':sum(x['sha256'] in excluded for x in screws['images']),'out_of_bounds_sources':sum('author_box_extends_outside_original' in x['reasons'] for x in rejected_sources),'out_of_bounds_instances':sum(any(v for v in [b[0]<0,b[1]<0,b[2]>1920,b[3]>1440]) for a in coco['annotations'] for b in [author_box(a)]),'total_rejected_sources':len(rejected_sources),'candidate_views':len(catalog),'candidate_sources':sum(x['unique_instance_subsets']>0 for x in original_stats),'selected_source_partition_rule':'SHA(seed|source-split|source-SHA) modulo 2, before crop filtering; custom source grouping, not official test', 'candidate_source_splits':dict(collections.Counter(x['upstream_split'] for x in original_stats if x['unique_instance_subsets']>0)),'candidate_count_vectors':{str(k):v for k,v in sorted(collections.Counter(vec(x['ground_truth']) for x in catalog).items())},'selected_dev_sources':len(sdev),'selected_holdout_sources':len(shold),'dev_count_vectors':{str(k):v for k,v in sorted(collections.Counter(vec(x['ground_truth']) for x in sdev).items())},'holdout_count_vectors':{str(k):v for k,v in sorted(collections.Counter(vec(x['ground_truth']) for x in shold).items())}},
 'checks':{'original_file_hash_duplicates':0,'v02_source_overlap':0,'new_dev_holdout_source_overlap':0,'selected_clipped_author_boxes':0,'selected_source_files_rehashed':len(sdev)+len(shold)+len(loco_cases),'no_model_run':True,'selected_decoded_pixel_duplicates':0,'old_decoded_pixel_overlap':0,'no_raw_images_modified':True,'derived_image_count':len(sdev)+len(shold)},'files':receipts,
 'script':{'path':'docs/v0.3/prepare_new_data_protocol_v2.py','sha256':sha(Path(__file__).read_bytes())}}
dump('DATA_PROTOCOL_SUMMARY.json',summary)
print(json.dumps({k:summary[k] for k in ['loco_unused','screws','checks']},ensure_ascii=False,indent=2))
