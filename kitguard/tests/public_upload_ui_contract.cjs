'use strict';
// CPU-only function contracts; no browser, HTTP, model, or UI visual-quality claim.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const listeners = new Map();
const calls = { picker: 0, uploads: 0, camera: [], notices: [] };
const context = vm.createContext({
  document: {
    addEventListener(type, fn) { listeners.set(type, [...(listeners.get(type) || []), fn]); },
    getElementById() { return { addEventListener() {}, click() { calls.picker++; } }; },
    querySelectorAll() { return []; },
  },
  window: { addEventListener() {} },
  localStorage: { getItem() { return null; } },
  KitGuardRegion: { text() { return 'region'; }, summary() { return ''; }, isRegion() { return false; } },
  spatialPhotoCheck() { return null; }, spatialOverlayMarkup() { return ''; }, spatialControlsMarkup() { return ''; },
  finalizedOrder(order) { return ['completed', 'manual_reviewed'].includes(order?.status); },
  openCamera(part) { calls.camera.push(part); },
  FormData: class { append() {} },
  calls,
});
for (const filename of ['app.js', 'public-review.js']) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../kitguard/static', filename), 'utf8'), context);
}
vm.runInContext(`
  toast = message => calls.notices.push(message);
  mutate = async () => { calls.uploads++; };
  globalThis.ui = { state, renderEvidence, pickPhoto, uploadPhoto };
`, context);
const ui = context.ui;
const photo = { id: 'fixture-photo', revision: 1, url: '/fixture.jpg', width: 64, height: 64 };
const order = { id: 'fixture', title: 'Synthetic contract', revision: 1, status: 'pending', photos: [photo],
  demo_source: { sample_id: 'synthetic' } };
const file = { type: 'image/png', size: 1 };
async function clickCamera(part) {
  const button = { disabled: false, dataset: { action: 'camera', ...(part ? { part } : {}) } };
  for (const listener of listeners.get('click')) await listener({ target: { closest() { return button; } } });
}
(async () => {
  ui.state.order = order;
  for (const lang of ['ko', 'zh']) {
    ui.state.lang = lang;
    const html = ui.renderEvidence(order);
    assert.doesNotMatch(html, /data-action="(?:camera|upload-photo)"/);
    assert.match(html, /data-action="inspection-region"/);
    assert.match(html, lang === 'ko' ? /출처 사진이 고정/ : /固定使用来源照片/);
  }
  ui.pickPhoto(); await ui.uploadPhoto(file); await clickCamera();
  assert.equal(calls.picker, 0); assert.equal(calls.uploads, 0); assert.equal(calls.camera.length, 0);
  // Drop handling still cancels native navigation but never uploads a public root.
  const zone = { classList: { remove() {} } };
  for (const listener of listeners.get('drop')) {
    await listener({ target: { closest() { return zone; } }, preventDefault() {}, dataTransfer: { files: [file] } });
  }
  assert.equal(calls.uploads, 0);
  assert.equal(calls.notices.length, 2);
  await clickCamera('bolt'); assert.equal(calls.camera.at(-1), 'bolt');
  const ordinary = { ...order }; delete ordinary.demo_source; ui.state.order = ordinary;
  assert.match(ui.renderEvidence(ordinary), /data-action="upload-photo"/);
  ui.pickPhoto(); await ui.uploadPhoto(file); await clickCamera();
  assert.equal(calls.picker, 1); assert.equal(calls.uploads, 1); assert.equal(calls.camera.at(-1), null);
  console.log('Public root upload UI contracts passed (synthetic, CPU only).');
})().catch(error => { console.error(error); process.exitCode = 1; });
