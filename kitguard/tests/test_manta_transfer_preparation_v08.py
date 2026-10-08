"""Transfer preparation: fixed metadata plus synthetic-only pixel contracts."""
import copy
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'scripts/v08/prepare_manta_transfer.py'
spec=importlib.util.spec_from_file_location('manta_transfer_contract',SOURCE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def metadata_inputs():
    return {rel:json.loads((ROOT/rel).read_text()) for rel in (m.SCREWS,m.SCREWS_MANIFEST,m.AUTHOR,m.FOD,m.PREFLIGHT,m.TRAIN_PROTOCOL)}


def test_module_import_does_not_import_image_or_model_libraries():
    code=f"import runpy,sys;runpy.run_path({str(SOURCE)!r});assert not any(x in sys.modules for x in ('PIL','torch','torchvision','mlx'))"
    result=subprocess.run([sys.executable,'-I','-c',code],capture_output=True,text=True,check=False)
    assert result.returncode==0,result.stderr


def test_all579_boundaries_are_metadata_only():
    data=metadata_inputs()
    images,rows=m.build_records(data)
    assert len(images)==80 and len(rows)==579
    assert [r['input_id'] for r in rows]==[f'roi-{i:04}' for i in range(579)]
    summary=m.summary(rows)
    assert summary['count_by_identity']=={'nut':168,'washer':12,'bolt':399}
    assert summary['classification_targets']==180 and summary['open_category_targets']==399
    assert sum(r['tiny'] for r in rows)==8
    assert sum(r['author_aabb_clipped'] is True for r in rows)==9
    assert sum(r['author_aabb_clipped'] is None for r in rows)==36
    assert all(r['localization']=='oracle_author_aabb' for r in rows)
    assert {r['author_category_id'] for r in rows if r['source']=='screws' and r['expected_identity']=='nut'}=={7,9,10,11}
    # Official val JSON uses local IDs; the derived mapping uses global file-based IDs.
    remapped=next(r for r in rows if r['source_id']=='screws:10')
    assert remapped['author_validation_local_annotation_id']!=remapped['author_global_annotation_id']


@pytest.mark.parametrize('variant',['omit','reorder','raw_bbox','mapping','source_sha','prior_box'])
def test_changed_metadata_population_is_rejected(variant):
    data=metadata_inputs()
    if variant=='omit':data[m.SCREWS]['annotations'].pop()
    elif variant=='reorder':data[m.PREFLIGHT]['validation'][0]['ground_truth'].reverse()
    elif variant=='raw_bbox':data[m.AUTHOR]['annotations'][0]['bbox'][0]+=.2
    elif variant=='mapping':data[m.SCREWS_MANIFEST]['category_mapping']['7']='bolt'
    elif variant=='source_sha':data[m.SCREWS]['images'][0]['source_sha256']='wrong'
    else:data[m.PREFLIGHT]['validation'][0]['ground_truth'][0]['box'][0]+=.01
    with pytest.raises(ValueError):m.build_records(data)


@pytest.mark.parametrize(('box','size','expected','clamped'),[
    ([1.2,2.8,5.01,7.0],[10,10],[1,2,6,7],False),
    ([-1.2,-.1,10.2,12],[10,10],[0,0,10,10],True),
    ([2.01,2.01,2.02,2.02],[10,10],[2,2,3,3],False),
])
def test_floor_ceil_exclusive_crop_preserves_tiny_and_clipped(box,size,expected,clamped):
    assert m.integer_crop(box,size)==(expected,clamped)


@pytest.mark.parametrize('box',[[1,1,1,2],[11,0,12,1],[0,float('nan'),1,2],[False,0,1,2]])
def test_invalid_or_empty_box_fails_instead_of_being_replaced(box):
    with pytest.raises(ValueError):m.integer_crop(box,[10,10])


def test_periodic_author_angle_not_discarded():
    raw,xywh,clipped=m.author_aabb([50,50,10,20,8*3.141592653589793],[100,100])
    assert xywh==pytest.approx([45,40,10,20])
    assert raw==pytest.approx([45,40,55,60]) and not clipped


def test_fixed_gray_pad_is_label_independent_and_keeps_tiny():
    from PIL import Image, ImageOps
    im=Image.new('RGB',(8,6),(80,140,200))
    row={'image_size':[8,6],'aabb_xyxy':[1.2,1.2,2.3,5.1],'crop_xyxy':[1,1,3,6],
         'integer_crop_clamped':False,'expected_identity':'nut'}
    content,facts=m.crop_input(im,row)
    changed=copy.deepcopy(row);changed['expected_identity']='washer'
    assert content==m.crop_input(im,changed)[0]
    ref=ImageOps.pad(im.crop((1,1,3,6)).convert('L').convert('RGB'),(224,224),method=Image.Resampling.LANCZOS,color=(0,0,0),centering=(.5,.5))
    buffer=io.BytesIO();ref.save(buffer,format='PNG',optimize=False,compress_level=6)
    assert content==buffer.getvalue() and facts['roi_size']==[2,5]
    with Image.open(io.BytesIO(content)) as image:
        assert image.size==(224,224) and image.mode=='RGB' and not image.getexif()


def gate_fixture(tmp_path):
    checkpoint=tmp_path/'final.pt';checkpoint.write_bytes(b'synthetic checkpoint, not a model')
    runpath=tmp_path/'run.json'
    run={'status':'completed','selected_epoch':10,'epochs_completed':10,'final_integrity_passed':True,
         'body_unchanged':True,'final_checkpoint':{'sha256':m.sha(checkpoint)}}
    m.write_new(runpath,run)
    auditpath=tmp_path/'audit.json'
    audit={'schema':'kitguard.v08.manta-classifier.independent-audit.v1','status':'passed','selected_epoch':10,'validation_records':256,
           'independent_results':{'continuation_gate':True,'threshold_0_9':{'denominator':256,'CWUEN':{'C':256,'W':0,'U':0,'E':0,'N':0},
                                  'classes':{n:{'group_macro_correct_coverage':1.0} for n in ('nut','yellow_green_washer')}}},
           'bindings':{str(runpath.resolve()):m.sha(runpath),str(checkpoint.resolve()):m.sha(checkpoint)}}
    m.write_new(auditpath,audit)
    planpath=tmp_path/'metadata.json';m.write_new(planpath,{'schema':'kitguard.v08.manta-transfer.metadata.v1','policy':m.POLICY})
    approval={'schema':'kitguard.v08.manta-transfer.preparation-approval.v1','status':'approved','authorized_by':'root',
              'metadata_sha256':m.sha(planpath),'allow_model_inference':False,'scope':'prepare_all579_oracle_rois'}
    for key,path in [('internal_audit',auditpath),('internal_run',runpath),('classifier_checkpoint',checkpoint)]:
        approval[key]={'path':str(path.resolve()),'sha256':m.sha(path)}
    return planpath,approval,auditpath,audit


def test_metadata_alone_never_authorizes_real_image_decode(tmp_path):
    plan,approval,_,_=gate_fixture(tmp_path)
    apath=tmp_path/'approval.json';m.write_new(apath,approval)
    assert m.check_gate(plan,m.sha(plan),apath,m.sha(apath))['policy']==m.POLICY
    approval['allow_model_inference']=True
    other=tmp_path/'different.json';m.write_new(other,approval)
    with pytest.raises(ValueError):m.check_gate(plan,m.sha(plan),other,m.sha(other))


@pytest.mark.parametrize('variant',['failed_audit','gate_false','W','wrong_epoch','other_run','changed_checkpoint'])
def test_prepare_rejects_failed_or_unbound_internal_gate(tmp_path,variant):
    plan,approval,auditpath,audit=gate_fixture(tmp_path)
    if variant=='failed_audit':audit['status']='failed'
    elif variant=='gate_false':audit['independent_results']['continuation_gate']=False
    elif variant=='W':audit['independent_results']['threshold_0_9']['CWUEN']['W']=1
    elif variant=='wrong_epoch':audit['selected_epoch']=7
    elif variant=='other_run':audit['bindings'][approval['internal_run']['path']]='different'
    else:Path(approval['classifier_checkpoint']['path']).write_bytes(b'changed synthetic')
    auditpath.write_text(json.dumps(audit))
    approval['internal_audit']['sha256']=m.sha(auditpath)
    apath=tmp_path/'approval.json';m.write_new(apath,approval)
    with pytest.raises(ValueError):m.check_gate(plan,m.sha(plan),apath,m.sha(apath))


def test_output_never_overwrites(tmp_path):
    m.write_new(tmp_path/'receipt.json',{'stage':'original'})
    with pytest.raises(FileExistsError):m.write_new(tmp_path/'receipt.json',{'stage':'replace'})
    with pytest.raises(ValueError):m.metadata(ROOT,tmp_path)


@pytest.mark.parametrize('interrupt',[False,True])
def test_prepare_runtime_failure_preserves_all_rows_without_retry(tmp_path,monkeypatch,interrupt):
    from PIL import Image
    rows=[];images=[]
    for i in range(2):
        path=tmp_path/f'synthetic-{i}.png'
        rgb=Image.new('RGB',(8,6),(10,20,30));rgb.save(path)
        source={'source_id':f'synthetic:{i}','source':'screws','source_group':'synthetic',
                'source_path':path.name,'source_sha256':m.sha(path),'source_rgb_sha256':m.digest(b'8,6,RGB\n'+rgb.tobytes()),
                'image_size':[8,6]}
        images.append(source)
        rows.append({**source,'input_id':f'roi-{i:04}','input_path':f'inputs/roi-{i:04}.png','aabb_xyxy':[1.2,1.2,5.2,5.2],
                     'crop_xyxy':[1,1,6,6],'integer_crop_clamped':False,'expected_identity':'nut','score_role':'nut_washer_identity',
                     'tiny':True,'author_aabb_clipped':False})
    plan={'project_root':str(tmp_path),'runtime':{},'bindings':{},'source_snapshot':{},'images':images,'records':rows}
    planpath=tmp_path/'metadata.json';m.write_new(planpath,plan)
    approval=tmp_path/'approval.json';m.write_new(approval,{'synthetic':True})
    for rel in (m.SCREWS,m.SCREWS_MANIFEST,m.AUTHOR,m.FOD,m.PREFLIGHT,m.TRAIN_PROTOCOL):m.write_new(tmp_path/rel,{})
    monkeypatch.setattr(m,'__file__',str(tmp_path/'source_snapshot'/m.SCRIPT))
    monkeypatch.setattr(m,'check_gate',lambda *_:plan)
    monkeypatch.setattr(m,'pillow_runtime',dict)
    monkeypatch.setattr(m,'build_records',lambda _:(images,rows))
    count=[]
    original=m.crop_input
    def crop(image,row):
        count.append(row['input_id'])
        if row['input_id']=='roi-0000':
            if interrupt:raise KeyboardInterrupt('synthetic interrupt')
            raise ValueError('synthetic crop failure')
        return original(image,row)
    monkeypatch.setattr(m,'crop_input',crop)
    output=tmp_path/'out'
    if interrupt:
        with pytest.raises(KeyboardInterrupt):m.prepare(planpath,m.sha(planpath),approval,m.sha(approval),output)
    else:
        assert m.prepare(planpath,m.sha(planpath),approval,m.sha(approval),output)['status']=='blocked'
    result=m.read(output/'preparation.json');saved=m.read(output/'records.json')
    assert len(saved)==2 and saved[0]['status']=='failed'
    assert saved[1]['status']==('not_attempted' if interrupt else 'prepared')
    assert count==(['roi-0000'] if interrupt else ['roi-0000','roi-0001'])
    assert result['models_called']==0 and not result['inference_authorized_by_this_receipt']
