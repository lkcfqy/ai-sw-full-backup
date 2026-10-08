#!/usr/bin/env node
/**
 * Eight-slide Korean v0.7.0 submission. Completed, independently audited evidence.
 * Presentations create marker was invoked once before this authoring operation.
 * Does not invoke MLX. Requires the full audited 153-attempt run. Historical
 * datasets stay separate and never contribute to the new-51 denominator.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const SKILL='/Users/lkc/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations';
const RUNTIME='/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const PYTHON=path.join(RUNTIME,'python/bin/python3');
const FONT='Apple SD Gothic Neo';
const args=process.argv.slice(2);
const val=(flag,fallback)=>{const i=args.indexOf(flag);return i<0?fallback:args[i+1];};
const absolute=p=>path.resolve(ROOT,p);
const read=p=>fs.readFile(absolute(p),'utf8').then(JSON.parse);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const digest=p=>fs.readFile(absolute(p)).then(sha);
const OUT=absolute(val('--output','output/presentations/v0.7-final/KitGuard_발표_v0.7.0_v1.pptx'));
const BUILD=absolute(val('--build-dir','.presentation-v07-build/final-v1'));
const DEMO='test-results/browser/public-review-v07/demonstration';
const sources={
  report:'docs/v0.7/RESULT_REPORT_KO_FINAL.md',
  agent:'docs/v0.7/AGENT_TECH_KO_FINAL.md',
  review:'docs/v0.7/PUBLIC_REVIEW_API.md',
  plan:'docs/v0.7/PUBLIC_EVALUATION_PLAN.md',
  freeze:'docs/v0.7/public_paired_freeze_v1/freeze.json',
  manifest:'datasets/derived/v0.7/public_paired_v1/manifest.json',
  historical64:'evaluation-runs/v03_guarded_holdout_v1/gate_report_v1.json',
  development28:'test-results/v0.7/development28-audit-v1.json',
  timeline:`${DEMO}/timeline.json`,
  completedRun:'evaluation-runs/v0.7/public_paired_v1/run.json',
  freshAnalysis:'evaluation-runs/v0.7/public_paired_v1/analysis.json',
  freshPredictions:'evaluation-runs/v0.7/public_paired_v1/predictions.jsonl',
  independentAudit:'test-results/v0.7/public-paired-audit-v1.json',
  auditor:'scripts/v07/audit_public_paired.py',
  auditNote:'docs/v0.7/PUBLIC_PAIRED_AUDIT.md',
};
const freeze=await read(sources.freeze), old64=await read(sources.historical64), dev28=await read(sources.development28);
assert.equal(freeze.cases,51);assert.equal(freeze.attempts,153);
assert.deepEqual(freeze.modes,['spatial_inventory','spatial_guarded','selective_identity_experimental_v1']);
assert.equal(await digest(sources.manifest),freeze.manifest_sha256);
assert.equal(await digest(sources.freeze),'cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7');
assert.equal(old64.complete,true);assert.equal(old64.completed_images,64);
assert.deepEqual(['C','W','U','E'].map(k=>old64.candidate[k]),[59,0,5,0]);
assert.deepEqual(['C','W','U','E'].map(k=>old64.baseline[k]),[62,2,0,0]);
assert.equal(dev28.status,'passed');assert.equal(dev28.completed_cases,28);
assert.equal(dev28.source_changed_during_run,false);assert.equal(dev28.normalized_inputs_identical,28);
assert.deepEqual(dev28.candidate_outcomes,{C:25,W:0,U:3,E:0});
assert.equal(dev28.timing_comparison_valid_for_speed_claim,false);
const audit=await read(sources.independentAudit), complete=await read(sources.completedRun);
assert.equal(audit.status,'passed');assert.equal(audit.completed_attempts,153);
assert.equal(complete.status,'completed');assert.equal(complete.source_changed,false);
assert.equal(audit.source_snapshot_files_verified,62);assert.equal(audit.model_loaded_or_called,false);
assert.equal(await digest(sources.independentAudit),'94c71e45341a5065ee90fe601e606cd3a54242094d5dcc08770f6aae8c588fe9');
assert.equal(await digest(sources.freshAnalysis),audit.artifacts_sha256['analysis.json']);
assert.equal(await digest(sources.freshPredictions),audit.evidence_sha256.predictions);
assert.equal(await digest(sources.auditor),audit.evidence_sha256.auditor);
const fresh=audit.independent_results;
const modes=['spatial_inventory','spatial_guarded','selective_identity_experimental_v1'];
assert.deepEqual(modes.map(m=>['C','W','U','E','N'].map(k=>fresh.modes[m].all.outcomes[k])),[[46,5,0,0,0],[41,3,7,0,0],[46,4,1,0,0]]);
assert.deepEqual(modes.map(m=>fresh.modes[m].all.any_false_ready_images),[5,3,4]);
assert.equal(fresh.comparisons_vs_inventory.spatial_guarded.engineering_acceptance_passed,false);
assert.equal(fresh.selective_identity_further_validation_gate.eligible_for_further_validation,false);
const predictions=(await fs.readFile(absolute(sources.freshPredictions),'utf8')).trim().split('\n').map(JSON.parse);
const errorAttempt=audit.attempt_audits.find(r=>r.mode==='spatial_guarded'&&r.outcome==='W');
const errorRow=predictions[errorAttempt.attempt-1];
assert.equal(errorAttempt.attempt,92);assert.equal(errorRow.ground_truth.nut,1);assert.equal(errorRow.observation.observed.nut,0);
assert.equal(errorRow.observation.observed.washer,1);
assert.ok(errorRow.observation.verification.passes.every(r=>r.observed.nut===0&&r.observed.washer===1));
assert.equal(errorRow.observation.identity_verification.response.objects[0].part,'washer');
const errorCrop='evaluation-runs/v0.7/public_paired_v1/cases/092-spatial_guarded/call-03/image-02.png';
assert.equal(await digest(errorCrop),audit.artifacts_sha256['cases/092-spatial_guarded/call-03/image-02.png']);
const fasterPct=(100*(1-fresh.modes[modes[2]].all.latency_all_attempted.median_ms/fresh.modes[modes[1]].all.latency_all_attempted.median_ms)).toFixed(1);
assert.equal(fasterPct,'28.4');

const timeline=await read(sources.timeline);
for(const key of ['04-r1-actual-difference','08-r2-invalidates-r1','10-r2-real-result']){
  assert.ok(timeline.find(x=>x.name===key+'.png'),`No recorded UI evidence for ${key}`);
}
const demoOrderArg=val('--demo-order',`${DEMO}/order.json`);
let demoOrder=null;
if(demoOrderArg){
  const exportRecord=await read(demoOrderArg);
  demoOrder=exportRecord.order ?? exportRecord;sources.demoOrder=demoOrderArg;
  assert.equal(demoOrder.revision,2);
  assert.equal(demoOrder.demo_source?.physical_completion_allowed,false);
  assert.ok(demoOrder.checks.some(c=>c.revision===1&&c.valid===false));
  assert.ok(demoOrder.checks.some(c=>c.revision===2));
  assert.deepEqual(demoOrder.completions,[]);
  assert.equal(demoOrder.id,'ord_01a0e1e0cd8f49b3bb67');
  const r1=demoOrder.checks.find(c=>c.revision===1), r2=demoOrder.checks.find(c=>c.revision===2);
  assert.equal(r1.decision,'correct');assert.equal(r2.decision,'ready');
  assert.deepEqual(r1.requirements_snapshot,{bolt:3,nut:2,washer:2,bracket:0});
  assert.deepEqual(r2.requirements_snapshot,{bolt:2,nut:2,washer:2,bracket:0});
  assert.deepEqual(r1.observed,r2.requirements_snapshot);assert.deepEqual(r2.observed,r1.observed);
  assert.equal(r1.photo_sha256,r2.photo_sha256);
  assert.equal(r1.backend,'mlx');assert.equal(r2.backend,'mlx');
  assert.equal(r1.latency_ms,51488);assert.equal(r2.latency_ms,46614);
  assert.equal(demoOrder.public_replays.length,1);
  assert.equal(demoOrder.public_replays[0].physical_capture,false);
  assert.equal(demoOrder.public_replays[0].requires_new_inference,true);
  assert.equal(demoOrder.public_reviews.length,2);
  assert.ok(demoOrder.public_reviews.every(r=>r.physical_completion===false && r.user_validation===false));
  for(const step of ['04-r1-actual-difference','08-r2-invalidates-r1','10-r2-real-result']){
    assert.ok(timeline.find(x=>x.name===step+'.png')?.url.includes(demoOrder.id));
  }
}
const sourceRecord={};
for(const [key,p]of Object.entries(sources))sourceRecord[key]={path:p,sha256:await digest(p)};
const imageRecord={};
async function asset(p){const bytes=await fs.readFile(absolute(p));imageRecord[p]=sha(bytes);return new Uint8Array(bytes);}
if(args.includes('--validate-only')){console.log(JSON.stringify({status:'evidence_valid',new51:'completed_independently_audited',sourceRecord},null,2));process.exit(0);}
try{await fs.access(OUT);throw Error(`Final output already exists: ${OUT}`);}catch(e){if(e.code!=='ENOENT')throw e;}
await fs.mkdir(BUILD,{recursive:true});await fs.mkdir(path.dirname(OUT),{recursive:true});
const runtimeRequire=createRequire(path.join(RUNTIME,'node/package.json'));
process.env.RUNTIME_NODE_MODULES=path.join(RUNTIME,'node/node_modules');
const {Presentation,PresentationFile,FileBlob}=await import(pathToFileURL(runtimeRequire.resolve('@oai/artifact-tool')).href);
const {GlobalFonts}=runtimeRequire('@napi-rs/canvas');
assert.ok(GlobalFonts.families.some(x=>x.family===FONT),'Korean presentation font unavailable');
const {finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={ink:'#163D35',green:'#176F5B',muted:'#536961',paper:'#F7F7F0',rule:'#CED8CC',amber:'#996625',pale:'#E7EEE3',white:'#FFFFFF'};
function text(s,t,x,y,w,h,size=28,color=C.ink,bold=false){
  const b=s.shapes.add({geometry:'textbox',name:t.slice(0,64),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  b.text=t;b.text.style={typeface:FONT,fontSize:size,color,bold,autoFit:'none',wrap:true};return b;
}
function slide(n,title,kicker){const s=p.slides.add();s.background.fill=C.paper;text(s,kicker,64,30,1148,31,19,C.green,true);text(s,title,64,72,1152,73,43,C.ink,true);text(s,'해피 팀   KitGuard v0.7.0   2026.10.02',64,680,1020,24,17,C.muted);text(s,String(n).padStart(2,'0'),1162,676,58,31,23,C.muted);return s;}
function note(s,body,keys=[]){s.speakerNotes.textFrame.setText(body+'\n\nSources:\n'+keys.map(k=>`${sourceRecord[k]?.path||k}${sourceRecord[k]?' SHA256 '+sourceRecord[k].sha256:''}`).join('\n'));}
async function image(s,file,x,y,w,h,alt,crop){return s.images.add({blob:await asset(file),contentType:'image/png',fit:crop?'cover':'contain',position:{left:x,top:y,width:w,height:h},alt,...(crop?{crop}:{} )});}
function table(s,values,x,y,w,h,widths,size=23){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});
 t.borders.assign({style:'solid',fill:C.rule,width:1});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){const cell=t.getCell(r,c);cell.fill=r===0?C.ink:C.white;cell.text.style={typeface:FONT,fontSize:size,bold:r===0,color:r===0?C.white:C.ink,autoFit:'none'};}
 return t;
}
function node(s,label,sub,x,y,w=208,h=104){const b=s.shapes.add({geometry:'rect',name:label,position:{left:x,top:y,width:w,height:h},fill:C.white,line:{fill:C.green,width:1.5}});text(s,label,x+17,y+17,w-34,37,26,C.ink,true);text(s,sub,x+17,y+60,w-34,35,18,C.muted);return b;}
function connect(s,a,b,fromSide='right',toSide='left',kind='straight',color=C.green){s.shapes.connect(a,b,{kind,fromSide,toSide,line:{fill:color,width:2},tail:{type:'arrow',width:'med',length:'med'}});}
const publicLicense='MVTec LOCO AD and MVTec Screws public research data, CC BY-NC-SA 4.0. https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad ; https://www.mvtec.com/research-teaching/datasets/mvtec-screws ; https://creativecommons.org/licenses/by-nc-sa/4.0/ . Images are public development examples, not field or user-validation photographs. Native editable diagrams describe implemented program flow.';
// 1. Product and concrete problem. Public photograph is source evidence.
{
 const s=p.slides.add();s.background.fill=C.paper;
 text(s,'KitGuard',64,55,625,90,64,C.ink,true);
 text(s,'사진·BOM 자료 검토 Agent',66,153,600,47,30,C.green,true);
 text(s,'사진은 그대로인데\n주문 수량이 바뀌면?',64,276,635,160,50,C.ink,true);
 text(s,'현재 버전과 사진, 판단 근거를\n함께 확인하고 기록합니다.',66,500,605,93,31);
 await image(s,'datasets/derived/v0.3/screws_views/v03-screws-screws_344-8d389e404b12.png',749,187,450,322,'MVTec Screws public development crop with three screws');
 text(s,'같은 사진도 주문이 바뀌면 다시 검토',747,542,463,75,26,C.green,true);
 text(s,'해피 팀   v0.7.0   2026.10.02',64,677,800,27,19,C.muted);
 text(s,'공개 연구용 사진   MVTec / CC BY-NC-SA 4.0',746,646,473,34,17,C.muted);
 note(s,'Target users are a hypothesis: small assembly, education and photo-document review teams. The problem is stale evidence after a BOM version change. No customer, field throughput, paid adoption or ROI is claimed. The displayed photo has been used in development and is not in the new-51 evaluation. '+publicLicense,['report','kitguard/public_demo_catalog.py']);
}
// 2. Editable task flow with explicit feedback/state transition.
{
 const s=slide(2,'사진 검토부터 근거 내보내기까지','구현한 디지털 업무 흐름');
 text(s,'하나의 주문에 버전별 사진과 판단을 연결합니다.',64,157,1134,50,30,C.muted);
 const a=node(s,'주문·사진','BOM과 출처',64,269);
 const b=node(s,'로컬 AI 관찰','물체 목록과 위치',298,269);
 const c=node(s,'수량 대조','프로그램 규칙',532,269);
 const d=node(s,'검토 기록','동의·보류·이견',766,269);
 const e=node(s,'근거 저장','JSON·ZIP·HTML',1000,269);
 [a,b,c,d].forEach((v,i)=>connect(s,v,[b,c,d,e][i]));
 const f=node(s,'새 버전·추가 자료','이전 결과 무효화',415,480,390,104);
 connect(s,c,f,'bottom','top','elbow');connect(s,f,a,'left','bottom','elbow');
 text(s,'불확실하면 추가 자료 또는 수동 검토',829,480,372,90,30,C.green,true);
 text(s,'공개 사진의 디지털 검토는 실물 보충·출고 완료를 기록하지 않습니다.',64,628,1148,36,23,C.muted);
 note(s,'Native editable flow diagram. Implemented observation and deterministic count/version rules, digital public review and export are shown. A changed BOM invalidates prior checks, while preserving history. Reviewer opinions never overwrite original AI observations. Repeated uncertain evidence can route to manual review. Public-photo replay is explicit and requires a new inference. '+publicLicense,['report','agent','review','kitguard/app.py','kitguard/store.py','kitguard/public_review.py']);
}
// 3. Actual Korean browser run. Keep two real screenshots and their sequence.
{
 const s=slide(3,'실제 실행: R1 차이 확인, R2 다시 검사','같은 공개 사진을 명시적으로 재사용');
 text(s,'R1   볼트 필요 3개 / 관찰 2개',64,162,558,46,29,C.ink,true);
 text(s,'R2   볼트 필요 2개 / 관찰 2개',664,162,550,46,29,C.green,true);
 await image(s,`${DEMO}/04-r1-actual-difference.png`,64,225,552,311,'Actual Korean browser R1 difference and local inference result');
 await image(s,`${DEMO}/10-r2-real-result.png`,664,225,552,311,'Actual Korean browser R2 matching result after explicit same-photo reuse');
 text(s,'사용자 지시·승인으로만 주문 변경\nR1의 차이는 그 버전 이력에 유지',64,565,554,82,28);
 text(s,'R2에서 새 추론을 실행합니다.\n새 촬영이나 실물 이동은 없습니다.',664,565,552,82,28);
 text(s,'자동화 개발 검수 화면입니다. 실제 사용자 연구나 현장 완료 실적이 아닙니다.',64,649,1150,26,19,C.muted);
 note(s,'Screenshots captured in the actual local Korean browser workflow on 2026-10-02 KST, order ord_01a0e1e0cd8f49b3bb67, bag-revision public development photo. R1 target bolt/nut/washer/bracket=3/2/2/0 and observed=2/2/2/0. The 3-to-2 change is a predetermined demo order scenario requested by the operator and committed only after explicit approval. The AI does not alter the target BOM to make a result ready. The shortage under fixed R1 remains in its history, and a match under R2 does not demonstrate physical replenishment. Korean instruction proposes bolt count 2, explicitly approved; R2 target=2/2/2/0, old R1 check invalidated; identical source photo explicitly replayed and independently re-inferred. R2 matches 2/2/2/0. Both actual checks match the exported JSON. R1 latency51,488ms and R2 latency46,614ms refer to machine observation only, not full human task duration. The three tool observations use the same model and are correlated. Public sources cannot produce physical completion. This is engineering integration evidence, not an accuracy sample or human review study. '+publicLicense,['timeline',...(demoOrderArg?['demoOrder']:[]),`${DEMO}/04-r1-actual-difference.png`,`${DEMO}/08-r2-invalidates-r1.png`,`${DEMO}/10-r2-real-result.png`]);
}
// 4. Responsibility mapping: a native editable table.
{
 const s=slide(4,'Agent 도구와 판단 규칙','목표: 현재 버전에 맞는 수량 판단');
 table(s,[['역할','실제로 실행하는 일'],['사진 관찰','원본과 90° 회전 사진에서 물체 목록 생성'],['조건부 확인','두 관찰이 일치하면 너트·와셔를 국소 확인'],['수량·다음 단계','프로그램이 계수·BOM 대조, 불확실하면 보류'],['상태·피드백','버전 변경 시 무효화, 추가 근거 또는 수동 검토']],64,185,1152,342,[270,882],28);
 text(s,'Qwen3.6-27B / MLX 4-bit   연구·디지털 검토 보조용 기본 절차',64,568,1150,42,29,C.green,true);
 text(s,'기대 BOM 수량은 시각 모델에 주지 않습니다. 같은 모델의 반복 관찰은 서로 독립적이지 않습니다.',64,625,1150,47,23,C.muted);
 note(s,'Current default spatial_guarded is a fixed-rule Agent. Original and rotated spatial inventories must clearly agree; conditional nut/washer identity checks follow when applicable. Program counts object lists and applies BOM difference and evidence validity. Unknown remains null rather than 0 or expected count. The base model is reused, not trained by this team. Self-developed components include inventory validation/counting, consensus and conditional identity, version/evidence state machine, digital review, UI and exports. The two orientations and local checks share one model and may repeat common errors. Source-specific physical category and SKU limitations remain.',['agent','report','kitguard/vision.py','kitguard/spatial.py','kitguard/identity.py','kitguard/app.py','kitguard/feedback.py']);
}
// 5. Completed frozen data and independently executed comparison design.
{
 const s=slide(5,'새 원본 51개, 3방법의 별도 실행 비교','사진·코드·순서를 추론 전에 동결');
 text(s,'35',65,162,200,95,69,C.green,true);text(s,'Screws 원본별 1개 영역 / 12가지 수량',65,266,552,46,27);
 text(s,'16',665,162,200,95,69,C.green,true);text(s,'LOCO 정상 원본',665,266,526,46,28);
 table(s,[['단일 관찰','현재 강화 절차','단방향 확인 후보'],['spatial_inventory','spatial_guarded','selective identity'],['각 51장 별도 실행','각 51장 별도 실행','각 51장 별도 실행']],64,338,1152,157,[384,384,384],24);
 text(s,'총 153회 관찰   같은 모델·입력·기록 경계   순서 균형',64,531,1152,47,31,C.ink,true);
 text(s,'저자 표기 기반 정답. 기존 사용 자료는 출처별 제외.\nLOCO 16장은 모두 2/2/2/0으로 상수 출력도 일치 가능.\n브래킷 양성·새 공장 검증 없음. 사전학습 중복은 미확인.',64,586,1152,87,22,C.muted);
 note(s,'Frozen protocol SHA256 cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7. 51 distinct source originals, 35 Screws views selected by deterministic crop rule without viewing predictions, 16 LOCO normal originals. All training/evaluation/development/demo source families found in local exposure audit were excluded, but pretrained overlap cannot be certified. Each arm uses app upload, identical normalized bytes, Qwen3.6-27B 4bit, max side 1536, same raw-text/image recording; each arm occurs 17 times in each of three order positions. Full denominator retains failures/unattempted cases. Any-false-ready is per-photo behavior over 255 legal BOM panels, not 255 additional photos or real orders. Source domain remains familiar. LOCO16 all have count vector2/2/2/0, so the constant-output comparator also matches all16; this stratum cannot establish superiority in anomaly discrimination. Screws35 includes12 distinct count vectors. No bracket-positive or fresh LOCO anomaly samples remain. '+publicLicense,['freeze','manifest','plan','development28']);
}
// 6. Complete new-51 evidence; historical results are separately labeled.
{
 const s=slide(6,'새 51장: 두 강화 방법 모두 기준 미통과','153/153 관찰 완료 · 원시 근거 독립 감사 통과');
 const labels=['단일 관찰','현재 강화 절차','단방향 확인 후보'];
 const values=[['방법','C / W / U / E / N','오확정 위험¹','중앙값','P90'],...modes.map((m,i)=>{
   const r=fresh.modes[m].all;
   return [labels[i],['C','W','U','E','N'].map(k=>r.outcomes[k]).join(' / '),`${r.any_false_ready_images}/51`,`${(r.latency_all_attempted.median_ms/1000).toFixed(3)}초`,`${(r.latency_all_attempted.p90_ms/1000).toFixed(3)}초`];
 })];
 table(s,values,64,180,1152,256,[300,252,220,190,190],25);
 text(s,'C 정답·확정 가능   W 확정 가능하지만 오답   U 보류   E 실패   N 미실행',64,455,1152,34,22,C.muted);
 text(s,'강화: 오류 2건을 보류했지만, 맞은 5건도 보류',64,509,1152,43,29,C.ink,true);
 text(s,`후보: 중앙값 ${fasterPct}% 단축, 오답 4건 남음 → 승격 없음`,64,560,1152,43,29,C.amber,true);
 text(s,'¹ 255개 합법 BOM 중 한 번이라도 잘못 준비됨을 표시할 사진 수 / 51',64,614,1152,28,20,C.muted);
 text(s,'과거 64장: 강화 C59/W0/U5  ·  개발 28장: 후보 C25/W0/U3  —  이번 51장과 합산 안 함',64,650,1152,27,19,C.muted);
 note(s,'Completed frozen new51 trial; full planned denominator51 per method,153 observations total. Inventory C46/W5/U0/E0/N0, guarded C41/W3/U7/E0/N0, candidate C46/W4/U1/E0/N0. Any-false-ready over all four broad categories is5/51,3/51,4/51. The source-supported panel is0/51 for every arm because the misclassified washers are outside the Screws positive-class domain; this narrower panel does not eliminate the observed nut-to-washer errors. Each photo is evaluated against255 legal BOMs, excluding its matched truth for the mismatched-order denominator; not extra photos or real customer orders. P50=8.962/21.814/15.625s; P90=14.550/46.231/31.896s; full attempt sums499.130/1352.628/927.090s. Timing includes upload and recorded observation, first cold load retained, same image/max-side/model and logging boundary. Candidate median is28.4% lower than guarded, but W4 and any-false-ready4 violate its preregistered safety gates. Guarded blocks2 wrong, abstains5 correct, retains3 wrong. Both enhancement methods fail preregistered acceptance; descriptive safety superiority is NOT established. No automatic promotion. Audit independently reconstructed153 normalized inputs,272 raw calls,444 actual model images and172 identity crops from62 snapshot source/resources; no model loaded. The nested candidate first-pass wall timer is preserved and bounded, not expected to equal CPU replay duration. Historical64 is a separate prior experiment: same-run correlated first pass62/2/0/0 versus guarded59/0/5/0; its first pass is not an independent complete pipeline. Development28 is exposed: old guarded24/0/4/0 versus candidate25/0/3/0; timing boundaries differ, so no historical speed claim. Neither historical dataset contributes to new51 results.',['independentAudit','freshAnalysis','freshPredictions','auditor','auditNote','historical64','development28','freeze']);
}
// 7. Real local entry and commercial hypothesis.
{
 const s=slide(7,'로컬 자료 검토 도구로 시작합니다','활용 대상과 사업화는 검증할 가설');
 await image(s,`${DEMO}/01-public-library.png`,64,192,610,344,'Actual Korean public-photo library entry in local browser');
 text(s,'사진과 BOM을 가진 소규모 팀',730,189,483,56,31,C.green,true);
 text(s,'반복 수량 확인과 주문 변경 검토\n버전별 근거를 관리자에게 전달',730,268,483,116,30);
 text(s,'수익 모델 가설',730,432,483,45,30,C.ink,true);
 text(s,'팀 단위 이용·유지보수\n초기 설치와 BOM 연동 지원',730,495,483,100,29);
 text(s,'검증 환경: Apple M5 Pro / 64GB\n로컬 단일 사용자, 조직 권한 관리 미제공',64,566,610,84,26,C.muted);
 text(s,'유료 고객·매출·가격 수용도·인건비 절감률은 아직 검증하지 않았습니다.',64,649,1152,28,21,C.muted);
 note(s,'The screenshot is the actual local library start page, not a mockup. Verified host Apple M5 Pro64GB, Python3.12, localhost127.0.0.1. Regular inference uses local MLX without external model upload. Product adoption and team subscriptions/maintenance or installation/BOM integration support are hypotheses, with no paid customers, pricing study or ROI claim. Existing model weights and configured environment are required; another machine or CUDA throughput not tested. Customers must hold rights to their own photos. Public research image license does not grant commercial customer-data usage rights. '+publicLicense,['report','timeline',`${DEMO}/01-public-library.png`,'docs/v0.7/SOURCE_PACKAGING.md']);
}
// 8. An actual retained wrong case makes the shared-model limitation concrete.
{
 const s=slide(8,'같은 모델의 반복 확인도 함께 틀립니다','실제 오류와 다음 검증');
 await image(s,errorCrop,64,182,264,264,'Actual retained identity input from a wrongly classified nut, public Screws source120');
 text(s,'저자 정답: 너트',363,184,310,46,28,C.ink,true);
 text(s,'원본 관찰 → 와셔\n90° 관찰 → 와셔\n국소 확인 → 와셔',363,253,310,165,27,C.amber);
 text(s,'강화 절차 오류 3건 모두 같은 유형\n저자 정답 유지 · 사후 정답 수정 없음',64,476,574,88,27);
 text(s,'다음 실제 업무 검증',719,177,496,50,32,C.green,true);
 text(s,'권한 있는 자료로 담당자가 검토\n전체 검토 시간·잘못된 확정 측정\n별도 현장 자료에서 오류 확인',719,257,496,169,29);
 text(s,'4종 거친 분류 · 종류별 0–3개\nSKU·규격·재질, 현장 효용은 미검증',719,470,496,94,26,C.muted);
 text(s,'기본 절차는 연구·디지털 보조 범위에 유지',64,606,1152,42,29,C.green,true);
 text(s,'연구용 공개 사진: 비상업 조건 적용. 해시는 새 촬영·실물 완료를 인증하지 않습니다.',64,651,1152,28,20,C.muted);
 note(s,'Displayed image is the actual retained model identity input, attempt92 spatial_guarded, casev07-screws-screws_120-3e86c9ca51d9, not an illustration or a new evaluation. Author truth bolt1/nut1/washer0/bracket0 remains unchanged. Both orientations and identity classify its nut as washer; source-backed exact raw outputs are retained. The3 guarded wrong cases are Screws120,024,172 and share nut-to-washer confusion. This qualitative selection is post-hoc error explanation, not evidence for an improved method and not used to change truth or tune a new candidate on these51. The crop is interpolation of existing pixels, not new evidence. Current default remains research/digital-review assistance and is not a field-safety release. Four broad classes,0–3 each,total1–12; benchmark has no bracket-positive evidence. Unknown SKU/spec/material and real customer field usefulness remain. Real people must supply user review time and feedback; ENGINEERING-CODEX records are integration tests. Future tasks require authorized own materials and independently collected field evidence. Public data license is not a commercial-data authorization. '+publicLicense,['independentAudit','freshPredictions','manifest','report','review',errorCrop]);
}
assert.equal(p.slides.items.length,8);
const candidate=path.join(BUILD,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
const owners=[4,5,6];
await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath:OUT,pythonExecutable:PYTHON,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...owners.flatMap(n=>['--require-native-table-slide',String(n)])],explicitTotalSlideCount:8,requiredNativeTableOwnerSlides:owners,requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
const final=await PresentationFile.importPptx(await FileBlob.load(OUT));
const renderDir=path.join(BUILD,'rendered-final');await fs.mkdir(renderDir,{recursive:true});
for(let i=0;i<8;i++){
 const item=final.slides.getItem(i);const png=await final.export({slide:item,format:'png',scale:1.5});
 await fs.writeFile(path.join(renderDir,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
 const layout=await item.export({format:'layout'});await fs.writeFile(path.join(BUILD,`slide-${i+1}.layout.json`),await layout.text());
}
await fs.writeFile(path.join(BUILD,'source-index.json'),JSON.stringify({sourceRecord,imageRecord,new51Results:'completed-independent-audit-passed',demoOrderAttached:!!demoOrder,output:path.relative(ROOT,OUT),output_sha256:await digest(OUT)},null,2)+'\n');
console.log(JSON.stringify({status:'finalized_rendered_needs_visual_QA',slides:8,output:OUT,build_dir:BUILD,render_dir:renderDir,sha256:await digest(OUT)},null,2));
