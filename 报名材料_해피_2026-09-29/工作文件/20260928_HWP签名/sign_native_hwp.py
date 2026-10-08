from pathlib import Path
import json,struct,subprocess,copy,hashlib,datetime
from zoneinfo import ZoneInfo
BASE=Path(__file__).parent; ROOT=BASE.parents[2]; SRC=ROOT/'现在签名_해피'/'未签名备份_勿提交'
NODE='/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node';PROC='/tmp/gnict-archive-venv/bin/hwp5proc'
NOW=datetime.datetime.now(ZoneInfo('Asia/Seoul'));DATE=f'{NOW.year}년 {NOW.month}월 {NOW.day}일'
PACK=lambda fmt,*a:struct.pack('<'+fmt,*a)
def rec(tag,level,payload):return dict(tag=tag,level=level,data=bytearray(payload))
def pack(rs):
 b=bytearray()
 for r in rs:
  n=len(r['data']);b+=PACK('I',r['tag']|(r['level']<<10)|(min(n,4095)<<20))
  if n>=4095:b+=PACK('I',n)
  b+=r['data']
 return b

def parse(path,stream):
 ms=json.loads(subprocess.check_output([PROC,'models','--json',str(path),stream]))
 rs=[rec(m['tagid'],m['level'],bytes.fromhex(' '.join(m['payload']))) for m in ms]
 return ms,rs

def ptext(m):return ''.join(c[1] for c in m['content']['chunks'] if isinstance(c[1],str))

def text_para(rs,i,text,inline_image=False):
 j=i+1
 while j<len(rs) and rs[j]['level']>rs[i]['level']:j+=1
 old=copy.deepcopy(rs[i:j]);head=old[0]
 payload=(text+'\r').encode('utf-16le')
 if inline_image:
  assert '\ufffc' in text
  payload=payload.replace('\ufffc'.encode('utf-16le'),bytes.fromhex('0b00206f736700000000000000000b00'))
 n=len(payload)//2
 struct.pack_into('<I',head['data'],0,(struct.unpack_from('<I',head['data'])[0]&0x80000000)|n)
 struct.pack_into('<I',head['data'],4,2048 if inline_image else 0)
 struct.pack_into('<HHH',head['data'],12,1,0,0)
 shape=next(r for r in old if r['tag']==68);shape['data']=shape['data'][:8]
 struct.pack_into('<I',shape['data'],0,0)
 out=[head,rec(67,head['level']+1,payload),shape]
 return out,j

def signature_shape(level,member=False):
 # HWPUNIT = 1/100 pt. Preserve the supplied JPEG aspect ratio.
 w=8504 # 30 mm
 h=round(w*295/(524 if member else 525))
 iid=2026092803 if member else 2026092802
 # Inline, affects line spacing, absolute dimensions, figure object.
 flags=1|4|(4<<15)|(2<<18)|(1<<26)
 ctrl=b' osg'+PACK('IiiIIhhHHHHIhH',flags,0,0,w,h,0,0,0,0,0,0,iid,0,0)
 # GSO child picture; identity transformation, native width and height.
 component=b'cip$cip$'+PACK('iiHHiiiiIHiiH',0,0,0,1,w,h,w,h,0x24000000,0,w//2,h//2,1)
 ident=PACK('6d',1,0,0,0,1,0)
 component+=ident+ident+ident
 picture=PACK('IiI',0,0,0)+PACK('8i',0,0,w,0,w,h,0,h)+PACK('4i',0,0,w,h)+PACK('4H',0,0,0,0)+PACK('bbBH',0,0,0,1)
 # Border opacity, picture instance id, no special effects, original size, opacity.
 picture+=PACK('BIIiiB',0,iid,0,w,h,0)
 return [rec(71,level+1,ctrl),rec(76,level+2,component),rec(85,level+3,picture)]

manifest=[]
for path in sorted(SRC.glob('0[123]_*.hwp')):
 is_app=path.name.startswith('01_');member=path.name.startswith('03_');name='이개심' if member else '남청청'
 source_copy=BASE/('unsigned-'+path.name)
 if not source_copy.exists():source_copy.write_bytes(path.read_bytes())
 else:assert source_copy.read_bytes()==path.read_bytes()
 ms,rs=parse(path,'BodyText/Section0');di,dr=parse(path,'DocInfo')
 replacements={};marks=0;dates=0;signed=0
 for m in ms:
  if m['type']!='ParaText':continue
  t=ptext(m);i=m['seqno']-1
  assert rs[i]['tag']==66
  if '[  ] 동의함    [  ] 동의하지 않음' in t:
   replacements[i]=text_para(rs,i,t.replace('[  ] 동의함    [  ] 동의하지 않음','[✓] 동의함    [  ] 동의하지 않음'));marks+=1
  elif t.strip().startswith('2026년') and t.rstrip().endswith('일'):
   replacements[i]=text_para(rs,i,DATE);dates+=1
  elif (is_app and t.startswith('상기신청인 (대표)')) or (not is_app and t.startswith('성    명 :')):
   sigtext=f'상기신청인 (대표) {name}   \ufffc (인)' if is_app else f'성    명 : {name}    \ufffc (인 또는 서명)'
   new,j=text_para(rs,i,sigtext,True);new+=signature_shape(rs[i]['level'],member)
   replacements[i]=(new,j);signed+=1
 assert marks==(0 if is_app else 4) and dates==1 and signed==1,(marks,dates,signed)
 out=[];i=0
 while i<len(rs):
  if i in replacements:
   new,j=replacements[i];out+=new;i=j
  else:out.append(rs[i]);i+=1
 # Append one embedded JPEG resource to the document's ID map.
 idmap=next(i for i,m in enumerate(di) if m['type']=='IdMappings')
 assert struct.unpack_from('<I',dr[idmap]['data'])[0]==0
 struct.pack_into('<I',dr[idmap]['data'],0,1)
 dr.insert(idmap+1,rec(18,1,PACK('HHH',0x21,1,3)+'jpg'.encode('utf-16le')))
 stem=path.stem.replace('_선택서명전','_서명본').replace('_서명전','_서명본')
 body=BASE/(stem+'.body');docinfo=BASE/(stem+'.docinfo');dest=BASE/(stem+'.hwp')
 body.write_bytes(pack(out));docinfo.write_bytes(pack(dr))
 signature=BASE/(('member' if member else 'leader')+'-signature-original.jpg')
 subprocess.run([NODE,str(BASE/'write_signed_cfb.cjs'),str(path),str(body),str(docinfo),str(signature),str(dest)],check=True)
 manifest.append(dict(file=dest.name,participant=name,signature_sha256=hashlib.sha256(signature.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),date=DATE,consents_accepted=marks,signature_count=1,signature_image_unmodified=True))
(BASE/'签署记录.json').write_text(json.dumps({'authorized_by':'User explicitly confirmed both signatures authorized and all four consent groups agreed','created_at':NOW.isoformat(),'files':manifest},ensure_ascii=False,indent=2))
print(json.dumps(manifest,ensure_ascii=False,indent=2))
