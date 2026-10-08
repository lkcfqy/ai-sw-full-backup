import json,struct,copy,subprocess
from pathlib import Path
BASE=Path(__file__).parent
M=json.loads((BASE/'original-models.json').read_text())
R=[dict(tag=m['tagid'],level=m['level'],data=bytearray.fromhex(' '.join(m['payload'])),seq=m['seqno']) for m in M]
def pack(records):
 out=bytearray()
 for r in records:
  size=len(r['data']); out+=struct.pack('<I',r['tag']|(r['level']<<10)|(min(size,4095)<<20))
  if size>=4095: out+=struct.pack('<I',size)
  out+=r['data']
 return out

def para_end(i):
 j=i+1
 while j<len(R) and R[j]['level']>R[i]['level']: j+=1
 return j

def text_para(i,text,style=None,clear_lines=True):
 old=R[i:para_end(i)]
 assert old[0]['tag']==66
 assert all(r['tag'] in (66,67,68,69,70) for r in old)
 new=copy.deepcopy(old)
 head=new[0]
 n=len(text.encode('utf-16le'))//2+1
 struct.pack_into('<I',head['data'],0,(struct.unpack_from('<I',head['data'])[0]&0x80000000)|n)
 struct.pack_into('<HHH',head['data'],12,1,0,0 if clear_lines else 1)
 ch=next(r for r in new if r['tag']==68)
 ch['data']=bytearray(ch['data'][:8]); struct.pack_into('<I',ch['data'],0,0)
 if style is not None: struct.pack_into('<I',ch['data'],4,style)
 pt=dict(tag=67,level=head['level']+1,data=bytearray((text+'\r').encode('utf-16le')),seq=None)
 out=[head,pt,ch]
 if not clear_lines:
  ls=next(r for r in new if r['tag']==69);ls['data']=ls['data'][:36];out.append(ls)
 return out

def generate(name,replacements,ranges=None):
 out=[]; i=0
 while i<len(R):
  if i in replacements:
   items=replacements[i];out.extend(items); i=para_end(i)
  else: out.append(copy.deepcopy(R[i]));i+=1
 if ranges:
  out=[r for r in out if r['seq'] is None or any(a<=r['seq']<b for a,b in ranges)]
 (BASE/(name+'.body')).write_bytes(pack(out))
 subprocess.run(['/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node',str(BASE/'write_cfb.cjs'),str(BASE/(name+'.body')),str(BASE/(name+'.hwp'))],check=True)
 return out
if __name__=='__main__':
 generate('probe',{38:text_para(38,'해피'),74:text_para(74,'국립창원대학교 대학원 인공지능융합공학과 석·박사통합과정 1년차')})

# Native HWP5 completion: edit only form fields; preserve original table controls.
def fill(i,text,style=22,paragraph_style=None):
 out=text_para(i,text,style=style)
 struct.pack_into('<I',out[0]['data'],4,0)
 if paragraph_style is not None:struct.pack_into('<H',out[0]['data'],8,paragraph_style)
 return out

def edited_range(start,end,replacements):
 out=[];i=start
 while i<end:
  if i in replacements:out.extend(copy.deepcopy(replacements[i]));i=para_end(i)
  else:out.append(copy.deepcopy(R[i]));i+=1
 return out

def save_records(name,records):
 last=next(r for r in reversed(records) if r['tag']==66 and r['level']==0)
 struct.pack_into('<I',last['data'],0,struct.unpack_from('<I',last['data'])[0]|0x80000000)
 (BASE/(name+'.body')).write_bytes(pack(records))
 subprocess.run(['/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node',str(BASE/'write_cfb.cjs'),str(BASE/(name+'.body')),str(BASE/(name+'.hwp'))],check=True)

if __name__=='__main__':
 fields=json.loads((BASE.parent/'报名字段正文.json').read_text())
 fields.update(json.loads((BASE.parent/'20260927_官方复核/updated-plan-fields.json').read_text()))
 replacements={}
 def setp(i,text,style=22,ps=None):replacements[i]=fill(i,text,style,ps)
 setp(28,'□고등부      □대학부     ■일반부',14)
 setp(38,'해피');setp(56,'남청청');setp(65,'010-6728-3265',15)
 setp(74,'국립창원대학교 대학원 인공지능융합공학과 석·박사통합과정 1년차',15)
 setp(83,'3246599898@qq.com',15)
 setp(92,'경상남도 창원시 의창구 창원대학로 20, 국립창원대학교 학생생활관 5동 510호실',15)
 setp(112,'이개심');setp(122,'010-3915-7350',15)
 setp(132,'국립창원대학교 대학원 인공지능융합공학과 박사과정 1년차',15)
 setp(142,'경상남도 창원시',15)
 setp(347,'■ 2. 업무혁신, 생산성향상 AI Agent',14)
 setp(429,fields['project_title'],15)
 for i,title,key in [(442,'목적','intro_purpose'),(446,'개발 내용 설명','intro_content'),(450,'기대효과','intro_effect')]:setp(i,title+': '+fields[key],15,0)
 setp(472,'□ 국내 LLM(        )  ■ 기타(Qwen3.6-27B 4-bit, MLX-VLM 로컬 추론, 신규 학습 없음)',18)
 setp(482,'□ LangChain  □ AutoGen  □ CrewAI  □ Dify  □ n8n  ■ 기타(FastAPI, MLX-VLM, SQLite, 경량 웹)',18)
 setp(492,'■ Python  ■ JavaScript  □ Java  ■ 기타(HTML, CSS, SQL)',18)
 setp(502,'□ 예 (희망 플랫폼: AWS / NCP / GCP / Azure / 기타(        )  ■ 아니오. MacBook Pro M5 Pro 64 GB 사전 연구 실행. RTX 3080 데스크톱은 미연결·미검증.',18)
 for i,title,key in [(516,'개발방법','method'),(520,'일정','schedule'),(524,'개발방법론','methodology'),(528,'목표 성능(정량, 정성)','targets')]:setp(i,title+': '+fields[key],15,0)
 setp(532,'As-Is: '+fields['as_is']+' To-Be: '+fields['to_be'],15,0)
 setp(536,'기타: '+fields['other']+' '+fields['roles'],15,0)
 for i,t in [(570,'남청청'),(574,'01067283265'),(578,'국립창원대학교 인공지능융합공학과'),(582,'팀장: 총괄·요구사항·사용자 실험·제출 관리'),(586,'이개심'),(590,'01039157350'),(594,'국립창원대학교 인공지능융합공학과'),(598,'실물 데이터·평가·재현성 검증·시연 준비')]:setp(i,t,3 if i in (574,578,590,594) else 15)
 setp(698,'상기신청인 (대표) 남청청              (인)',8)
 # Keep the date and signature together; prevent telephone digits splitting.
 R[681]['data'][11] |= 4
 app=edited_range(0,778,replacements)
 save_records('01_해피_참가신청서_개발계획서_서명전',app)
 for n,name in [(2,'남청청'),(3,'이개심')]:
  header=copy.deepcopy(R[:12]); p=header[1]
  p['data']=bytearray(p['data'].replace('(서식 제1호)'.encode('utf-16le'),'(서식 제2호)'.encode('utf-16le')))
  struct.pack_into('<H',header[0]['data'],8,25)
  cons=header+edited_range(782,1025,{998:fill(998,'성    명 : '+name+'          (인 또는 서명)',22)})
  save_records(f'0{n}_참가자_동의서_{name}_선택서명전',cons)
 (BASE/'field-audit.json').write_text(json.dumps({'template':'official-template.hwp','filled_paragraphs':sorted(replacements),'source_body_records':len(R),'application_body_records':len(app),'consent_only_change':'typed participant name; original clauses and choices retained','signature_status':'unsigned; date day blank; all consent choices unchecked'},ensure_ascii=False,indent=2))
