"""Conditional MANTA transfer ROI preparation; metadata first, no model calls.

metadata reads only fixed JSON/text sources and records historical image hashes.
prepare requires a separate root approval bound to a passed internal256 audit and
its unchanged epoch10 checkpoint. It crops all579 author targets, never detects.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import math
import platform
import shutil
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = 'scripts/v08/prepare_manta_transfer.py'
TEST = 'tests/test_manta_transfer_preparation_v08.py'
DRAFT = 'docs/v0.8/MANTA_CLASSIFIER_CROSS_SOURCE_PLAN_DRAFT.md'
SCREWS = 'datasets/derived/public_detector_v1/val.json'
SCREWS_MANIFEST = 'datasets/derived/public_detector_v1/manifest.json'
AUTHOR = 'datasets/raw/mvtec_screws_v1.0/mvtec_screws_val.json'
FOD = 'datasets/derived/v0.8/foda_grouped_v1/validation.json'
PREFLIGHT = 'training-runs/v0.8/grouped_detector_v1/preflight.json'
TRAIN_PROTOCOL = 'training-runs/v0.8/grouped_detector_v1/protocol.json'
PINNED = {
    SCREWS: 'cd2604d0d11bee0824188f287168490436085e150784a599822180edef311d66',
    SCREWS_MANIFEST: '27044ecee0fd81d3f29b7cb70c5c8252f08d6588cbba46d346388b2cf83adf23',
    AUTHOR: 'c746bee8f0ea2d48623960bcc41c80e02232914ca09bbf21928d924d22215599',
    FOD: '9eb41e12060da09732f9c5a1b1160feafcc98222e0d7cd836dd90aff5d6e958c',
    PREFLIGHT: 'f3e31e0420ef5b18e731484d9e0da58f5f51ca3c0479d7cdc064917622e1b63e',
    TRAIN_PROTOCOL: '0230682fac7d542cf6669a42a6ba274402747908795da874b80f1f33c54be24a',
    'docs/v0.8/MANTA_CLASSIFIER_PROTOCOL_V1.md': 'cbb3ca611bd4ba3be4c4a082f7d2b4d7b8319713bc3f04a2a62724acfa9a0959',
    'docs/v0.8/manta_classifier_freeze_v1/freeze.json': '226f739d011c5f4095888251b572663fd2c12a485c6b48d8c36e206553111f9e',
    'docs/v0.8/SCREWS_CATEGORY_SEMANTICS_REVIEW.md': '42acee3eea618463969ba2116b65b067a7d0e42eacaa30ce527b3e7e17622e27',
}
POLICY = {
    'population': 'all80 prior validation images/all579 author targets; no replacement or filtering',
    'order': 'original grouped detector preflight.validation image order then ground_truth order',
    'localization': 'oracle author annotation ROI, not independent proposal/detection',
    'coordinates': 'existing original-image continuous AABB xyxy; floor left/top, ceil right/bottom, clamp to image, PIL exclusive right/bottom',
    'margin': 0, 'rotation': 'none', 'tiny_short_side_threshold': 16,
    'preprocess': 'crop RGB→L→RGB; Pillow ImageOps.pad224 LANCZOS black centering(.5,.5)',
    'input_size': [224, 224], 'png': {'optimize': False, 'compress_level': 6},
    'normalization_mean': [.485, .456, .406], 'normalization_std': [.229, .224, .225],
    'classifier_epoch': 10, 'probability_threshold': .9,
    'bolt_control': 'open-category rejection only; unknown does not identify bolt',
    'failure': 'all579 retained as prepared/failed/not_attempted; no retry/drop/replacement',
    'exposure': 'previously exposed detector validation; no new holdout/physical independence claim',
    'production_change': False,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def safe_path(root, relative):
    root = Path(root).resolve()
    require(isinstance(relative, str) and not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'Unsafe path')
    path = root / relative
    require(path.resolve().is_relative_to(root) and not any(p.is_symlink() for p in [path, *path.parents]), 'Symlink/escape')
    return path


def pixel_sha(image):
    return digest(canonical({'mode': image.mode, 'size': list(image.size)}).encode() + b'\0' + image.tobytes())


def pillow_runtime():
    base = Path(importlib.util.find_spec('PIL').origin).parent
    paths = {base / x for x in ('Image.py', 'ImageOps.py', 'ImageFile.py', 'PngImagePlugin.py', 'JpegImagePlugin.py')}
    paths.update(base.glob('_imaging*.so'))
    return {'python': sys.version, 'platform': platform.platform(), 'pillow': importlib.metadata.version('Pillow'),
            'files': {str(p): sha(p) for p in sorted(paths)}}


def integer_crop(box, size):
    require(len(box) == 4 and all(type(x) in (float, int) and math.isfinite(x) for x in box), 'Invalid continuous AABB')
    require(len(size) == 2 and all(type(x) is int and x > 0 for x in size), 'Invalid image dimensions')
    x0, y0, x1, y1 = box
    require(x1 > x0 and y1 > y0, 'Empty AABB')
    rounded = [math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1)]
    w, h = size
    clipped = [max(0, min(w, rounded[0])), max(0, min(h, rounded[1])),
               max(0, min(w, rounded[2])), max(0, min(h, rounded[3]))]
    require(clipped[2] > clipped[0] and clipped[3] > clipped[1], 'AABB outside image')
    return clipped, clipped != rounded


def author_aabb(box, size):
    require(len(box) == 5 and all(type(v) in (int, float) and math.isfinite(v) for v in box), 'Bad author oriented box')
    row, col, width, height, phi = box
    require(width > 0 and height > 0, 'Bad author axis length')
    dx = abs(math.cos(phi))*width/2 + abs(math.sin(phi))*height/2
    dy = abs(math.sin(phi))*width/2 + abs(math.cos(phi))*height/2
    original = [col-dx, row-dy, col+dx, row+dy]
    clipped = [max(0., original[0]), max(0., original[1]), min(float(size[0]), original[2]), min(float(size[1]), original[3])]
    return original, [clipped[0], clipped[1], clipped[2]-clipped[0], clipped[3]-clipped[1]], clipped != original


def build_records(data):
    """Pure metadata; strict agreement with prior full validation and author sources."""
    screws, manifest, author, foda = (data[k] for k in (SCREWS, SCREWS_MANIFEST, AUTHOR, FOD))
    previous = data[PREFLIGHT]['validation']
    require(len(previous) == 80 and len(screws['images']) == 44 and len(foda) == 36, 'Image denominator changed')
    require(manifest['category_mapping'] == {str(i): ('nut' if i in (7,9,10,11) else 'bolt') for i in range(1,14)}, 'Teaching mapping changed')
    simages = {f"screws:{r['id']}": r for r in screws['images']}
    sann = {r['id']: r for r in screws['annotations']}
    aimages = {r['file_name']: r for r in author['images']}
    author_filename = {r['id']: r['file_name'] for r in author['images']}
    aann = defaultdict(list)
    for row in author['annotations']:
        aann[author_filename[row['image_id']]].append(row)
    fimages = {f"foda:{r['image_id']}": r for r in foda}
    require(len(sann) == len(screws['annotations']) == 543 and len(simages) == 44 and len(fimages) == 36, 'Duplicate annotation/image')
    require(sum(len(aann[i['original_filename']]) for i in screws['images']) == len(sann), 'Dropped author target')
    require({r['id'] for r in previous} == set(simages) | set(fimages), 'Previous source set differs')
    records, images, seen = [], [], set()
    for image_index, old in enumerate(previous):
        sid = old['id']
        require(old['role'] == 'validation', 'Nonvalidation source')
        if sid in simages:
            image = simages[sid]
            original_image = aimages[image['original_filename']]
            source = {'source_path': image['file_name'], 'source_sha256': image['source_sha256'],
                      'source_rgb_sha256': image['source_decoded_rgb_sha256'], 'rgb_hash_scheme': 'width,height,RGB newline + rawRGB',
                      'image_size': [image['width'], image['height']], 'source_group': 'screws_validation_collection'}
            require(original_image['file_name'] == image['original_filename'] and all(original_image[k] == image[k] for k in ('width','height')), 'Author source mismatch')
            expected = [a for a in screws['annotations'] if a['image_id'] == image['id']]
            require(len(old['ground_truth']) == len(expected), 'Missing prior annotation')
            require([g['annotation_id'] for g in old['ground_truth']] == [a['id'] for a in expected], 'Prior annotation order differs')
        else:
            image = fimages[sid]
            source = {'source_path': image['local_image'], 'source_sha256': image['image_sha256'],
                      'source_rgb_sha256': image['rgb_sha256'], 'rgb_hash_scheme': 'widthxheight|RGB| + rawRGB',
                      'image_size': image['image_size'], 'source_group': image['group_id']}
            require(image['protocol_role'] == 'validation' and '/images/validation/' in image['local_image'], 'FOD role mismatch')
            require(image['group_id'] in ('GOPR0181', 'GOPR0183', 'unprefixed_Washer'), 'Unplanned FOD group')
            require(len(old['ground_truth']) == 1, 'FOD single author target changed')
        require(source['source_path'] == old['file_name'] and source['source_sha256'] == old['source_sha256']
                and source['image_size'] == old['image_size'], 'Historical source binding mismatch')
        require(data[TRAIN_PROTOCOL]['bindings'][str(Path(data[PREFLIGHT]['project_root']) / source['source_path'])] == source['source_sha256'], 'Detector protocol source SHA mismatch')
        for ground in old['ground_truth']:
            label = {1:'bolt',2:'nut',3:'washer'}[ground['label']]
            fields = {}
            if sid in simages:
                ann = sann[ground['annotation_id']]
                matches = [a for a in aann[image['original_filename']] if a['category_id']==ann['original_category_id']
                           and a['bbox']==ann['original_bbox_row_col_width_height_phi']]
                require(len(matches)==1,'Ambiguous author validation annotation identity')
                orig = matches[0]
                require(ann['image_id'] == image['id'] and ground['label'] == ann['category_id']
                        and orig['category_id'] == ann['original_category_id']
                        and orig['bbox'] == ann['original_bbox_row_col_width_height_phi'], 'Author annotation mismatch')
                require(label == manifest['category_mapping'][str(orig['category_id'])], 'Wrong projected class')
                raw, clipped_xywh, clipped = author_aabb(orig['bbox'], source['image_size'])
                require(clipped_xywh == ann['bbox'] and clipped == ann['bbox_clipped'], 'Oriented-to-AABB conversion changed')
                x,y,w,h = ann['bbox']
                require(ground['box'] == [x,y,x+w,y+h], 'Prior AABB changed')
                fields = {'annotation_metadata_path': SCREWS, 'annotation_metadata_sha256': PINNED[SCREWS],
                          'author_annotation_file_sha256': PINNED[AUTHOR], 'author_annotation_sha256': digest(canonical(orig).encode()),
                          'author_category_id': orig['category_id'], 'author_validation_local_annotation_id': orig['id'],
                          'author_global_annotation_id': ann['original_annotation_id'], 'author_oriented_bbox_row_col_width_height_phi': orig['bbox'],
                          'author_unclipped_aabb_xyxy': raw, 'author_aabb_clipped': clipped,
                          'author_oriented_short_side': min(orig['bbox'][2:4]),
                          'label_basis': 'author numeric type mapped by existing teaching alias, not direct English nut certification'}
            else:
                require(ground['annotation_id'] == image['annotation_member_path'] and ground['box'] == image['box_xyxy']
                        and label == image['author_category'].lower() and ground['label'] == image['class_id'], 'FOD annotation differs')
                fields = {'annotation_metadata_path': FOD, 'annotation_metadata_sha256': PINNED[FOD],
                          'author_xml_sha256': image['annotation_xml_sha256'], 'author_xml_member': image['annotation_member_path'],
                          'author_original_xml_path': image['original_xml_path'], 'author_category': image['author_category'],
                          'author_aabb_clipped': None, 'label_basis': 'author Pascal VOC single target class'}
            identity = (sid, ground['annotation_id'])
            require(identity not in seen, 'Duplicate target')
            seen.add(identity)
            box = ground['box']
            crop, clamped = integer_crop(box, source['image_size'])
            records.append({'index': len(records), 'input_id': f'roi-{len(records):04}', 'image_index': image_index,
                            'source_id': sid, 'source': old['source'], **source,
                            'annotation_id': ground['annotation_id'], **fields, 'aabb_xyxy': box,
                            'crop_xyxy': crop, 'integer_crop_clamped': clamped,
                            'short_side': min(box[2]-box[0], box[3]-box[1]),
                            'tiny': min(box[2]-box[0], box[3]-box[1]) < 16,
                            'expected_identity': label, 'class_index': {'nut':0,'washer':1}.get(label),
                            'score_role': 'open_category_bolt' if label == 'bolt' else 'nut_washer_identity',
                            'localization': 'oracle_author_aabb', 'physical_object_id': None,
                            'already_exposed_development': True, 'input_path': f'inputs/roi-{len(records):04}.png'})
        images.append({'image_index': image_index, 'source_id': sid, 'source': old['source'], **source})
    require(len(records) == 579 and Counter(r['expected_identity'] for r in records) == {'nut':168,'washer':12,'bolt':399}, 'Target denominator changed')
    return images, records


def summary(records):
    by_group = {}
    for row in records:
        key = row['source_group'] + '/' + row['expected_identity']
        entry = by_group.setdefault(key, {'targets':0,'images':set(),'tiny':0,'author_clipped_true':0,'author_clipped_unknown':0})
        entry['targets'] += 1
        entry['images'].add(row['source_id'])
        entry['tiny'] += row['tiny']
        entry['author_clipped_true'] += row['author_aabb_clipped'] is True
        entry['author_clipped_unknown'] += row['author_aabb_clipped'] is None
    for value in by_group.values():
        value['images'] = len(value['images'])
    return {'targets':len(records),'images':len({r['source_id'] for r in records}), 'by_group_class':by_group,
            'count_by_identity':dict(Counter(r['expected_identity'] for r in records)),
            'classification_targets':sum(r['score_role']=='nut_washer_identity' for r in records),
            'open_category_targets':sum(r['score_role']=='open_category_bolt' for r in records)}


def metadata(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    require(not output.exists(), 'Metadata output exists')
    for rel, expected in PINNED.items():
        require(sha(safe_path(root, rel)) == expected, 'Pinned metadata changed: '+rel)
    data = {rel: read(root / rel) for rel in (SCREWS, SCREWS_MANIFEST, AUTHOR, FOD, PREFLIGHT, TRAIN_PROTOCOL)}
    images, records = build_records(data)
    output.mkdir(parents=True)
    bindings = dict(PINNED)
    bindings[DRAFT] = sha(root / DRAFT)
    sources = {}
    for rel in (SCRIPT, TEST, DRAFT):
        target = output / 'source_snapshot' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / rel, target)
        sources[rel] = sha(target)
        require(sources[rel] == sha(root / rel), 'Source changed while copying')
    plan = {'schema':'kitguard.v08.manta-transfer.metadata.v1', 'status':'metadata_only_not_authorized',
            'created_at_utc':datetime.now(UTC).isoformat(), 'project_root':str(root), 'policy':POLICY,
            'bindings':bindings, 'source_snapshot':sources, 'runtime':pillow_runtime(), 'images':images,'records':records,
            'summary':summary(records), 'source_hash_claim':'copied and cross-checked historical bindings; source image bytes not read in metadata stage',
            'actual_images_decoded':0,'actual_image_bytes_read':0,'models_called':0,'prepare_authorized':False,
            'exclusions':['FOD held_back','new LOCO24','MANTA test','other detector partitions'],
            'limitations':['Oracle annotation localization can contain neighboring instances/background',
                           'Tiny and clipped targets are retained; resizing does not restore detail',
                           'Existing validation exposure and unknown physical/session/pretraining independence',
                           'Class/background/crop geometry and padding remain shortcut risks']}
    write_new(output / 'metadata.json', plan)
    return {'status':plan['status'],'metadata':str(output/'metadata.json'),'sha256':sha(output/'metadata.json'),**plan['summary']}


def check_gate(plan_path, expected, approval_path, approval_sha):
    require(sha(plan_path)==expected and sha(approval_path)==approval_sha,'Plan/approval changed')
    plan, approval = read(plan_path), read(approval_path)
    require(plan['schema']=='kitguard.v08.manta-transfer.metadata.v1' and plan['policy']==POLICY,'Wrong transfer plan')
    require(approval['schema']=='kitguard.v08.manta-transfer.preparation-approval.v1' and approval['status']=='approved'
            and approval['authorized_by']=='root' and approval['metadata_sha256']==expected
            and approval['allow_model_inference'] is False and approval['scope']=='prepare_all579_oracle_rois','Separate preparation approval required')
    paths = {}
    for name in ('internal_audit','internal_run','classifier_checkpoint'):
        entry = approval[name]
        paths[name] = Path(entry['path']).resolve()
        require(sha(paths[name])==entry['sha256'],'Internal gate evidence changed')
    audit, run = read(paths['internal_audit']), read(paths['internal_run'])
    require(audit['schema']=='kitguard.v08.manta-classifier.independent-audit.v1' and audit['status']=='passed'
            and audit['selected_epoch']==10 and audit['validation_records']==256,'Internal independent audit incomplete')
    metrics = audit['independent_results']
    main = metrics['threshold_0_9']
    require(metrics['continuation_gate'] is True and main['denominator']==256
            and all(main['CWUEN'][k]==0 for k in ('W','E','N'))
            and set(main['classes'])=={'nut','yellow_green_washer'}
            and all(v['group_macro_correct_coverage']>=.75 for v in main['classes'].values()),'Internal fixed gate did not pass')
    require(run['status']=='completed' and run['selected_epoch']==run['epochs_completed']==10
            and run['final_integrity_passed'] is True and run['body_unchanged'] is True,'Internal run incomplete')
    require(audit['bindings'][str(paths['internal_run'])]==approval['internal_run']['sha256']
            and audit['bindings'][str(paths['classifier_checkpoint'])]==approval['classifier_checkpoint']['sha256']
            and run['final_checkpoint']['sha256']==approval['classifier_checkpoint']['sha256'], 'Audit/run/checkpoint do not correspond')
    return plan


def crop_input(rgb, row):
    """Called only by separately approved prepare or with synthetic test images."""
    from PIL import Image, ImageOps
    require(rgb.mode=='RGB' and list(rgb.size)==row['image_size'], 'Wrong source shape/mode')
    crop, clamped = integer_crop(row['aabb_xyxy'], row['image_size'])
    require(crop==row['crop_xyxy'] and clamped==row['integer_crop_clamped'],'Crop policy changed')
    region = rgb.crop(crop)
    gray = region.convert('L').convert('RGB')
    inp = ImageOps.pad(gray,(224,224),method=Image.Resampling.LANCZOS,color=(0,0,0),centering=(.5,.5))
    stream=io.BytesIO();inp.save(stream,format='PNG',optimize=False,compress_level=6)
    return stream.getvalue(), {'roi_rgb_sha256':pixel_sha(region),'roi_gray_sha256':pixel_sha(gray),
                               'roi_size':list(region.size),'input_pixel_sha256':pixel_sha(inp),'input_size':[224,224]}


def prepare(plan_path, expected, approval_path, approval_sha, output):
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan = check_gate(plan_path,expected,approval_path,approval_sha)
    require(not output.exists(),'Prepare output exists')
    require(Path(__file__).resolve()==plan_path.parent/'source_snapshot'/SCRIPT,'Use metadata source snapshot')
    root=Path(plan['project_root'])
    require(pillow_runtime()==plan['runtime'],'Pillow runtime changed')
    for rel, expected_sha in plan['bindings'].items():
        require(sha(safe_path(root,rel))==expected_sha,'Metadata binding changed')
    for rel, expected_sha in plan['source_snapshot'].items():
        require(sha(safe_path(plan_path.parent/'source_snapshot',rel))==expected_sha,'Preparation source changed')
    source_data={rel:read(root/rel) for rel in (SCREWS,SCREWS_MANIFEST,AUTHOR,FOD,PREFLIGHT,TRAIN_PROTOCOL)}
    images, original=build_records(source_data)
    require(images==plan['images'] and original==plan['records'],'Source population changed')
    output.mkdir(parents=True)
    shutil.copyfile(plan_path,output/'metadata.json');shutil.copyfile(approval_path,output/'approval.json')
    rows=[{**copy.deepcopy(r),'status':'not_attempted','error':None} for r in original]
    grouped=defaultdict(list)
    for row in rows: grouped[row['source_id']].append(row)
    interrupted=None;decoded=0
    from PIL import Image
    for source in images:
        members=grouped[source['source_id']]
        try:
            path=safe_path(root,source['source_path'])
            require(sha(path)==source['source_sha256'],'Original image SHA changed')
            with Image.open(path) as im:
                require(list(im.size)==source['image_size'] and getattr(im,'n_frames',1)==1
                        and im.getexif().get(274,1)==1,'Image geometry/orientation differs')
                rgb=im.convert('RGB');rgb.load();decoded+=1
            w,h=rgb.size
            prefix=f'{w},{h},RGB\n'.encode() if source['source']=='screws' else f'{w}x{h}|RGB|'.encode()
            require(digest(prefix+rgb.tobytes())==source['source_rgb_sha256'],'Original decoded RGB changed')
            for row in members:
                try:
                    encoded,facts=crop_input(rgb,row)
                    target=output/row['input_path'];target.parent.mkdir(parents=True,exist_ok=True)
                    with target.open('xb') as stream:stream.write(encoded)
                    row.update(status='prepared',input_sha256=digest(encoded),**facts)
                except Exception as error:  # noqa: BLE001 -- preserve all targets, never substitute
                    row.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
        except BaseException as error:  # noqa: BLE001 -- retain failed source targets and remaining not-attempted
            for row in members:
                if row['status']=='not_attempted':row.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
            if not isinstance(error,Exception):interrupted=error;break
    write_new(output/'records.json',rows)
    integrity_error=None
    try:
        check_gate(plan_path,expected,approval_path,approval_sha)
        for rel, bound in plan['bindings'].items():require(sha(safe_path(root,rel))==bound,'Metadata changed during preparation')
        for rel, bound in plan['source_snapshot'].items():require(sha(safe_path(plan_path.parent/'source_snapshot',rel))==bound,'Source changed during preparation')
        require(pillow_runtime()==plan['runtime'],'Pillow runtime changed during preparation')
        for source in images:require(sha(safe_path(root,source['source_path']))==source['source_sha256'],'Source bytes changed during preparation')
    except Exception as error:  # noqa: BLE001 -- retain mutation failure
        integrity_error={'type':type(error).__name__,'message':str(error)}
    result={'schema':'kitguard.v08.manta-transfer.preparation.v1','status':'prepared' if all(r['status']=='prepared' for r in rows) and not integrity_error else 'blocked',
            'metadata_sha256':expected,'approval_sha256':approval_sha,'records_sha256':sha(output/'records.json'),
            'status_counts':dict(Counter(r['status'] for r in rows)),'summary':summary(rows),'images_decoded':decoded,
            'models_called':0,'independent_detection':False,'inference_authorized_by_this_receipt':False,
            'new_holdout_claim':False,'integrity_error':integrity_error}
    write_new(output/'preparation.json',result)
    if interrupted:raise interrupted
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('metadata','prepare'))
    parser.add_argument('--project-root',type=Path,default=ROOT)
    parser.add_argument('--metadata',type=Path)
    parser.add_argument('--expected-metadata-sha256')
    parser.add_argument('--approval',type=Path)
    parser.add_argument('--expected-approval-sha256')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='metadata':result=metadata(args.project_root,args.output)
    else:
        require(all((args.metadata,args.expected_metadata_sha256,args.approval,args.expected_approval_sha256)),'Missing bound preparation approval')
        result=prepare(args.metadata,args.expected_metadata_sha256,args.approval,args.expected_approval_sha256,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result.get('status')=='blocked' else 0


if __name__=='__main__':
    raise SystemExit(main())
