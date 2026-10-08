#!/usr/bin/env node
// Update the established KitGuard visual design with the v0.9 evidence.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const RUNTIME='/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const SKILL='/Users/lkc/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations';
const OUT=path.join(ROOT,'output/competition-v0.9/KitGuard_presentation_9slides.pptx');
const BUILD=path.join(ROOT,'tmp/v09-slides');
const FONT='Apple SD Gothic Neo';
const facts=JSON.parse(await fs.readFile(path.join(ROOT,'output/competition-v0.9/facts.json'),'utf8'));
assert.equal(facts.tests_passed,1826);assert.deepEqual(facts.resolution_outcomes,['mismatch','matched']);
for(const s of Object.values(facts.sources))assert.equal(crypto.createHash('sha256').update(await fs.readFile(path.join(ROOT,s.path))).digest('hex'),s.sha256);
await fs.mkdir(BUILD,{recursive:true});
const rr=createRequire(path.join(RUNTIME,'node/package.json'));
process.env.RUNTIME_NODE_MODULES=path.join(RUNTIME,'node/node_modules');
const {Presentation,PresentationFile,FileBlob}=await import(pathToFileURL(rr.resolve('@oai/artifact-tool')).href);
const {finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={ink:'#123D35',green:'#17725C',muted:'#566B64',paper:'#F8F8F2',rule:'#D4DDD4',amber:'#996227',white:'#FFFFFF'};
function text(s,t,x,y,w,h,size=28,color=C.ink,bold=false){const b=s.shapes.add({geometry:'textbox',name:t.slice(0,64),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});b.text=t;b.text.style={typeface:FONT,fontSize:size,color,bold,autoFit:'none',wrap:true};return b;}
function slide(n,title){const s=p.slides.add();s.background.fill=C.paper;text(s,title,64,48,1152,75,43,C.ink,true);text(s,'KitGuard 0.9.0.dev1   해피   2026.10.03',64,681,1090,24,17,C.muted);text(s,String(n).padStart(2,'0'),1166,677,50,28,21,C.muted);return s;}
function note(s,t,keys=[]){s.speakerNotes.textFrame.setText(t+'\n\nSources\n'+keys.map(k=>`${facts.sources[k].path} SHA256 ${facts.sources[k].sha256}`).join('\n'));}
function table(s,values,x,y,w,h,widths,size=27){const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});t.borders.assign({style:'solid',fill:C.rule,width:1});for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){const cell=t.getCell(r,c);cell.fill=r===0?C.ink:C.white;cell.text.style={typeface:FONT,fontSize:size,bold:r===0,color:r===0?C.white:C.ink,autoFit:'none'};}return t;}
const photoSources=[];
async function shot(s,name,x,y,w,h){const fp=path.join(ROOT,'test-results/v0.9/browser',name),bytes=await fs.readFile(fp);photoSources.push({path:path.relative(ROOT,fp),sha256:crypto.createHash('sha256').update(bytes).digest('hex')});s.images.add({blob:new Uint8Array(bytes),contentType:'image/jpeg',fit:'contain',position:{left:x,top:y,width:w,height:h},alt:'Actual local browser engineering rehearsal, 0 human participants. '+name});}
const imageNote='Actual unretouched browser screenshot, fitted in full. MVTec LOCO AD screw_bag/train/good/016.png, previously exposed development image. https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad . CC BY-NC-SA 4.0 https://creativecommons.org/licenses/by-nc-sa/4.0/ . ENGINEERING-AGENT automation, 0 human participants, no physical completion. Review points are operator assertions, not authenticated image truth.';
{
 const s=p.slides.add();s.background.fill=C.paper;
 text(s,'KitGuard',64,90,1145,110,86,C.ink,true);
 text(s,'사진·BOM 디지털 검토 Agent',68,227,1130,58,40,C.green,true);
 text(s,'AI 관찰부터\n근거가 남는 검토 결론까지',64,365,1120,150,49,C.ink,true);
 text(s,'기존 Mac에서 실행하는 디지털 업무 MVP',68,584,1110,49,29,C.muted);
 text(s,'해피   일반부   2026.10.03   0.9.0.dev1',68,678,1130,28,19,C.muted);
 note(s,'자가평가 Level3 MVP. 사진의 수량과 현재 주문을 비교하고 검토자의 위치 근거와 결론을 보존합니다. 새 실물 구입이나 외부 GPU 없이 현존 M5 Pro64GB에서 구현했습니다. 사업·현장 효과는 아직 검증하지 않았습니다. 발표6분 구성, 시연영상은 보조 자료입니다.',['A','F','G']);
}
{
 const s=slide(2,'사진과 주문을 함께 검토하는 작업');
 text(s,'대상 업무 가설',64,166,300,42,30,C.green,true);
 text(s,'교육 키트 운영\n소규모 조립 자료 검토',64,227,300,100,29);
 text(s,'사진은 같은데\n주문 수량은 바뀝니다',64,388,300,102,30,C.ink,true);
 text(s,'현재 버전과 근거를\n한 작업에 연결합니다',64,540,300,92,27,C.muted);
 await shot(s,'08-final-workspace.jpg',388,168,828,466);
 text(s,'실제 R2 작업 화면 / 공개 개발 사진',388,641,828,28,20,C.muted);
 note(s,'사진과 BOM이 메시지로 따로 전달될 때 생길 수 있는 재검토 문제를 다룹니다. 사용자·구매 수요는 가설입니다. 내 사진 자료 주문에는 로컬 이미지와 출처 진술을 등록할 수 있고 출처는 미인증 상태로 유지합니다. '+imageNote,['A','B']);
}
{
 const s=slide(3,'R1의 차이를 발견한 실제 로컬 실행');
 text(s,'주문 3 / 2 / 2 / 0',64,167,300,47,29,C.ink,true);
 text(s,'관찰 2 / 2 / 2 / 0',64,231,300,47,29,C.green,true);
 text(s,'나사류 1개 차이',64,330,300,52,32,C.ink,true);
 text(s,'55.052초',64,418,300,64,43,C.green,true);
 text(s,'저장된 관찰 시간\n사용자 전체 시간과 구분',64,503,300,97,26,C.muted);
 await shot(s,'01-real-r1.jpg',389,167,827,466);
 text(s,'수량 순서: 나사류 / 너트 / 와셔 / 브래킷',389,642,827,28,20,C.muted);
 note(s,'R1 check '+facts.checks[0].id+' backendmlx, latency55052ms. Model observes same public source2/2/2/0, currentBOM3/2/2/0. correct is an internal decision name meaning correction/difference, not a claim of complete model accuracy. This already exposed source adds no evaluation image. '+imageNote,['A','B']);
}
{
 const s=slide(4,'Agent 구조와 도구의 역할');
 table(s,[['단계','실제 구현'],['관찰','원방향·90° 회전 공간 목록, 조건부 국소 확인'],['판단·실행','프로그램 계수와 BOM 대조, 차이·불확실성 안내'],['Feedback','위치 복검을 독립 결론으로 저장, AI 원결과 유지'],['Memory / State','버전·사진·검사·실행 identity·의견 집합 결합'],['도구 결과','개정 후 새 검사, JSON·HTML·사진·SHA 내보내기']],64,166,1152,356,[271,881],27);
 text(s,'Qwen3.6-27B 4-bit / MLX / M5 Pro 64GB',64,551,1152,48,31,C.green,true);
 text(s,'BOM 정답은 모델에 미입력. 도구와 상태 전이는 고정 정책으로 제어합니다.',64,619,1152,40,24,C.muted);
 note(s,'The same local VLM performs correlated observations; it is not an independent ensemble. FastAPI/SQLite persist jobs, revisions and evidence. This is a bounded fixed-policy workflow agent, not a free autonomous planner. The operator explicitly approves requirements changes. The default observation core is unchanged.',['A','G']);
}
{
 const s=slide(5,'사진 위에 남기는 복검 근거');
 await shot(s,'04-r2-marked.jpg',64,158,902,508);
 text(s,'6개 위치',994,191,230,50,32,C.green,true);
 text(s,'표시를 계수해\n주문과 비교',994,268,220,102,27);
 text(s,'AI 원관찰\n그대로 보존',994,416,220,98,27);
 text(s,'추가 자료 요청도\n별도 결론으로',994,562,220,83,23,C.muted);
 note(s,'Each point records one class and normalized0-1000coordinates. The server derives count and difference, requires scope and digital-only acknowledgement, binds frozen state, and preserves independent originalAI. Users can choose needs_more_evidence without confirmedcounts. Picture shows ENGINEERING-AGENT purposeengineering_rehearsal, not humanvalidation. '+imageNote,['A','B','G']);
}
{
 const s=slide(6,'개정 후 재검사와 내려받는 증거');
 text(s,'R1 필요 3개 → R2 필요 2개',64,168,620,46,31,C.ink,true);
 text(s,'명시적 요구 변경\n이전 검사·결론은 과거 이력으로',64,239,617,110,31);
 text(s,'같은 사진을 다시 추론',64,389,616,43,31,C.green,true);
 text(s,'49.773초 / 관찰 2·2·2·0\n새 복검도 수량 일치',64,452,616,104,29);
 text(s,'부품 보충 없이 주문만 변경한 시나리오',64,615,616,35,23,C.amber);
 await shot(s,'07-offline-points.jpg',705,160,511,443);
 text(s,'증거 HTML의 실제 위치 표시',705,618,511,33,23,C.muted);
 note(s,'The preset explicit BOMchange is requirement revision, not AI lowering a target or physical repair. R1resolution becomes expired; R2requires fresh inference. Repeatedsamebytes do not count as a newphysicalphoto. CheckR2latency49773ms. Actual browser ZIPdownload was SHAverified, extractedHTML was served on127.0.0.1and visuallyinspected. No file://browserpolicy bypass or file://visualtest claim. A new publicopinion also expires currentresolution; tested by syntheticcontract. '+imageNote,['A','B','G']);
}
{
 const s=slide(7,'검증 결과와 적용 범위');
 table(s,[['분리된 모델 자료','정확 / 오류 / 보류'],['기존 공개 51장','41 / 3 / 7'],['LOCO 조합 24장','23 / 0 / 1']],64,172,1152,220,[711,441],31);
 text(s,'1,826개 소프트웨어 회귀 통과',64,439,1152,53,37,C.green,true);
 text(s,'24장은 총 6개 조합을 바꾼 같은 도메인의 제한된 검증\n기존 세 오류 유지 / 두 분모는 합치지 않음',64,520,1152,91,28);
 text(s,'실제 참여자 0명 / 사용자 전체 시간과 현장 효익은 미측정',64,632,1152,34,24,C.amber);
 note(s,'Ccorrectusable, Wwrongdefinite,Uuncertain,Eerror,Nunattempted. BothdatasetsE0N0. LOCO24truthderivedfromauthorcompositionlabels, fixedtotal6bolt2bracket0, not nativenative4classcounts. Mainanyfalseready0/24over255legalBOMs; alwaysabstainalso0/24. Twelve count4photos cannotcreateexactmatchedBOMmax3; remaining12correctready11. Do not poolorclaimindustrialgeneralization. Candidatefailedcrosssourceapproachesremainrejected.1,826engineeringtests,44.69s,2existingwarnings. Initialrunmissingrequiredtestenvcaused5setuperrors;correctisolationrerunallpassed.',['A','C','D','E']);
}
{
 const s=slide(8,'도입 가설과 수익 방식');
 text(s,'첫 적용 범위',64,174,532,43,31,C.green,true);
 text(s,'한 담당자의 사진·BOM 검토\n로컬 단일 사용자 설치',64,245,532,110,32);
 text(s,'조직별 설치·양식 설정\n유지보수 계약',64,435,532,110,32,C.ink,true);
 text(s,'가격·구매 의향·고객 실적 미확정',64,613,532,40,24,C.muted);
 text(s,'실제 업무에서 확인할 값',712,174,504,43,31,C.green,true);
 text(s,'기존 방식 대비 전체 소요시간\n놓친 차이와 잘못된 일치\n완료율과 도움 요청',712,246,504,179,29);
 text(s,'고객이 권리를 확보한 사진으로 검증\n연구 자료의 비상업 조건 유지',712,506,504,111,26,C.muted);
 note(s,'Allmarketandbusinessitemsarehypotheses, notcustomerinterviewsorvalidatedfinancialforecasts. Propose localinstallation/workflowconfiguration/maintenance, priceaftervalidation. Theoretical benefit is evidence continuity and review traceability; no time-savingpercent or ROI. CurrentpublicresearchphotosCCBYNCSA do not confer commercialdatasetrights. No externalGPUorhardwarepurchaseisneededforcurrentdemo, compatiblehardwareisneededforfuturedeployment.',['F','G']);
}
{
 const s=slide(9,'개발 기여와 현재 완성도');
 text(s,'기존 자산',64,171,548,44,31,C.ink,true);
 text(s,'9월26일부터 개발한\n사진 관찰·주문·증거 엔진',64,233,548,108,30);
 text(s,'대회 기간 추가',64,393,548,44,31,C.green,true);
 text(s,'비동기 복구·자료 주문·개정 재검사\n10월3일 위치 복검·결론 만료·증거',64,455,548,114,28);
 text(s,'Codex 코드·검사·자료 제작 보조 공개',64,622,548,34,23,C.muted);
 text(s,'자가평가 Level 3 MVP',714,171,502,51,35,C.green,true);
 text(s,'입력부터 검토 결론까지 실제 실행\n기존 장비와 공개 사진으로 재현',714,256,502,115,29);
 text(s,'다음 단계',714,438,502,43,31,C.ink,true);
 text(s,'담당자의 독립 작업 검증\n혼동 범주 자료 확보와 개선',714,507,502,103,29);
 note(s,'Official development9/29-10/6. Actualstart9/26disclosed;noassertionallworkduringperiod. PreviouslybuiltassetsmaybereusedwithdisclosureunderOct2clarificationandindividualassetlicenses. NewOct3workbindspointreviewwithrevisioncheckidentityandopinionchanges,notnewbasemodeltraining. Level3selfassessmentmatchesatleastoneendtoendworkflow;notLevel4Pilot,effectunmeasured. Noawardsorfieldreliabilityguarantee. Report5pages,tech1page,deck9,video<3min,sourceZIPprepared but notsubmitted. Official https://contest.gnict.org/bbs/board.php?bo_table=notice&wr_id=5 .',['F','G']);
}
assert.equal(p.slides.items.length,9);
const candidate=path.join(BUILD,'candidate.pptx');
await(await PresentationFile.exportPptx(p)).save(candidate);
await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath:OUT,pythonExecutable:path.join(RUNTIME,'python/bin/python3'),integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','4','--require-native-table-slide','7'],explicitTotalSlideCount:9,requiredNativeTableOwnerSlides:[4,7],requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
const final=await PresentationFile.importPptx(await FileBlob.load(OUT));
await fs.mkdir(path.join(BUILD,'rendered-final'),{recursive:true});
for(let i=0;i<9;i++){const png=await final.export({slide:final.slides.getItem(i),format:'png',scale:1.5});await fs.writeFile(path.join(BUILD,'rendered-final',`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));}
await fs.writeFile(path.join(ROOT,'output/competition-v0.9/slide-build.json'),JSON.stringify({slides:9,version:'0.9.0.dev1',font:FONT,photoSources,visual_qa:'pending',sha256:crypto.createHash('sha256').update(await fs.readFile(OUT)).digest('hex')},null,2)+'\n');
console.log(JSON.stringify({output:OUT,slides:9}));
