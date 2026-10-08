'use strict';
// Synthetic CPU contracts: no browser, network, model, or participant evidence.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const listeners = new Map(), elements = new Map();
const calls = { posts: [], picker: 0, camera: [], toasts: [], errors: [] };
const context = vm.createContext({
  document: {
    addEventListener(type, fn) { listeners.set(type, [...(listeners.get(type) || []), fn]); },
    getElementById(id) { if (!elements.has(id)) elements.set(id, { addEventListener() {}, click() { calls.picker++; }, close() {}, showModal() {}, innerHTML: '' }); return elements.get(id); },
    querySelectorAll() { return []; },
  },
  window: { addEventListener() {} }, localStorage: { getItem() { return null; } },
  URL, queueMicrotask() {}, setInterval() {}, clearInterval() {},
  crypto: { randomUUID() { return 'synthetic'; } },
  FormData: class { constructor() { this.entries = []; } append(key, value) { this.entries.push([key, value]); } },
  KitGuardRegion: { text() { return 'region'; }, summary() { return ''; }, isRegion() { return false; } },
  spatialPhotoCheck() { return null; }, spatialOverlayMarkup() { return ''; }, spatialControlsMarkup() { return ''; },
  openCamera(part) { calls.camera.push(part); }, calls,
});
for (const file of ['app.js', 'photo-documents.js', 'workflow.js', 'public-review.js', 'audit.js']) {
  vm.runInContext(fs.readFileSync(`kitguard/static/${file}`, 'utf8'), context);
}
vm.runInContext(`
  render = () => {}; refreshOrders = async () => {}; refreshCurrent = async () => {};
  toast = text => calls.toasts.push(text); modalError = (id, text) => calls.errors.push({id,text});
  setBusy = value => {state.busy=value;}; clearBusy = () => {state.busy=null;};
  post = async (path, body) => {calls.posts.push({path,body}); return globalThis.response;};
  globalThis.ui = {state, digitalOnlyOrder, renderEvidence, renderAction, renderSourceNotice, renderDocumentSource,
    renderPublicReview, publicReviewKey, pickPhoto, uploadPhoto, openManualReview, openComplete,
    photoDocumentSubmission, submitPhotoDocument, openPhotoDocument, auditDecision};
`, context);
const { ui } = context;
const photo = { id: 'synthetic-photo', revision: 1, width: 64, height: 64, sha256: 'a'.repeat(64) };
const source = { kind: 'user_declared_photo', verification: 'user_declared_unverified', physical_completion_allowed: false,
  source_note: '<script>UNTRUSTED</script>', source_url: 'javascript:alert(1)', license_note: 'USER CLAIM ONLY',
  original_root_photo_id: photo.id, source_sha256: 'b'.repeat(64), storage_sha256: photo.sha256,
  statement_sha256: 'c'.repeat(64), binding_sha256: 'd'.repeat(64) };
const order = { id: 'synthetic-document', title: 'SYNTHETIC DOCUMENT', revision: 1, evidence_epoch: 1,
  requirements: { bolt: 1, nut: 1, washer: 1, bracket: 1 }, status: 'ready', photos: [photo], events: [],
  document_source: source, latest_check: { id: 'synthetic-check', revision: 1, photo_id: photo.id, valid: true,
    decision: 'ready', backend: 'mlx', observed: { bolt: 1, nut: 1, washer: 1, bracket: 1 }, issues: [] } };
// The mlx label is just synthetic rendering input; no observer is imported or called.
const file = { type: 'image/png', size: 1, name: 'SYNTHETIC.png' };
const fields = Object.fromEntries(Object.entries(order.requirements).map(([key, value]) => [key, { value: String(value) }]));
Object.assign(fields, { title: { value: 'SYNTHETIC DOCUMENT' }, photo: { files: [file] }, source_note: { value: 'Created as a synthetic contract' },
  source_url: { value: '' }, license_note: { value: '' }, confirmed_digital_only: { checked: true } });
const form = { elements: { namedItem(name) { return fields[name]; } } };
(async () => {
  Object.assign(ui.state, { order, selectedPhoto: photo.id, health: { model: { available: true } }, orders: [order] });
  assert.equal(ui.digitalOnlyOrder(order), true);
  assert.equal(ui.digitalOnlyOrder({ demo_source: { sample_id: 'catalog' } }), true);
  assert.equal(ui.digitalOnlyOrder({ document_source: null }), true, 'Malformed metadata must fail closed like backend');
  assert.equal(ui.digitalOnlyOrder({}), false);
  for (const lang of ['ko', 'zh']) {
    ui.state.lang = lang;
    assert.doesNotMatch(ui.renderEvidence(order), /data-action="(?:camera|upload-photo)"/);
    assert.doesNotMatch(ui.renderAction(order), /data-action="(?:camera|manual-review|complete)"/);
    const markup = ui.renderSourceNotice(order);
    assert.match(markup, /data-source-verification="user_declared_unverified"/);
    assert.match(markup, lang === 'ko' ? /출처 미검증/ : /来源未核实/);
    assert.match(markup, /&lt;script&gt;UNTRUSTED&lt;\/script&gt;/);
    assert.doesNotMatch(markup, /<script>|href="javascript:/);
    assert.match(markup, /<details>/); assert.match(markup, /c{64}/);
    assert.doesNotMatch(ui.renderDocumentSource(order, true), /data-action=/);
    assert.match(ui.renderPublicReview(order), /public-review-panel/);
    assert.ok(ui.publicReviewKey(order));
    ui.openPhotoDocument(); assert.match(elements.get('photo-document-dialog').innerHTML, /name="source_note" required/);
  }
  const oldKey = ui.publicReviewKey(order); order.revision++; assert.notEqual(ui.publicReviewKey(order), oldKey); order.revision--;
  ui.pickPhoto(); await ui.uploadPhoto(file); ui.openManualReview(); ui.openComplete();
  assert.equal(calls.picker, 0); assert.equal(calls.posts.length, 0);
  const camera = { disabled: false, dataset: { action: 'camera' }, closest() { return null; } };
  for (const listener of listeners.get('click')) await listener({ target: { closest() { return camera; } } });
  assert.equal(calls.camera.length, 0);
  camera.dataset.part = 'nut';
  for (const listener of listeners.get('click')) await listener({ target: { closest() { return camera; } } });
  assert.deepEqual(calls.camera, ['nut']);
  const metadata = JSON.parse(JSON.stringify(ui.photoDocumentSubmission(form).metadata));
  assert.deepEqual(metadata, { title: 'SYNTHETIC DOCUMENT', requirements: order.requirements,
    source_note: 'Created as a synthetic contract', source_url: null, license_note: null, confirmed_digital_only: true });
  for (const bad of ['javascript:alert(1)', 'https://name:secret@example.invalid/a', 'https://example.invalid/ space']) {
    fields.source_url.value = bad; assert.throws(() => ui.photoDocumentSubmission(form));
  }
  fields.source_url.value = 'https://example.invalid/source'; fields.source_note.value = ' ';
  assert.throws(() => ui.photoDocumentSubmission(form)); fields.source_note.value = 'Synthetic local file';
  fields.confirmed_digital_only.checked = false; assert.throws(() => ui.photoDocumentSubmission(form));
  fields.confirmed_digital_only.checked = true;
  context.response = { order, photo }; await ui.submitPhotoDocument(form);
  assert.equal(calls.posts.length, 1); assert.equal(calls.posts[0].path, '/api/photo-documents');
  assert.deepEqual(calls.posts[0].body.entries.map(([key]) => key), ['photo', 'metadata']);
  assert.equal(ui.state.selectedPhoto, photo.id);
  assert.equal(JSON.parse(calls.posts[0].body.entries[1][1]).confirmed_digital_only, true);
  const ordinary = { ...order }; delete ordinary.document_source; ui.state.order = ordinary;
  assert.match(ui.renderEvidence(ordinary), /data-action="upload-photo"/);
  assert.equal(ui.renderSourceNotice(ordinary), '');
  assert.match(ui.renderAction(ordinary), /data-action="complete"/);
  console.log('Photo document UI: exact multipart metadata, unverified source, digital-only controls, scopes, escaping and legacy order passed (synthetic CPU).');
})().catch(error => { console.error(error); process.exitCode = 1; });
