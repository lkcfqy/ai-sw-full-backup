import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const RUNTIME='/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const SKILL='/Users/lkc/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations';
const OUT=path.join(ROOT,'output/competition-final-dev4/KitGuard_presentation_9slides.pptx');
const BUILD=path.join(ROOT,'tmp/scoring-slides');
const FONT='Apple SD Gothic Neo';
const facts=JSON.parse(await fs.readFile(path.join(ROOT,'output/competition-final-dev4/facts.json'),'utf8'));
assert.equal(facts.version,'0.9.0.dev4');assert.equal(facts.tests_passed,1877);assert.equal(facts.machine_tasks.workflow_outcomes_met,5);
for(const s of Object.values(facts.sources))assert.equal(crypto.createHash('sha256').update(await fs.readFile(path.join(ROOT,s.path))).digest('hex'),s.sha256);
await fs.mkdir(BUILD,{recursive:true});
const rr=createRequire(path.join(RUNTIME,'node/package.json'));
process.env.RUNTIME_NODE_MODULES=path.join(RUNTIME,'node/node_modules');
const {Presentation,PresentationFile,FileBlob}=await import(pathToFileURL(rr.resolve('@oai/artifact-tool')).href);
const {finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={ink:'#123D35',green:'#17725C',muted:'#566B64',paper:'#F8F8F2',rule:'#D4DDD4',white:'#FFFFFF'};
function text(s,t,x,y,w,h,size=28,color=C.ink,bold=false){const b=s.shapes.add({geometry:'textbox',name:t.slice(0,64),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});b.text=t;b.text.style={typeface:FONT,fontSize:size,color,bold,autoFit:'none',wrap:true};return b;}
function slide(n,title){const s=p.slides.add();s.background.fill=C.paper;text(s,title,64,48,1152,80,42,C.ink,true);text(s,'KitGuard 0.9.0.dev4   해피   2026.10.04',64,681,1090,24,17,C.muted);text(s,String(n).padStart(2,'0'),1166,677,50,28,21,C.muted);return s;}
function note(s,t,keys=[]){s.speakerNotes.textFrame.setText(t+'\n\nSources\n'+keys.map(k=>`${facts.sources[k].path} SHA256 ${facts.sources[k].sha256}`).join('\n'));}
function table(s,values,x,y,w,h,widths,size=25){const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});t.borders.assign({style:'solid',fill:C.rule,width:1});for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){const cell=t.getCell(r,c);cell.fill=r===0?C.ink:C.white;cell.text.style={typeface:FONT,fontSize:size,bold:r===0,color:r===0?C.white:C.ink,autoFit:'none'};}return t;}
const photoSources=[];
async function shot(s,relative,x,y,w,h){const fp=path.join(ROOT,relative),bytes=await fs.readFile(fp);photoSources.push({path:relative,sha256:crypto.createHash('sha256').update(bytes).digest('hex')});s.images.add({blob:new Uint8Array(bytes),contentType:'image/jpeg',fit:'contain',position:{left:x,top:y,width:w,height:h},alt:'Actual unretouched engineering browser screenshot, 0 human validation participants. '+relative});}
const rights='Actual unretouched browser screenshot, full aspect preserved. Public MVTec LOCO AD/Screws examples, https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad and https://www.mvtec.com/research-teaching/datasets/mvtec-screws . CC BY-NC-SA 4.0 https://creativecommons.org/licenses/by-nc-sa/4.0/ . Previously exposed development photos, engineering execution, 0 recruited human validation participants, no new image accuracy denominator or physical completion.';
{
 const s=p.slides.add();s.background.fill=C.paper;text(s,'KitGuard',64,88,1152,110,86,C.ink,true);text(s,'현재 사진과 BOM을 검토하는 로컬 Agent',68,235,1110,75,40,C.green,true);text(s,'입력부터 차이·불확실성 기록과\n디지털 증거까지 자동 실행',68,399,1120,120,44,C.ink,true);text(s,'기존 M5 Pro 64GB / 0.9.0.dev4 / 해피 / 일반부',68,630,1120,45,24,C.muted);note(s,'발표6분과 Q&A2분 준비. 현재 Level3 MVP; 실제 사용 효과·고객 수요·성능 우승을 주장하지 않는다. No physical purchases or external GPUs. Same frozen observation core.',['A','G']);
}
{
 const s=slide(2,'사진·BOM·버전이 분리되는 작업');text(s,'업무 가설',64,167,285,45,31,C.green,true);text(s,'교육 키트 운영\n소규모 조립 자료 검토',64,230,310,110,30);text(s,'현재 입력을 맡기면\n새 검증과 근거를 저장',64,405,306,120,30,C.ink,true);text(s,'수요·사람의 효익은\n아직 측정하지 않음',64,567,310,90,25,C.muted);
 await shot(s,'test-results/scoring-v1/recording/own-goal/0015.jpg',388,172,828,466);note(s,'사용자가 사진과 BOM을 등록하고 현재 주문 자율 목표를 시작하는 구조. 여기 실행은 자동 기계 리허설로 human validation0. Source note remains user-declared/unverified. four coarse classes, BOM per-class0-3, not SKU identity. '+rights,['A','B']);
}
{
 const s=slide(3,'Agent의 목표·계획·도구·기억');table(s,[['요소','실제 구현'],['Goal','현재 사진·BOM·버전·범위의 수량 자료 검토'],['Plan / Reasoning','입력 확인 → 새 관찰 → 저장된 결과별 분기'],['Tool','로컬 MLX·검사 작업·명시적 개정·증거 ZIP'],['Memory / Feedback','revision·photoSHA·check·epoch·모델 identity'],['실행 경계','현재 자료는 자동 개정 없음; 바뀌면 새 목표']],64,162,1152,360,[270,882],27);text(s,'관찰: Qwen3.6-27B 4-bit / MLX / spatial_guarded1536',64,558,1152,55,28,C.green,true);text(s,'BOM·저자 정답을 모델에 미입력 / 명시적 규칙 계획',64,620,1152,38,24,C.muted);note(s,'Bounded explicit rule planner, no hidden generated chain claimed. Rotated/local observations are correlated same-model checks, not independent reviewers. Worker persists tools and snapshots; cancel stops follow-on tools, inference gate remains until actual completion. Browser reload does not rerun.',['A','C']);
}
{
 const s=slide(4,'실제 관찰에서 다른 행동으로 분기');await shot(s,'test-results/scoring-v1/recording/all-cases/0030.jpg',64,153,1152,475);text(s,'차이 목록 / 추가 자료 요청 / 현재 버전에서 새 추론',64,638,1152,35,27,C.green,true);note(s,'Live real browser state during last inference: quantity difference, unknown small ring preserved, R1 revision finding historical while R2 is running. Whole mission137071ms, 4actualMLX checks15995/21566/48976/49972ms. Not an image-accuracy or human-benefit experiment. '+rights,['C']);
}
{
 const s=slide(5,'사전에 고정한 대표 기계 과제 5건');table(s,[['과제','실제 결과','새 목표 실행'],['수량 차이','차이 목록','20.213초'],['작은 부품 불확실','추가 자료 요청','21.739초'],['현재 BOM 일치','수량 일치 기록','48.628초'],['주문 변경','옛 목표409 → 새 차이','49.417초'],['실물 주문','디지털 범위409 거절','모델0회']],64,162,1152,350,[330,550,272],25);text(s,'5/5는 흐름 결과 / 실제 모델4회 / 공개 개발 사진3장',64,551,1152,49,28,C.green,true);text(s,'정답 정확도·사용자 시간 절감과 분리 / 새 이미지 분모0',64,618,1152,40,24,C.muted);note(s,'ProtocolSHA locked before first execution. Every planned task kept, including source-policy refusal. Server autonomous worker time includes binding verification/model waits, excludes photo registration, R2 revision/replay operations and human work. No recruited participants. Results do not estimate accuracy5/5 or generalization.',['B']);
}
{
 const s=slide(6,'같은 관찰에서 버전 결합을 제거한 대조');text(s,'R1 요구 2/2/2/0 · 관찰 2/2/2/0',64,164,1152,55,32,C.green,true);text(s,'사전에 정한 R2 요구 3/2/2/0으로 변경',64,234,1152,55,32,C.ink,true);table(s,[['동일 저장 관찰의 CPU 대조','R2에서 옛 ready'],['버전 결합을 생략한 최근 검사','계속 반환'],['KitGuard 현재 검사 guard','거절 → 새 실제 검증 후 차이 기록']],64,336,1152,183,[690,462],26);text(s,'기능 제거 대조: 결합 장치의 효과만 확인',64,558,1152,50,29,C.green,true);text(s,'독립 모델·경쟁 서비스 비교, 시장 우위 증명이 아님',64,624,1152,35,24,C.muted);note(s,'Ablation reuses the exact same real MLX observations, so no visual competitor denominator or artificial baseline inference timing. One predeclared changed-BOM task exposes stale reuse; not a statistical cross-market advantage. Source-binding and current check are checked without truth leakage into observation.',['B']);
}
{
 const s=slide(7,'인식 성과와 실패 경계');table(s,[['평가 분모','C / W / U / E / N','false-ready'],['기존 공개51장','41 / 3 / 7 / 0 / 0','3/51'],['LOCO 조합24장','23 / 0 / 1 / 0 / 0','0/24'],['이번 반복 과제·시연','새 이미지 분모0','새 정확도 없음']],64,165,1152,245,[435,455,262],25);text(s,'기존 모델 오류를 그대로 유지',64,461,1152,52,34,C.green,true);text(s,'작은 링·세부 규격·가림·브래킷 양성 검증 부족',64,534,1152,46,28);text(s,'실물 출고·산업 안전·인증된 정답으로 승격하지 않음',64,606,1152,42,24,C.muted);note(s,'C correct confirmed,W wrong confirmed,U uncertain,E error,N unattempted. LOCO24 same-domain derived combination criterion,total6,bracket positive0, unknown pretraining exposure. Do not pool51+24. Always-abstain also has0false-ready, so0/24 does not prove reliability. Prior reference/transfer failed candidates not promoted.',['E','F']);
}
{
 const s=slide(8,'로컬 도입 조건과 사업 가설');text(s,'수익 가설',64,165,500,49,32,C.green,true);text(s,'로컬 설치·업무 양식 설정·유지보수\n고객 가격·수요·수익은 미검증',64,233,540,137,29);text(s,'한 모델 worker / 대기열0\n과부하는 명확하게 거절',64,433,530,109,29,C.ink,true);text(s,'고객이 권리를 확보한 사진이 필요',64,609,548,42,23,C.muted);
 text(s,'실측 목표 20.213-49.417초',672,167,544,66,32,C.green,true);text(s,'추론 점유50% 가정\n시간당36-89건 계산 예시',672,264,540,140,31,C.ink,true);text(s,'사진 등록·복검·휴지시간 제외\n지속 처리 실측과 SLA는 미확인',672,437,540,110,27);text(s,'신규 실물·외부GPU0 / 운영비 미측정',672,608,544,42,23,C.muted);note(s,'Capacity scenarios from four single-goal server elapsed times. floor(3600000*0.5/max or min elapsed_ms) gives36-89 tasks/hour under stated assumptions; not measured sustained throughput, customer SLA, human time saving or profit. Hardware and electricity costs unknown, not zero. Research demo photosCCBYNCSA cannot be repurposed as commercial client data.',['I','G']);
}
{
 const s=slide(9,'완성도·개발 기여·남은 검증');text(s,'자가평가 Level3 MVP',64,168,1152,57,39,C.green,true);text(s,'현재 목표를 맡겨 실제 로컬 검증·분기·증거까지 실행',64,260,1152,58,32);text(s,'1,877 회귀 통과 / 실제 사용 효과는 별도 검증 필요',64,338,1152,58,30);text(s,'9/26 시작한 관찰·주문 엔진 재사용\n공식 기간9/29-10/6 중 자료·복검·복구·자율 실행 추가',64,442,1152,107,29);text(s,'Codex 코드·실험·자료 보조 공개 / 기반 VLM 신규학습 없음',64,579,1152,52,25,C.muted);note(s,'Official Annex3 Level3 requires stable E2E MVP; Level4 real-user repeated effects absent, do not claim. Official weights used for internal self-review; no panel points or first-place prediction. Five artifacts prepared same dev4, not submitted/received. Final deadline20261006 noonKST from officialnotice https://contest.gnict.org/bbs/board.php?bo_table=notice&wr_id=5 . Known limits and later validation needed are explicit.',['A','G','H']);
}
assert.equal(p.slides.items.length,9);
const candidate=path.join(BUILD,'candidate.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath:OUT,pythonExecutable:path.join(RUNTIME,'python/bin/python3'),integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','3','--require-native-table-slide','5','--require-native-table-slide','6','--require-native-table-slide','7'],explicitTotalSlideCount:9,requiredNativeTableOwnerSlides:[3,5,6,7],requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
const final=await PresentationFile.importPptx(await FileBlob.load(OUT));await fs.mkdir(path.join(BUILD,'rendered-final'),{recursive:true});for(let i=0;i<9;i++){const png=await final.export({slide:final.slides.getItem(i),format:'png',scale:1.5});await fs.writeFile(path.join(BUILD,'rendered-final',`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));}
await fs.writeFile(path.join(ROOT,'output/competition-final-dev4/slide-build.json'),JSON.stringify({slides:9,version:facts.version,font:FONT,photoSources,visual_qa:'pending',sha256:crypto.createHash('sha256').update(await fs.readFile(OUT)).digest('hex')},null,2)+'\n');console.log(JSON.stringify({output:OUT,slides:9}));
