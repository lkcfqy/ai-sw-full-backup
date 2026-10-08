#!/usr/bin/env node
// Korean preview deck. No inference, source-image edits, or v0.7 mutations.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const SKILL='/Users/lkc/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations';
const RUNTIME='/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const PYTHON=path.join(RUNTIME,'python/bin/python3');
const FONT='Apple SD Gothic Neo';
const VERSION='0.8.0.dev1';
const args=process.argv.slice(2);
function arg(name,fallback){const i=args.indexOf(name);return i<0?fallback:args[i+1];}
const OUT=path.resolve(ROOT,arg('--out','output/slides/v0.8-preview/KitGuard_발표_v0.8.0.dev1_preview_r2.pptx'));
const BUILD=path.resolve(ROOT,arg('--build','tmp/v08-slides-preview-build-02'));
assert.ok(OUT.startsWith(ROOT+path.sep)&&BUILD.startsWith(ROOT+path.sep),'Paths must stay in workspace');
assert.ok(!BUILD.startsWith(path.dirname(OUT)+path.sep),'Private validation must stay outside output');
const browser='test-results/browser/photo-document-live-v08';
const sources={
  update:'docs/v0.8/DELIVERY_UPDATE_PLAN.md',
  guide:'docs/v0.8/PHOTO_DOCUMENT_GUIDE_KO_ZH.md',
  reference:'docs/v0.8/REFERENCE_INPUT_EVIDENCE_CHANGE.md',
  recovery:'docs/v0.8/INSPECTION_RECOVERY_FIX.md',
  recoveryReceipt:'test-results/browser/workflow-readonly-v08/final-receipt.json',
  live:'test-results/v0.8/photo-document-live-api-v1/receipt.json',
  referenceLive:'test-results/v0.8/reference-live-api-v1/receipt.json',
  browser:`${browser}/browser-receipt.json`,
  order:`${browser}/order.json`,
  download:`${browser}/download-verification.json`,
  locoResult:'docs/v0.8/LOCO_COMBINED_RESULT.md',
  locoDecision:'docs/v0.8/LOCO_COMBINED_DECISION.json',
  locoAudit:'test-results/v0.8-loco-combined-independent-audit-v2.json',
  identityResult:'docs/v0.8/IDENTITY_REFERENCE_GUARDED_RESULT.md',
  identityDecision:'docs/v0.8/IDENTITY_REFERENCE_GUARDED_DECISION.json',
  original51:'docs/v0.7/FINAL_EVALUATION.md',
  contributions:'docs/v0.7/CONTEST_PERIOD_CONTRIBUTIONS.md',
  contributions08:'docs/v0.8/CONTEST_PERIOD_CONTRIBUTIONS.md',
  rules:'docs/v0.7/OFFICIAL_RULE_CHECK_20261002.txt',
  tests:'test-results/v0.8-preview-full-v1.log',
  project:'pyproject.toml',
};
const digest=b=>crypto.createHash('sha256').update(b).digest('hex');
const read=p=>fs.readFile(path.resolve(ROOT,p));
const json=async p=>JSON.parse(await read(p));
const sha=async p=>digest(await read(p));
const sourceRecord={};
for(const [key,p]of Object.entries(sources))sourceRecord[key]={path:p,sha256:await sha(p)};
const live=await json(sources.live), br=await json(sources.browser);
const order=(await json(sources.order)).order;
const loco=await json(sources.locoDecision), audit=await json(sources.locoAudit);
const identity=await json(sources.identityDecision), reference=await json(sources.referenceLive);
const recovery=await json(sources.recoveryReceipt);
const auditG=audit.independent_analysis.methods.spatial_guarded;
assert.ok((await read(sources.project)).toString().includes(`version = "${VERSION}"`));
assert.equal(live.status,'passed');assert.equal(live.human_participants,0);
assert.equal(live.inspect_attempts,2);assert.equal(live.model_calls_completed,6);
assert.equal(live.source_unchanged,true);assert.equal(live.physical_completion,false);
assert.equal(br.status,'passed_read_only_display_and_download');
assert.equal(br.prior_real_api_run.receipt_sha256,sourceRecord.live.sha256);
assert.equal(br.browser_scope.additional_model_calls,0);
assert.equal(br.human_participants,0);assert.equal(br.saved_order_unchanged,true);
assert.equal(order.id,live.order_id);assert.equal(order.revision,2);
assert.equal(order.document_source.verification,'user_declared_unverified');
assert.equal(order.checks.length,2);assert.equal(order.public_reviews.length,2);
assert.equal(order.public_replays.length,1);assert.equal(order.completions.length,0);
assert.ok(order.public_reviews.every(x=>x.operator_code==='ENGINEERING-AGENT'&&x.conclusion==='inconclusive'&&x.user_validation===false&&x.physical_completion===false));
const r1=order.checks.find(x=>x.revision===1),r2=order.checks.find(x=>x.revision===2);
assert.equal(r1.backend,'mlx');assert.equal(r2.backend,'mlx');
assert.deepEqual([r1.decision,r2.decision],['correct','ready']);
assert.deepEqual([r1.latency_ms,r2.latency_ms],[50909,47728]);
assert.equal(r1.requirements_snapshot.bolt,3);assert.equal(r2.requirements_snapshot.bolt,2);
assert.deepEqual(r1.observed,{bolt:2,nut:2,washer:2,bracket:0});
assert.deepEqual(r1.observed,r2.observed);assert.equal(r1.photo_sha256,r2.photo_sha256);
assert.equal(audit.status,'passed');assert.equal(loco.independent_integrity_audit,'passed');
assert.deepEqual(loco.outcomes,{C:23,W:0,U:1,E:0,N:0});
assert.deepEqual(loco.outcomes,auditG.outcomes);assert.deepEqual(loco.groups,auditG.groups);
assert.equal(loco.population.planned,24);assert.ok(loco.groups.every(x=>x.planned===6));
assert.equal(loco.false_ready_panels.primary_all_four.observed_any_false_ready_images,0);
assert.equal(loco.matched_order_applicable,12);assert.equal(loco.matched_order_not_applicable_count4,12);
assert.equal(loco.matched_order_correct_ready,11);assert.equal(loco.automatic_promotion,false);
for(const key of ['locoResult','locoAudit']){
 const entry=loco.evidence.find(x=>x.path===sources[key]);assert.ok(entry);assert.equal(entry.sha256,sourceRecord[key].sha256);
}
assert.deepEqual(loco.old51_guarded_remains.outcomes,{C:41,W:3,U:7,E:0,N:0});
assert.deepEqual(identity.outcomes,{C:40,W:3,U:8,E:0,N:0});
assert.equal(identity.decision,'candidate_rejected');assert.equal(identity.automatic_promotion,false);
assert.equal(reference.status,'passed');assert.equal(reference.generation_calls,3);
assert.deepEqual(reference.stages.map(x=>x.reference_image_indices),[[2,3],[2,3],[]]);
assert.equal(recovery.verification_scope.synthetic_observer_calls,4);
assert.equal(recovery.verification_scope.real_model_calls,0);
assert.equal(sourceRecord.tests.sha256,'fee1e1e353c87c9c3bedc3f02821f208bf5b41f5ddb29f3332092c29503785da');
assert.match((await read(sources.tests)).toString(),/1530 passed, 2 warnings in 42\.49s/);
const images={};
for(const name of ['r2-ko.jpg','r1-history-zh.jpg','reviews-zh.jpg']){
 const p=`${browser}/${name}`;images[p]=await sha(p);assert.equal(images[p],br.artifacts_sha256[p]);
}
if(args.includes('--validate-only')){console.log(JSON.stringify({status:'source_evidence_valid',version:VERSION,preview:true,sourceRecord,images},null,2));process.exit(0);}
try{await fs.access(OUT);throw Error(`Refusing to overwrite ${OUT}`);}catch(e){if(e.code!=='ENOENT')throw e;}
await fs.mkdir(BUILD,{recursive:true});await fs.mkdir(path.dirname(OUT),{recursive:true});
const runtimeRequire=createRequire(path.join(RUNTIME,'node/package.json'));
process.env.RUNTIME_NODE_MODULES=path.join(RUNTIME,'node/node_modules');
const {Presentation,PresentationFile,FileBlob}=await import(pathToFileURL(runtimeRequire.resolve('@oai/artifact-tool')).href);
const {GlobalFonts}=runtimeRequire('@napi-rs/canvas');
assert.ok(GlobalFonts.families.some(x=>x.family===FONT),'Korean font unavailable');
const {finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={ink:'#123D35',green:'#17725C',muted:'#566B64',paper:'#F8F8F2',rule:'#D4DDD4',amber:'#996227',white:'#FFFFFF'};
function text(s,t,x,y,w,h,size=28,color=C.ink,bold=false){
 const b=s.shapes.add({geometry:'textbox',name:t.slice(0,64),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 b.text=t;b.text.style={typeface:FONT,fontSize:size,color,bold,autoFit:'none',wrap:true};return b;
}
function slide(n,title){const s=p.slides.add();s.background.fill=C.paper;text(s,title,64,47,1152,75,44,C.ink,true);text(s,`KitGuard ${VERSION} preview`,64,682,1070,22,16,C.muted);text(s,String(n).padStart(2,'0'),1166,676,52,30,22,C.muted);return s;}
function note(s,body,keys=[]){s.speakerNotes.textFrame.setText(body+'\n\n근거 / Sources\n'+keys.map(k=>`${sourceRecord[k]?.path||k}${sourceRecord[k]?' SHA256 '+sourceRecord[k].sha256:images[k]?' SHA256 '+images[k]:''}`).join('\n'));}
async function screenshot(s,name,x,y,w,h){const source=`${browser}/${name}`;s.images.add({blob:new Uint8Array(await read(source)),contentType:'image/jpeg',fit:'contain',position:{left:x,top:y,width:w,height:h},alt:`Actual saved MLX history with ENGINEERING-AGENT automated opinions, 0 human participants: ${name}`});}
function table(s,values,x,y,w,h,widths,size=25){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});
 t.borders.assign({style:'solid',fill:C.rule,width:1});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){const cell=t.getCell(r,c);cell.fill=r===0?C.ink:C.white;cell.text.style={typeface:FONT,fontSize:size,bold:r===0,color:r===0?C.white:C.ink,autoFit:'none'};}
 return t;
}
const realCaption='실제 MLX 이력 화면 / ENGINEERING-AGENT 자동화 검수 / 실제 참여자 0명';
const license='Displayed source photo: MVTec LOCO AD screw_bag/train/good/016.png, an already exposed public development example, CC BY-NC-SA 4.0. https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad ; https://creativecommons.org/licenses/by-nc-sa/4.0/ . Its upload declaration remains user-declared and unverified in the product. These are original screenshots, unmodified and fitted without cropping. No new inference, generated imagery, human feedback or physical replenishment is represented.';

// 1. Minimal cover and concrete product problem.
{
 const s=p.slides.add();s.background.fill=C.paper;
 text(s,'KitGuard',64,77,1146,110,82,C.ink,true);
 text(s,'사진·BOM 디지털 검토 Agent',68,205,1142,56,37,C.green,true);
 text(s,'주문이 바뀌면\n사진의 판단 근거도 다시 확인합니다',66,337,1118,145,48,C.ink,true);
 text(s,'내 사진으로 시작하고, 현재 버전의 AI 결과와 검토 이력을 함께 남깁니다.',68,550,1126,78,29,C.muted);
 text(s,'해피 팀   2026.10.02   0.8.0.dev1 preview',68,678,1130,26,19,C.muted);
 note(s,'KitGuard is a local prototype for digital review of a photograph against a bill of materials, not a field-completion result. Audience use is a hypothesis for small assembly/education/photo-document review teams. User-owned or lawfully obtained public images can be used without procuring physical hardware for this digital workflow. Version0.8.0.dev1 preview is not an official submission or eligibility decision. The project began2026-09-26; current additions and historical implementation are distinguished on slide8.',['guide','update','project','contributions']);
}
// 2. New entry and actual Korean current-state evidence.
{
 const s=slide(2,'내 사진으로 만드는 자료 주문');
 text(s,'JPEG / PNG / WebP',64,176,258,43,27,C.green,true);
 text(s,'사진 1장\n출처 설명\n종류별 BOM 0–3개',64,239,250,153,29);
 text(s,'출처·허가는 사용자 진술\n확인되지 않은 상태 유지',64,452,250,103,25,C.muted);
 text(s,'URL은 사진을\n대신 내려받지 않습니다.',64,579,250,69,23,C.muted);
 await screenshot(s,'r2-ko.jpg',341,160,875,459.3);
 text(s,realCaption,341,635,875,30,19,C.muted);
 note(s,'The new local-photo entry requires a JPEG/PNG/WebP file, source_note and legal BOM with each class0–3. URL/license_note are optional and unverified. Source URLs are not fetched. The root photograph and source declaration are bound; replacing a photograph requires a new document order. Public/web photographs may be used only with appropriate rights, never by claiming a license has been certified. This screenshot is currentR2 displayed by a cold realLocalVision service after the completed real API run; the browser performed GET only, no additional model call. API multipart upload succeeded. Browser file-chooser upload remains unverified due extension permission restrictions; no bypass was used. '+license,['guide','live','browser','order',`${browser}/r2-ko.jpg`]);
}
// 3. Actual responsibilities, including the new reference trace and recovery.
{
 const s=slide(3,'Agent 도구와 버전별 근거');
 table(s,[['도구','실제 동작','후속 처리·범위'],['사진 관찰','원본과 90° 회전에서 물체 목록 생성','일치할 때 조건부 국소 확인'],['수량 대조','프로그램이 목록을 계수하고 BOM과 비교','불확실한 수량은 보류'],['참고 이미지 추적','당시 이미지와 실제 참여 단계 표시','기본 국소 확인은 참고 미입력'],['상태·근거 저장','새 버전은 재검사, 현재 실패는 재시도 안내','AI 결과·의견·이력을 ZIP 보존']],64,172,1152,324,[230,533,389],25);
 text(s,'Qwen3.6-27B / MLX 4-bit   기본 절차 spatial_guarded',64,536,1152,43,30,C.green,true);
 text(s,'BOM 수량은 시각 모델에 주지 않습니다. 반복 관찰은 같은 모델의 상관된 판단입니다.',64,596,1152,51,25,C.muted);
 note(s,'This native editable table describes implemented fixed-rule Agent responsibilities, not autonomous control of physical parts. Original and rotated inventories condition the nut/washer identity check; program code counts, compares and updates evidence validity. The added product reference trace does not change prompt/count/call order. Actual reference integration receipt: original and rotate received indices[2,3], identity received[];1actual observation,3generations,51.650s. Historical records missing reference fields are not backfilled. Prepared reference PNG bytes are not retained by the product, so no full historical pixel-vault claim. Failure recovery was tested in a separate synthetic browser fixture:4synthetic calls,0models,0humans. Its current revision/photo/epoch failed/interrupted warning survives refresh and clears after newer evidence/success. These engineering scopes do not contribute to image recognition accuracy.',['reference','referenceLive','recovery','recoveryReceipt','guide']);
}
// 4. The order changes by an explicit preset request, not by a physical repair.
{
 const s=slide(4,'같은 사진, 바뀐 주문, 새로운 검사');
 text(s,'R1  볼트 필요 3개',64,173,293,45,29,C.ink,true);
 text(s,'관찰 2개 / 차이 −1\n50.909초',64,231,293,91,28);
 text(s,'예정된 요구 변경 승인',64,357,293,47,28,C.green,true);
 text(s,'R2  볼트 필요 2개\n같은 사진으로 새 추론\n관찰 2개 / 수량 일치\n47.728초',64,418,293,171,28);
 await screenshot(s,'r1-history-zh.jpg',374,164,842,441.9);
 text(s,'R1 차이와 이력 유지 / 새 촬영·실물 보충 없음',374,619,842,34,24,C.amber,true);
 text(s,realCaption,64,656,1152,25,19,C.muted);
 note(s,'R1 requires bolt/nut/washer/bracket3/2/2/0 and observes2/2/2/0, decisioncorrect(difference). The operator explicitly commits the predefined requirement change to2/2/2/0. This is an order-change engineering scenario, never physical replenishment or the AI editing its target to pass. R1check and R1review become historical-invalid; a recorded same-byte replay does not run the model and requires a new R2inspection. R2observes2/2/2/0 and decisionready only means digital photo/BOM agreement. R1latency50,909ms and R2latency47,728ms are persisted machine observation durations, not human task times. Six actual generations total, no retry. No references were supplied in this two-version integration. '+license,['live','browser','order',`${browser}/r1-history-zh.jpg`]);
}
// 5. Saved opinions are engineering records, explicitly not real people.
{
 const s=slide(5,'디지털 의견과 내려받는 기록');
 text(s,'검사 2회\n디지털 의견 2건\n같은 사진 재사용 1회\n실물 완료 0건',64,171,275,179,29,C.ink,true);
 text(s,'ENGINEERING-AGENT',64,407,275,40,24,C.green,true);
 text(s,'두 의견 모두 “판단 보류”\n실제 참여자 0명\n사용자 검증 실적 없음',64,463,275,128,26);
 await screenshot(s,'reviews-zh.jpg',348,159,868,455.5);
 text(s,'출처·버전·원 AI 결과·의견을 ZIP으로 보존',348,627,868,35,24,C.green,true);
 text(s,realCaption,64,656,1152,25,19,C.muted);
 note(s,'The two saved opinions are ENGINEERING-AGENT automated integration records, both inconclusive, user_validationfalse and physical_completionfalse. They prove API binding/history, not human acceptance, image truth or model accuracy. The real read-only browser pass verified R2current and R1history in Korean/Chinese and downloaded a ZIP. Four payload hashes across six ZIP members verified; saved order remained identical to prior API output. Source declaration remains unverified; physical completion and root replacement are blocked. The archive contains JSON/photos/standaloneHTML with history, but file:// visual inspection was blocked by browser policy and not bypassed. No offline visual pass is claimed. '+license,['browser','download','live','order',`${browser}/reviews-zh.jpg`]);
}
// 6. Full new composition denominator, including counts outside legal BOM range.
{
 const s=slide(6,'LOCO 수량 조합 24장 전체 결과');
 text(s,'정확·실행 가능 23   오답 0   보류 1   실패 0   미실행 0',64,140,1152,46,31,C.green,true);
 const rows=[['너트 / 와셔','사진 수','정답 / 보류','정답과 같은 BOM'],...loco.groups.map(g=>[`${g.counts.nut} / ${g.counts.washer}`,String(g.planned),`${g.outcomes.C} / ${g.outcomes.U}`,Math.max(g.counts.nut,g.counts.washer)>3?'N/A (4개 관찰)':'적용 가능'])];
 table(s,rows,64,213,1152,260,[273,194,277,408],25);
 text(s,'저자 조합 라벨로 정답 도출. 관찰 4개도 유효 / BOM은 종류별 최대 3개',64,494,1152,37,24,C.muted);
 text(s,'오확정 관측 사진 0/24¹   일치 주문 11/12   나머지 12장은 N/A',64,542,1152,43,28,C.ink,true);
 text(s,'분석 대조: 상수 2/2/2/0은 오답 24장 / 전체 보류는 보류 24장',64,589,1152,35,24,C.muted);
 text(s,'¹ 255개 BOM의 관련 규칙 검사 / 동일 도메인 / 모두 총 6개·볼트 2개·브래킷 0개',64,643,1152,30,21,C.muted);
 note(s,'Full frozen G-only24, completed and independent v2audit passed. C23W0U1E0N0; group truths bolt/nut/washer/bracket2/0/4/0,2/1/3/0,2/3/1/0,2/4/0/0 each6. Ground truth derives once-per-class global deltas from author labels, not mask instance counts or native count fields. The24sources were absent from the bounded prior exposure registry/rawRGBduplicate check, not proven unseen by pretraining or all people, and not independent physical/session samples. Count4is a valid observed inventory; it is never clipped or markedE. Twelve count4cases cannot have a legal exactly matched BOM(max3), hence matched taskN/A, but remain in all24 observation andfalse-ready denominators. Other12matched tasks11correctready. Main255panel6120relatedorders/6108mismatches,0/24anyfalse-ready; secondary63panel1500mismatches also0/24. Repeated rule panels are correlated, not additional independent images. Constant2/2/2/0controlC0W24U0andAFR24/24; alwaysabstainC0W0U24andAFR0/24. SingleUcase125originalwasher3/rotated2; finalwasherunknown,recapture,identityskipped. No post-hoc prompt or truth change. Saved71calltexts/163inputs were replay-audited without loading a model; replay proves consistency of saved artifacts, not independent historical generation authentication. P50all24observations46.901s, not whole product/user time. Production remains a research/digital aid, no promotion.',['locoResult','locoDecision','locoAudit']);
}
// 7. Keep the unresolved old domain and rejected candidate visible.
{
 const s=slide(7,'기존 51장의 오류는 그대로 남아 있습니다');
 table(s,[['기존 51장 별도 비교','C / W / U / E / N','오확정 위험'],['기본 G, 역사적 기록','41 / 3 / 7 / 0 / 0','3/51'],['정체 확인 단계 참고 후보 I','40 / 3 / 8 / 0 / 0','3/51']],64,177,1152,198,[530,365,257],27);
 text(s,'같은 세 오류 유지, 기존 정답 한 장을 추가 보류',64,411,1152,48,32,C.amber,true);
 text(s,'후보 거절 / 기본 절차 유지',64,472,1152,47,31,C.ink,true);
 text(s,'Screws type_007을 사전 규칙으로 nut에 투영한 3건을 washer로 오인\n참고 이미지 참여 기록은 추적 기능이며, 인식 개선을 입증하지 않습니다.',64,536,1152,84,25,C.muted);
 text(s,'C 정답·실행 가능 / W 명확한 오답 / U 보류 / E 실패 / N 미실행',64,641,1152,29,22,C.muted);
 note(s,'Historical G on complete old51 remainsC41W3U7E0N0(all-fourAFR3/51),35Screwsviews+16LOCOnormal. Identity-onlyfixedrefcandidateI full51C40W3U8E0N0, same3wrong plus1CtoU, rejected; no default change. Type007is the preserved author type projected by prior project/educationalalias mapping to nut, not an author-native literalnut annotation, and truth was not changed based on visual appearance. Both calls and identity use the same correlated model. Ireference roles appear only in conditional identity, not current default product identity. This exposed, nonconcurrent development comparison cannot establish causal or fresh-domain performance. It is not pooled with24. Historicalnormal16C14W0U2alone, alltruth2/2/2/0, constantnormalcouldmatch16/16. The24same-domain composition validation does not repair the3oldScrews errors. A separate two-spatial-reference candidate also rejected(C41W4U6), kept in research index rather than main results narrative.',['identityResult','identityDecision','locoDecision','original51']);
}
// 8. Provenance and next bounded validation, including actual development dates.
{
 const s=slide(8,'개발 이력과 다음 검증');
 text(s,'2026.09.26  실제 개발 시작',64,167,576,44,29,C.ink,true);
 text(s,'공식 개발기간 09.29–10.06\n사전 원형 사용 자격은 주최 측 확인 대기',64,230,578,94,26,C.muted);
 text(s,'10.02  이번 제품 추가분',64,358,578,45,29,C.green,true);
 text(s,'내 사진 주문, 참고 참여 기록, 실패 복구\n기존 관찰·버전 엔진 재사용',64,421,578,92,27);
 text(s,'기반 모델·공개 자료·AI 코딩 도움 공개\n연구 사진 CC BY-NC-SA 4.0 조건 유지',64,555,578,79,24,C.muted);
 text(s,'공학 회귀 1,530개 통과',716,167,500,45,31,C.green,true);
 text(s,'API·상태 처리 검증 수\n모델 사진 수·실제 사용자 수와 구분',716,230,500,90,26,C.muted);
 text(s,'다음 실제 업무 검증',716,358,500,45,29,C.ink,true);
 text(s,'권한 있는 사진으로 담당자가 직접 검토\n완료·실패·도움 요청과 전체 시간 기록',716,421,500,92,27);
 text(s,'현재 단일 로컬 사용 / 현장 효용 미검증\nSKU·규격·재질·브래킷 양성 미검증',716,555,500,79,24,C.muted);
 note(s,'Actual development started2026-09-26. Official competition development period2026-09-29 through10-06 appears in saved official rule https://contest.gnict.org/rule.php . A prior-development clause and disclosure allowance require organizer clarification; no organizer approval of the9/26prototype is attached. Neither eligibility approval nor disqualification is claimed. The whole project is not represented as built from zero during the competition period. Oct2currentwork added own-photo documents,actualreference tracing,recovery and corresponding evidence, reusing earlier observation/state engine. The current contribution comparison is against the earlier sealedOct2v0.7source, not a competition-start snapshot or authorship certificate. Qwen/MLX,FastAPI/SQLite/Pillow,publicdata and OpenAICodexcodinghelp are disclosed in project sources; base model was not trained from scratch by the team. Full engineering suite1530passed,2existingwarnings,42.49s from exact log. This is not image accuracy or user-study sample count. Source-package extracted smoke is separate and pending at deck authoring; no fresh-machine install claim. Modelweights and researchraw are separate dependencies. Future actual human trial should preserve failures/assistance and all-task time; no0humanengineeringopinion becomes humanfeedback. No field automatic release, material/SKU authentication,commercialROI or award guarantee.',['contributions','contributions08','rules','guide','tests','reference','recovery','live']);
}
assert.equal(p.slides.items.length,8);
const candidate=path.join(BUILD,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
const owners=[3,6,7];
await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath:OUT,pythonExecutable:PYTHON,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...owners.flatMap(n=>['--require-native-table-slide',String(n)])],explicitTotalSlideCount:8,requiredNativeTableOwnerSlides:owners,requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
const final=await PresentationFile.importPptx(await FileBlob.load(OUT));
const renderDir=path.join(BUILD,'rendered-final');await fs.mkdir(renderDir,{recursive:true});
for(let i=0;i<8;i++){
 const item=final.slides.getItem(i), png=await final.export({slide:item,format:'png',scale:1.5});
 await fs.writeFile(path.join(renderDir,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
 const layout=await item.export({format:'layout'});await fs.writeFile(path.join(BUILD,`slide-${i+1}.layout.json`),await layout.text());
}
await fs.writeFile(path.join(BUILD,'source-index.json'),JSON.stringify({schema:'kitguard.v08.slides-preview.build.v1',version:VERSION,preview:true,created_at:new Date().toISOString(),authoring_source:{path:path.relative(ROOT,fileURLToPath(import.meta.url)),sha256:await sha(fileURLToPath(import.meta.url))},sourceRecord,images,output:path.relative(ROOT,OUT),output_sha256:await sha(OUT),slides:8,native_table_slides:owners,render_path:path.relative(ROOT,renderDir),visual_qa:'pending'},null,2)+'\n');
console.log(JSON.stringify({status:'finalized_rendered_needs_visual_QA',slides:8,output:OUT,build_dir:BUILD,render_dir:renderDir,sha256:await sha(OUT)},null,2));
