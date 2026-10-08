const fs = require('fs'), path = require('path'), zlib = require('zlib'), assert = require('assert'), crypto = require('crypto');
const CFB = require('../20260928_原生HWP填写/vendor/node_modules/cfb');
const base = __dirname, root = path.resolve(base, '../../..');
const file = '01_해피_참가신청서_개발계획서_서명본.hwp';
const source = path.join(root, '现在签名_해피', file);
const beforeBytes = fs.readFileSync(source);
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
assert.equal(sha(beforeBytes), '7c5bb6422c15f51504a022695dab31334157868a5fd7ac830d65cf5764c20764');
fs.writeFileSync(path.join(base, '修订前_' + file), beforeBytes);
const original = CFB.read(beforeBytes, {type:'buffer'});
const body = zlib.inflateRawSync(CFB.find(original, '/BodyText/Section0').content);
const records = [];
for (let p=0; p<body.length;) {
  const h = body.readUInt32LE(p); p+=4;
  let n = h>>>20;
  if (n===4095) { n=body.readUInt32LE(p); p+=4; }
  records.push({tag:h&1023, level:(h>>>10)&1023, data:Buffer.from(body.subarray(p,p+n))}); p+=n;
}
const replacements = new Map([
  [
    "개발방법 및 진행 상태:",
    "개발방법: 주문 입력·검사 범위 지정·사진 분석·수량 대조·재확인의 흐름을 하나의 작업 단위로 연결한다. 로컬 시각 모델은 부품 목록을 제안하고, 프로그램은 주문과의 차이를 계산하도록 설계한다. 주문이나 사진 범위가 변경되면 관련 판정을 다시 확인하고, 불확실한 관찰에는 추가 촬영 또는 작업자 확인을 요청한다. 사진·좌표·주문 버전·결과를 함께 기록하여 판단 근거를 추적할 수 있도록 구성한다."
  ],
  [
    "일정(참가 및 개발 범위 확인을 전제로 함):",
    "일정: 9.29 운영규정을 확인하고 요구사항·평가 지표를 정리한다. 9.30~10.2 핵심 흐름과 실물 사진 검증을 진행하고, 10.3~4 오류·보류 처리 및 재현성을 점검한다. 10.5 보고서·기술설명서·발표·영상·소스를 정리하여 10.6 12:00까지 제출할 계획이다."
  ],
  [
    "개발방법론:",
    "개발방법론: 실제 확보한 부품으로 초기 12사례를 계획하고, 각 사례의 주문·사진·검사 범위와 수기 정답을 고정하여 AI 결과와 비교한다. 정답·오답·불확실·실행 실패를 구분하고, 같은 사진의 여러 영역을 독립 사례로 중복 계산하지 않는다. 검증 인원·미수행 사례·제약을 함께 기록한다. 공개 데이터 평가와 실물 사진 검증의 결과를 구분하여 보고한다."
  ],
  [
    "기타:",
    "기타: MacBook Pro M5 Pro 64 GB에서 Qwen3.6-27B 4-bit/MLX-VLM을 활용하는 구성을 계획한다. 신규 모델 학습, 치수·나사산·재질 판정 및 생산설비 제어는 범위에서 제외한다. 팀장 남청청은 요구사항·사용자 검증·제출 관리를, 팀원 이개심은 실물 데이터·평가·재현성·시연 준비를 담당한다. Codex를 코드 작성·점검·문서 보조에 활용하며, 두 참가자가 결과를 검토하고 책임진다. AI 도구·공개 코드·모델·데이터의 출처와 사용 범위는 주최 측 지정 양식에 기재한다."
  ]
]);
const changes = [], blocks = new Map();
for (let i=0;i<records.length;i++) {
  const r=records[i]; if(r.tag!==67) continue;
  const text=r.data.toString('utf16le').replace(/\r$/,'');
  const keys=[...replacements.keys()].filter(k=>text.startsWith(k));
  if(!keys.length) continue; assert.equal(keys.length,1);
  const key=keys[0], next=replacements.get(key), j=i-1;
  assert.equal(records[j].tag,66); let end=j+1;
  while(end<records.length&&records[end].level>records[j].level)end++;
  assert(records.slice(j+1,end).every(x=>[67,68,69,70].includes(x.tag)));
  const header={...records[j],data:Buffer.from(records[j].data)};
  header.data.writeUInt32LE(((header.data.readUInt32LE(0)&0x80000000)|(next.length+1))>>>0,0);
  header.data.writeUInt32LE(0,4); header.data.writeUInt16LE(1,12); header.data.writeUInt16LE(0,14); header.data.writeUInt16LE(0,16);
  const shape=records.slice(j+1,end).find(x=>x.tag===68); assert(shape);
  const cs={...shape,data:Buffer.from(shape.data.subarray(0,8))};cs.data.writeUInt32LE(0,0);
  blocks.set(j,{end,rs:[header,{tag:67,level:header.level+1,data:Buffer.from(next+'\r','utf16le')},cs]});
  changes.push({field:key,before:text,after:next});
}
assert.equal(changes.length,replacements.size);
const revised=[];
for(let i=0;i<records.length;) {const b=blocks.get(i);if(b){revised.push(...b.rs);i=b.end;}else revised.push(records[i++]);}
const newBody=Buffer.concat(revised.flatMap(r=>{
  const n=r.data.length, h=Buffer.alloc(n>=4095?8:4);
  h.writeUInt32LE((r.tag|(r.level<<10)|(Math.min(n,4095)<<20))>>>0);
  if(n>=4095)h.writeUInt32LE(n,4);return [h,r.data];
}));
const result=CFB.utils.cfb_new();
for(let i=0;i<original.FileIndex.length;i++) {
  const e=original.FileIndex[i], p=original.FullPaths[i];if(e.type!==2)continue;
  let data=Buffer.from(e.content);
  if(p.endsWith('/BodyText/Section0'))data=zlib.deflateRawSync(newBody);
  if(p.endsWith('/PrvText'))data=Buffer.from('해피 KitGuard 참가신청서·개발계획서 — 2026.9.29 수정\r\n프로젝트 목표·개발 방법·검증 계획을 확인하십시오.\r\n','utf16le');
  CFB.utils.cfb_add(result,p,data);
}
CFB.utils.cfb_gc(result);
const dest=path.join(base,file);CFB.write(result,{type:'file',filename:dest});
const verify=CFB.read(dest,{type:'file'});
for(let i=0;i<original.FileIndex.length;i++) {
  const e=original.FileIndex[i],p=original.FullPaths[i];if(e.type!==2||p.endsWith('/BodyText/Section0')||p.endsWith('/PrvText'))continue;
  assert.deepStrictEqual(Buffer.from(CFB.find(verify,p).content),Buffer.from(e.content),p);
}
assert.deepStrictEqual(zlib.inflateRawSync(CFB.find(verify,'/BodyText/Section0').content),newBody);
assert.equal(revised.filter(r=>r.tag===66).length,records.filter(r=>r.tag===66).length);
assert.equal(revised.filter(r=>r.tag===85).length,1);
const textRecords=rs=>rs.filter(r=>r.tag===67).map(r=>r.data.toString('utf16le'));
const oldText=textRecords(records),newText=textRecords(revised);
assert.equal(oldText.length,newText.length);
assert.equal(oldText.filter((t,i)=>t!==newText[i]).length,replacements.size);
const removedNarratives=['2026.9.26','9월 26','사전 개발','사전 연구','기존 원형','진행한 이력','개발을 중단','개발 중단','기존 코드·시험','허용된 기존 자산'];
for(const phrase of removedNarratives) assert(!newText.some(t=>t.includes(phrase)),phrase);
fs.writeFileSync(path.join(base,'修订正文.body'),newBody);
fs.writeFileSync(path.join(base,'修订前后对照.json'),JSON.stringify(changes,null,2));
fs.writeFileSync(path.join(base,'HWP结构核查.json'),JSON.stringify({source_sha256:sha(beforeBytes),revised_sha256:sha(fs.readFileSync(dest)),changed_paragraphs:changes.length,signature_image_and_other_streams_unchanged:true,official_clauses_and_identity_fields_unchanged:true,native_layout_verification:'pending'},null,2));
fs.copyFileSync(dest,'/tmp/kitguard-registration-plan-20260929.hwp');
console.log(JSON.stringify({file:dest,changed_paragraphs:changes.length,sha256:sha(fs.readFileSync(dest))}));
