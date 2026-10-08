'use strict';
/** Real Chrome + real isolated HTTP server. Images are synthetic engineering fixtures, not model evaluations. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.KITGUARD_PLAYWRIGHT_MODULE || path.join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'test-results/ui');
const base = process.env.KITGUARD_UI_BASE_URL || 'http://127.0.0.1:8767';
const report = {purpose:'Engineering UI test only; synthetic image fixtures are NOT real parts, model outputs, or competition accuracy evidence.', base, startedAt:new Date().toISOString(), browser:'Installed Google Chrome, headless; Playwright bundled runtime', steps:[], screenshots:[], pageErrors:[], consoleErrors:[], requestFailures:[], httpErrors:[]};
const fixture = n => path.join(out, `SYNTHETIC_UI_FIXTURE_${n}.png`);
const action = (page, name) => page.locator(`[data-action="${name}"]`);
async function step(name, work) { await work(); report.steps.push({name,passed:true}); console.log('PASS '+name); }
function watch(page, contextName) {
  page.on('pageerror', error => report.pageErrors.push({context:contextName,error:String(error)}));
  page.on('console', message => { if(message.type()==='error') report.consoleErrors.push({context:contextName,text:message.text()}); });
  page.on('requestfailed', request => report.requestFailures.push({context:contextName,url:request.url(),error:request.failure()?.errorText}));
  page.on('response', response => {if(response.status()>=400) report.httpErrors.push({context:contextName,url:response.url(),status:response.status()});});
}
async function screenshot(page, name) {
  await page.evaluate(() => document.fonts.ready);
  const dimensions=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth}));
  assert.ok(dimensions.document<=dimensions.viewport, `${name}: horizontal page overflow ${JSON.stringify(dimensions)}`);
  const filename=name+'.png';
  await page.screenshot({path:path.join(out,filename),fullPage:await page.locator('dialog[open]').count()===0,animations:'disabled'});
  report.screenshots.push({file:filename,dimensions});
}
async function mutation(page, fragment, trigger, status) {
  const pending=page.waitForResponse(r=>r.url().includes(fragment)&&r.request().method()==='POST');
  await trigger(); const response=await pending; assert.equal(response.status(),status);
  return await response.json();
}
async function fillCounts(form, values) {for(const [part,value] of Object.entries(values)) await form.locator(`[name="${part}"]`).fill(String(value));}
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.KITGUARD_CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    const desktop=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1,acceptDownloads:true});
    const page=await desktop.newPage(); watch(page,'desktop');
    await page.goto(base,{waitUntil:'networkidle'});
    await page.locator('.welcome h1').waitFor();
    await step('Desktop mobile-menu control stays hidden',async()=>{assert.equal(await action(page,'toggle-sidebar').isVisible(),false);});
    await step('Desktop welcome and Chinese language switch',async()=>{await action(page,'language').filter({hasText:'中文'}).click(); await screenshot(page,'01-desktop-empty-zh');});
    await step('Reject zero total without creating an order',async()=>{
      await action(page,'new-order').first().click();
      const form=page.locator('#create-form'); await fillCounts(form,{bolt:0,nut:0,washer:0,bracket:0});
      await form.locator('button[type="submit"]').click();
      await form.locator('.modal-error').filter({hasText:'0–3'}).waitFor();
      assert.equal((await (await desktop.request.get(base+'/api/orders')).json()).orders.length,0);
    });
    let order;
    await step('Create real persisted order from desktop form',async()=>{
      const form=page.locator('#create-form'); await form.locator('[name="title"]').fill('UI 工程测试 · 非实物验证');
      await fillCounts(form,{bolt:2,nut:2,washer:2,bracket:1});
      const data=await mutation(page,'/api/orders',()=>form.locator('button[type="submit"]').click(),201); order=data.order;
      await page.locator('.workspace-heading h1').filter({hasText:order.title}).waitFor();
      assert.equal(order.revision,1); assert.equal(order.status,'pending');
      await screenshot(page,'02-desktop-order-empty');
    });
    await step('Structured edit increments revision and persists quantities',async()=>{
      await action(page,'revise').click(); const form=page.locator('#revision-form');
      await form.locator('[name="washer"]').fill('3'); await form.locator('[name="instruction"]').fill('工程 UI 测试：垫圈改为三件');
      const data=await mutation(page,'/revise',()=>form.locator('button[type="submit"]').click(),200); order=data.order;
      await page.locator('#revision-dialog').waitFor({state:'hidden'});
      assert.equal(order.revision,2); assert.equal(order.requirements.washer,3);
    });
    await step('Upload evidence through file chooser and display original dimensions',async()=>{
      const data=await mutation(page,'/photos',()=>page.locator('#photo-file').setInputFiles(fixture(1)),201); order=data.order;
      await page.locator('.photo-frame img').waitFor(); await page.locator('.photo-frame img').evaluate(img=>img.decode());
      assert.equal(data.photo.width,1000); assert.equal(data.photo.height,720);
      const iconBox=await page.locator('.canvas-label svg').boundingBox(); assert.ok(iconBox.width<=18&&iconBox.height<=18,'Evidence badge icon must remain compact');
      assert.equal(await action(page,'inspect').isDisabled(),true); // Model intentionally absent on isolated test server.
      const inspectBox=await action(page,'inspect').boundingBox(); assert.ok(inspectBox.y+inspectBox.height<=900,'Inspect action must fit initial desktop viewport');
      await screenshot(page,'03-desktop-evidence');
    });
    await step('Register a reference through real browser file picker',async()=>{
      await action(page,'references').click();
      const choose=page.waitForEvent('filechooser'); await page.locator('[data-action="upload-reference"][data-part="bolt"]').click();
      const chooser=await choose;
      const data=await mutation(page,'/references/bolt',()=>chooser.setFiles(fixture(1)),201); order=data.order;
      await page.locator('#references-dialog .reference-image img').waitFor();
      assert.ok(order.references.bolt);
      await screenshot(page,'04-desktop-reference-dialog');
      await page.locator('#references-dialog .modal-footer [data-action="close-modal"]').click();
    });
    await step('Second photo, old photo selection, return to latest',async()=>{
      const data=await mutation(page,'/photos',()=>page.locator('#photo-file').setInputFiles(fixture(2)),201); order=data.order;
      await page.locator('.thumbnail').nth(1).waitFor();
      await page.locator('.thumbnail').nth(1).click();
      await page.locator('.action-panel h3').filter({hasText:'正在查看历史证据'}).waitFor();
      assert.equal(await action(page,'inspect').isDisabled(),true);
      await action(page,'show-latest').click();
      await page.locator('.action-panel h3').filter({hasText:'现在可以核验新证据'}).waitFor();
    });
    await step('Revision after evidence marks old evidence historical',async()=>{
      await action(page,'revise').click(); const form=page.locator('#revision-form');
      await form.locator('[name="bolt"]').fill('1');
      const data=await mutation(page,'/revise',()=>form.locator('button[type="submit"]').click(),200); order=data.order;
      await page.locator('#revision-dialog').waitFor({state:'hidden'});
      assert.equal(order.revision,3); assert.equal(await action(page,'inspect').isDisabled(),true);
      await page.locator('.evidence-footer').filter({hasText:'历史照片'}).waitFor();
      await mutation(page,'/photos',()=>page.locator('#photo-file').setInputFiles(fixture(1)),201);
    });
    await step('Unavailable model proposal shows error and cannot apply',async()=>{
      await action(page,'revise').click(); await page.locator('[data-mode="natural"]').click();
      await page.locator('#revision-form [name="instruction"]').fill('将垫圈改为两件。工程测试。');
      await mutation(page,'/propose-revision',()=>action(page,'propose').click(),503);
      await page.locator('#revision-form .modal-error').filter({hasText:'本地模型暂不可用'}).waitFor();
      assert.equal(await page.locator('#revision-submit').isDisabled(),true);
      await page.locator('#revision-dialog .modal-footer [data-action="close-modal"]').click();
      await action(page,'refresh-workspace').click();
      await page.locator('.error-banner').waitFor({state:'hidden'});
    });
    await step('Export downloads parseable real audit record',async()=>{
      const pending=page.waitForEvent('download'); await page.locator('.heading-buttons a[download]').click();
      const download=await pending; const output=path.join(out,'SYNTHETIC_UI_AUDIT.json'); await download.saveAs(output);
      const exported=JSON.parse(fs.readFileSync(output,'utf8')); assert.ok(JSON.stringify(exported).includes(order.id));
      assert.ok(JSON.stringify(exported).includes('UI 工程测试'));
    });
    const historyInspectBox=await action(page,'inspect').boundingBox(); assert.ok(historyInspectBox.y+historyInspectBox.height<=900,'Inspect action must remain visible with photo history');
    await screenshot(page,'05-desktop-current-workspace');
    const mobile=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true});
    const phone=await mobile.newPage(); watch(phone,'mobile'); await phone.goto(base,{waitUntil:'networkidle'});
    await phone.locator('.workspace-heading h1').waitFor();
    await step('Mobile Korean workspace fits without horizontal overflow',async()=>{await screenshot(phone,'06-mobile-ko-workspace');});
    await step('Mobile navigation opens and new-order modal fits',async()=>{
      assert.equal(await phone.locator('.mobile-menu svg').isVisible(),true);
      await action(phone,'toggle-sidebar').click(); await phone.locator('.sidebar.open').waitFor();
      await phone.locator('.sidebar-add').click();
      const form=phone.locator('#create-form'); await form.waitFor(); await screenshot(phone,'07-mobile-create-dialog');
      await form.locator('[name="title"]').fill('UI fixture <b>text only</b>');
      await fillCounts(form,{bolt:1,nut:0,washer:1,bracket:0});
      await mutation(phone,'/api/orders',()=>form.locator('button[type="submit"]').click(),201);
      await phone.locator('#order-dialog').waitFor({state:'hidden'});
      assert.equal(await phone.locator('.workspace-heading h1').innerText(),'UI fixture <b>text only</b>');
      assert.equal(await phone.locator('.workspace-heading h1 b').count(),0);
      // Close drawer if it remains open after mobile creation.
      if(await phone.locator('.sidebar.open').count()) await action(phone,'close-sidebar').click();
    });
    await step('Mobile photo upload and Chinese toggle remain usable',async()=>{
      await mutation(phone,'/photos',()=>phone.locator('#photo-file').setInputFiles(fixture(2)),201);
      await phone.locator('.photo-frame img').waitFor(); await phone.locator('.photo-frame img').evaluate(img=>img.decode());
      await action(phone,'language').filter({hasText:'中文'}).click();
      const evidenceBox=await phone.locator('.evidence-panel').boundingBox(); const checkBox=await phone.locator('.check-column').boundingBox(); const historyBox=await phone.locator('.history-panel').boundingBox();
      assert.ok(evidenceBox.y<checkBox.y&&checkBox.y<historyBox.y,'Mobile must place evidence, checks/actions, then history');
      await screenshot(phone,'08-mobile-zh-evidence');
    });
    await step('No browser JavaScript errors or failed network requests',async()=>{
      assert.deepEqual(report.pageErrors,[]); assert.deepEqual(report.requestFailures,[]);
      assert.ok(report.httpErrors.every(item=>item.status===503&&item.url.endsWith('/propose-revision')));
      assert.ok(report.consoleErrors.every(item=>item.text.includes('503')));
    });
    report.success=true;
  } catch(error) {report.success=false; report.error=String(error.stack||error); console.error(report.error); process.exitCode=1;}
  finally {report.finishedAt=new Date().toISOString();fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
})();
