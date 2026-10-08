"""Independent CPU-only audit and canonical manifest. Does not run a vision model."""
from pathlib import Path
import collections, datetime as dt, hashlib, itertools, json, math, os, tempfile
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'datasets/manifests/v0.3'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads((ROOT/p).read_text())
def write(name,x):
 p=OUT/name
 if p.exists():raise RuntimeError(f'Refuse overwrite: {p}')
 p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
 return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
loco_path='datasets/manifests/v0.3/loco_new_holdout_v1.json'
screws_path='datasets/manifests/v0.3/source_grouped_v2/screws_safe_crops_benchmark_v1.json'
loco=load(loco_path);screws=load(screws_path)
assert len(loco['cases'])==32 and len(screws['cases'])==44
# Preserve the first LOCO 32 selection, rather than changing its normal sample under the crop-v2 seed.
cases=screws['cases']+loco['cases']
assert collections.Counter(r['split'] for r in cases)=={'development':12,'holdout':64}
manifest={'schema_version':1,'name':'KitGuard v0.3 source-disjoint public data verification','created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
 'dataset_root':'datasets','selection_frozen_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
 'status':'data_selection_frozen_model_protocol_not_yet_selected','sources':[{'path':p,'sha256':sha(ROOT/p)} for p in [loco_path,screws_path]],
 'cases':cases,'limitations':['LOCO is a fresh source-image subset of the same acquisition domain, not a new factory.','Screws consists of exact-pixel author-box-derived views, one per new source, not full-source-image or field performance.','Report separate LOCO-normal, LOCO-quantity-anomaly, Screws strata; do not merge all into one industrial accuracy claim.','The complete 16/48 v0.2 set is now development/regression evidence, never an unseen holdout for v0.3.','Public pretraining exposure and physical acquisition-session independence remain unknown.']}
combined_path=OUT/'CANONICAL_NEW_SOURCE_BENCHMARK_V1.json'
if combined_path.exists():
 existing=json.loads(combined_path.read_text());assert existing['cases']==cases and existing['sources']==manifest['sources']
 manifest=existing;combined={'path':str(combined_path.relative_to(ROOT)),'sha256':sha(combined_path)}
else:combined=write('CANONICAL_NEW_SOURCE_BENCHMARK_V1.json',manifest)
# Import canonical app validator with an isolated throwaway store. No observer call or load.
with tempfile.TemporaryDirectory(prefix='validator-store-',dir=OUT) as d:
 os.environ['KITGUARD_DATA_DIR']=d
 import sys
 sys.path.insert(0,str(ROOT))
 from kitguard.evaluation import read_manifest, validate_case
 parsed=read_manifest(ROOT/combined['path'])
 for r in parsed['cases']: validate_case(r,ROOT/'datasets')

orig_s=load('datasets/manifests/mvtec_screws/manifest.json')
orig_l=load('datasets/manifests/mvtec_loco_screw_bag/manifest.json')
coco=load(orig_s['upstream_annotation_path']);anns={x['id']:x for x in coco['annotations']}
ann_by_img=collections.defaultdict(list)
for a in coco['annotations']:ann_by_img[a['image_id']].append(a)
images={r['file_name']:r for r in coco['images']}
map_cls={int(k):v for k,v in orig_s['category_mapping'].items()}
old=load('datasets/manifests/v0.3/prior_exposure_exclusions.json')
exclude=set(old['v02_loco_64_sha256'])|{r['sha256'] for r in old['prior_source_records']}
source_hashes=[r.get('source_sha256',r['sha256']) for r in cases]
assert len(set(source_hashes))==76 and not set(source_hashes)&exclude
pixel_audit=load('datasets/manifests/v0.3/source_grouped_v2/decoded_pixel_duplicate_audit.json')
pixels=pixel_audit['all_original_pixel_hashes']
assert len({pixels[h] for h in source_hashes})==76
assert not {pixels[h] for h in source_hashes}&{pixels[h] for h in exclude}
# Use explicitly rotated corners as a second calculation, not the generation AABB formula.
margin_distances=[]; bytes_total=0
for r in screws['cases']:
 src=ROOT/'datasets'/r['source_image'];out=ROOT/'datasets'/r['image']
 assert sha(src)==r['source_sha256'] and sha(out)==r['sha256']
 imeta=images[src.name];counts=dict.fromkeys(('bolt','nut','washer','bracket'),0);included=[]
 l,t,rr,b=r['crop_xyxy']
 for a in ann_by_img[imeta['id']]:
  row,col,w,h,p=a['bbox']
  corners=[(col+sx*w/2*math.cos(p)+sy*h/2*math.sin(p),row-sx*w/2*math.sin(p)+sy*h/2*math.cos(p)) for sx,sy in itertools.product([-1,1],repeat=2)]
  x1,y1=min(q[0] for q in corners),min(q[1] for q in corners)
  x2,y2=max(q[0] for q in corners),max(q[1] for q in corners)
  inside=x1-16>=l and y1-16>=t and x2+16<=rr and y2+16<=b
  outside=x2+16<=l or x1-16>=rr or y2+16<=t or y1-16>=b
  assert inside or outside,(r['id'],a['id'])
  if inside:
   counts[map_cls[a['category_id']]]+=1; included.append(a['id'])
   margin_distances.append(min(x1-l,y1-t,rr-x2,b-y2))
 assert counts==r['ground_truth'] and sorted(included)==r['included_annotation_ids']
 with Image.open(src) as im,Image.open(out) as cropped:
  im.load();cropped.load();expected=im.convert('RGB').crop(r['crop_xyxy'])
  assert cropped.mode=='RGB' and cropped.size==expected.size and cropped.tobytes()==expected.tobytes()
 bytes_total+=out.stat().st_size
# Author attribution/license files and annotation files are pinned independently.
license_files=[]
for source in [orig_s,orig_l]:
 p=ROOT/source['upstream_readme_path'];assert sha(p)==source['upstream_readme_sha256']
 assert 'Attribution-NonCommercial-ShareAlike 4.0' in p.read_text(errors='replace') and 'creativecommons.org/licenses/by-nc-sa/4.0/' in p.read_text(errors='replace')
 license_files.append({'path':source['upstream_readme_path'],'sha256':sha(p),'license':'CC BY-NC-SA 4.0'})
assert sha(ROOT/orig_s['upstream_annotation_path'])==orig_s['upstream_annotation_sha256']
# Optional deterministic order panels are software scenarios, not extra photos or author BOMs.
orders={}
for domain,active in [('screws',['bolt','nut']),('loco',['bolt','nut','washer'])]:
 values=[]
 for v in itertools.product(range(4),repeat=len(active)):
  if not sum(v):continue
  values.append(dict(zip(('bolt','nut','washer','bracket'),[dict(zip(active,v)).get(p,0) for p in ('bolt','nut','washer','bracket')])))
 orders[domain]=values
order_file=write('OPTIONAL_RULE_ORDER_PANELS.json',{'schema':'kitguard.synthetic-order-rules.v1','actual_order_records':False,'adds_independent_photos':False,'must_not_be_passed_to_visual_observer':True,'note':'Optional exhaustive valid coarse-count order scenarios; use per-image any-false-ready to avoid denominator dilution. Author LOCO 222 nominal separately; no author nominal order for Screws.','orders':orders})
report={'created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'canonical_manifest':combined,'read_manifest_pass':True,'validate_case_passed':76,
 'domains':{'loco_original_holdout':32,'screws_derived_development':12,'screws_derived_holdout':32},
 'overlap_checks':{'old_v02_excluded_originals':len(exclude),'shared_original_with_v02':0,'shared_original_across_new_splits':0,'exact_decoded_original_pixel_overlap':0,'selected_originals':76},
 'geometry':{'author_coco_not_standard_xywh':True,'format':'row-center,col-center,full-width,full-height,phi-radians','rotated_corner_independent_recalculation':True,'minimum_included_box_to_crop_border_distance_px':min(margin_distances),'required_margin_px':16,'clipped_or_ambiguous_boxes':0},
 'pixel_integrity':{'verified_exact_source_rgb_crop_equality':44,'derived_png_bytes':bytes_total,'raw_files_modified':0},
 'source_licenses':license_files,'optional_rule_orders':order_file,'visual_review':{'development_contact_sheet':'docs/v0.3/SCREWS_DEVELOPMENT_CONTACT_SHEET.png','sha256':sha(ROOT/'docs/v0.3/SCREWS_DEVELOPMENT_CONTACT_SHEET.png'),'development_views_reviewed':12,'holdout_views_displayed_to_parent':0,'review_does_not_relabel_author_annotations':True},
 'no_model_loaded_or_called':True,'source_script':'docs/v0.3/validate_new_data_protocol.py','source_script_sha256':sha(Path(__file__))}
receipt=write('FINAL_DATA_AUDIT.json',report)
index={'authoritative_manifest':combined,'audit':receipt,'original_loco_selection_preserved':{'path':loco_path,'sha256':sha(ROOT/loco_path)},'screws_materialized_views':{'path':screws_path,'sha256':sha(ROOT/screws_path)},
 'development_contact_sheet':'docs/v0.3/SCREWS_DEVELOPMENT_CONTACT_SHEET.png','do_not_evaluate_alternatives':['datasets/manifests/v0.3/source_grouped_v2/loco_new_holdout_v1.json','datasets/manifests/v0.3/screws_new_development_crop_specs_v1.json','datasets/manifests/v0.3/screws_new_holdout_crop_specs_v1.json'],
 'alternative_note':'Exploration files are retained. The source-grouped crop-v2 script mechanically generated an alternative LOCO normal selection under its crop seed; it is not canonical. The very first LOCO32 is preserved in the combined benchmark. No alternative has been run through a model in this task.'}
write('CANONICAL_FILES.json',index)
print(json.dumps(report,ensure_ascii=False,indent=2))
