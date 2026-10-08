'use strict';
/** Records real HTTP/model responses. Public-photo walkthrough, never physical completion. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(path.join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const root = path.resolve(__dirname, '..');
const base = process.env.KITGUARD_DEMO_URL || 'http://127.0.0.1:8766';
const out = path.join(root, 'output/demo');
const photo = path.join(root, 'datasets/raw/mvtec_loco_ad/screw_bag/train/good/016.png');
const report = {startedAt:new Date().toISOString(), kind:'Actual local model and browser walkthrough', source:'MVTec LOCO AD screw_bag/train/good/016.png, CC BY-NC-SA 4.0', selection:'Development image chosen for demonstration before 27B results; excluded from holdout; demo reuse does not add an evaluation sample', physicalActionVerified:false, humanCompletionPerformed:false, samePhotoResubmittedAfterOrderRevision:true, responses:[], errors:[]};
fs.mkdirSync(out, {recursive:true});
const action = (page, name) => page.locator(`[data-action="${name}"]`);
const pause = ms => new Promise(resolve=>setTimeout(resolve,ms));
async function mutation(page, fragment, work) {
  const pending=page.waitForResponse(r=>r.url().includes(fragment)&&r.request().method()==='POST', {timeout:300000});
  await work(); const response=await pending; const body=await response.json();
  report.responses.push({url:response.url(),status:response.status(),body});
  assert.ok(response.ok(),JSON.stringify(body)); return body;
}
async function caption(page, title, detail) {
  await page.evaluate(({title,detail})=>{
    let element=document.querySelector('#demo-caption');
    if(!element){element=document.createElement('div');element.id='demo-caption';document.body.append(element);}
    element.style.cssText='position:fixed;bottom:12px;left:50%;transform:translateX(-50%);z-index:9999;width:min(1080px,94vw);padding:12px 22px;border-radius:12px;background:#173a32;color:#fff;box-shadow:0 6px 30px #0004;pointer-events:none;font:16px/1.45 Arial,sans-serif';
    element.replaceChildren();const strong=document.createElement('strong');strong.textContent=title;const line=document.createElement('div');line.style.cssText='font-size:13px;color:#d6e9e2';line.textContent=detail;element.append(strong,line);
  },{title,detail});
}
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  let context,page;
  try{
    context=await browser.newContext({viewport:{width:1440,height:900},recordVideo:{dir:out,size:{width:1280,height:800}},acceptDownloads:true});
    page=await context.newPage();page.on('pageerror',e=>report.errors.push(String(e)));
    await page.goto(base,{waitUntil:'networkidle'});
    const existing=await (await context.request.get(base+'/api/orders')).json();
    assert.equal(existing.orders.length,0,'Use a fresh isolated demo store');
    await caption(page,'KitGuard · 공개 실사 데이터로 실행한 로컬 AI 시연','화면·응답은 실제 실행입니다. 공개 정지 사진이므로 실물 조치나 현장 성능을 입증하지 않습니다.');await pause(4500);
    await action(page,'new-order').first().click();const form=page.locator('#create-form');
    await form.locator('[name="title"]').fill('공개 사진 데모 · 실물 검증 아님');
    for(const [part,count] of Object.entries({bolt:3,nut:2,washer:2,bracket:0})) await form.locator(`[name="${part}"]`).fill(String(count));
    await caption(page,'01 · 버전이 있는 작업지시','필요 수량은 코드로 관리합니다. 관찰 모델에는 목표 수량을 보내지 않습니다.');await pause(2500);
    await mutation(page,'/api/orders',()=>form.locator('button[type="submit"]').click());
    await mutation(page,'/photos',()=>page.locator('#photo-file').setInputFiles(photo));await pause(1500);
    await caption(page,'02 · 실제 로컬 모델 추론','공개 원본 → 앱의 업로드 처리 → 로컬 모델 → 코드 수량 대조. 결과를 미리 넣지 않았습니다.');
    const firstInspection=await mutation(page,'/inspect',()=>action(page,'inspect').click());
    assert.equal(firstInspection.check.backend,'mlx');assert.equal(firstInspection.check.decision,'correct');await pause(4500);
    await page.locator('.evidence-panel [data-action="spatial-toggle"]').click();await pause(2000);
    await page.screenshot({path:path.join(out,'01-real-inspection.png'),fullPage:true});
    await action(page,'revise').click();await page.locator('[data-mode="natural"]').click();
    await page.locator('#revision-form [name="instruction"]').fill('볼트를 2개로 변경하고 나머지는 유지해 주세요.');
    await caption(page,'03 · 자연어는 변경안만 생성','모델은 원문의 수량 표현을 추출하고, 코드가 계산·범위를 검사합니다. 승인 전에는 적용되지 않습니다.');
    await mutation(page,'/propose-revision',()=>action(page,'propose').click());await pause(4000);
    await mutation(page,'/revise',()=>page.locator('#revision-submit').click());await pause(1500);
    await caption(page,'04 · 변경되면 이전 검증은 무효','이 시연은 같은 공개 사진을 다시 제출합니다. 부품을 실제로 바꿨다는 뜻이 아닙니다.');
    await mutation(page,'/photos',()=>page.locator('#photo-file').setInputFiles(photo));
    const finalInspection=await mutation(page,'/inspect',()=>action(page,'inspect').click());
    assert.equal(finalInspection.check.backend,'mlx');assert.equal(finalInspection.check.decision,'ready');
    assert.equal(finalInspection.order.revision,2);assert.notEqual(finalInspection.order.status,'completed');
    assert.equal(finalInspection.order.checks.find(c=>c.id===firstInspection.check.id).valid,false);
    report.applicationAssertions={realMlxResponses:2,firstDecision:'correct',newRevisionDecision:'ready',oldCheckInvalid:true,completed:false};await pause(4000);
    await page.locator('.evidence-panel [data-action="spatial-toggle"]').click();await pause(2000);
    await page.screenshot({path:path.join(out,'02-current-version.png'),fullPage:true});
    const audit=page.locator(`.audit-record[data-check="${firstInspection.check.id}"]`);
    await audit.click();await page.locator('#audit-dialog[open]').waitFor();
    await page.locator('#audit-dialog [data-action="spatial-toggle"]').click();
    await caption(page,'05 · 사진·버전·모델·판단 근거를 연결','R1의 과거 검사는 무효이며 읽기 전용입니다. 사람이 실물을 확인하지 않았으므로 완료를 누르지 않습니다.');await pause(5000);
    await page.screenshot({path:path.join(out,'03-audit.png')});
    await page.locator('#audit-dialog [data-action="close-modal"]').last().click();
    const downloading=page.waitForEvent('download');await page.locator('a[href$="/evidence.zip"]').click();
    await (await downloading).saveAs(path.join(out,'PUBLIC_PHOTO_DEMO_evidence.zip'));
    await caption(page,'06 · 오프라인 증거 패키지','사진·JSON·열람 페이지·SHA-256을 함께 저장합니다. 공개 사진 성능은 별도 동결 평가 보고서에서 확인하세요.');await pause(5000);
    report.success=true;
  }catch(error){report.success=false;report.error=String(error.stack||error);process.exitCode=1;}
  finally{
    const video=page?.video();if(context)await context.close();
    if(video)await video.saveAs(path.join(out,'KitGuard_real_local_demo.webm'));
    await browser.close();report.finishedAt=new Date().toISOString();fs.writeFileSync(path.join(out,'recording.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify({success:report.success,error:report.error,output:out}));
  }
})();
