'use strict';
// Synthetic server snapshots only: no browser, HTTP, image decode, or model call.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const clone = value => JSON.parse(JSON.stringify(value));
const photo = { id: 'synthetic-photo', sha256: 'a'.repeat(64), revision: 1, created_at: '2026-01-01T00:00:00Z' };
const check = { id: 'synthetic-check', revision: 1, evidence_epoch: 1, photo_id: photo.id, photo_sha256: photo.sha256,
  valid: true, decision: 'ready', backend: 'test', observed: { bolt: 1, nut: 1, washer: 1, bracket: 0 }, issues: [] };
const conclusions = ['disputed', 'needs_more_evidence', 'inconclusive', 'acknowledged'];
const reviews = conclusions.map((conclusion, index) => ({ current: true, receipt: {
  id: `synthetic-review-${index}`, revision: 1, conclusion, operator_code: '<script>synthetic</script>',
  note: '<img src=x onerror=alert(1)>', created_at: '2026-01-01T00:01:00Z', ai_decision: 'ready', user_validation: false,
} }));
const pending = { schema_version: 1, status: 'needs_clarification', current_count: 4, pending_count: 3,
  counts: { acknowledged: 1, disputed: 1, needs_more_evidence: 1, inconclusive: 1 },
  current_review_ids: reviews.map(item => item.receipt.id), pending_review_ids: reviews.slice(0, 3).map(item => item.receipt.id),
  check_id: check.id, binding_scope: 'live_runtime_metadata' };
const order = { id: 'synthetic-order', title: 'SYNTHETIC', revision: 1, evidence_epoch: 1, status: 'ready',
  requirements: { bolt: 1, nut: 1, washer: 1, bracket: 0 }, photos: [photo], latest_check: check,
  document_source: { kind: 'user_declared_photo' }, digital_review_feedback: pending, updated_at: '2026-01-01T00:01:00Z' };
function emptyFeedback(status = 'none') {
  return { ...clone(pending), status, current_count: 0, pending_count: 0,
    counts: { acknowledged: 0, disputed: 0, needs_more_evidence: 0, inconclusive: 0 },
    current_review_ids: [], pending_review_ids: [], check_id: status === 'not_applicable' ? null : check.id };
}
function fresh() {
  const listeners = new Map(), elements = new Map();
  const calls = { api: [], posts: [], focus: 0, scroll: 0 };
  const target = { focus() { calls.focus++; }, scrollIntoView() { calls.scroll++; } };
  const history = { open: false, querySelector() { return target; } };
  elements.set('public-review-history', history);
  const context = vm.createContext({
    document: {
      addEventListener(type, fn) { listeners.set(type, [...(listeners.get(type) || []), fn]); },
      getElementById(id) { if (!elements.has(id)) elements.set(id, { addEventListener() {}, innerHTML: '' }); return elements.get(id); },
      querySelectorAll() { return []; },
    }, window: { addEventListener() {} }, localStorage: { getItem() { return null; } },
    queueMicrotask() {}, setInterval() {}, clearInterval() {},
    KitGuardRegion: { isRegion() { return false; }, text() { return ''; } }, calls,
  });
  for (const file of ['app.js', 'workflow.js', 'public-review.js']) {
    vm.runInContext(fs.readFileSync(`kitguard/static/${file}`, 'utf8'), context);
  }
  vm.runInContext(`
    api = async path => { calls.api.push(path); throw new Error('SYNTHETIC read failure'); };
    post = async path => { calls.posts.push(path); throw new Error('Unexpected mutation'); };
    render = () => {};
    globalThis.ui = { state, publicReviewCache, publicReviewKey, refreshPublicReview, digitalReviewFeedback,
      digitalFeedbackBadge, renderAction, renderHeader, renderOrderList, renderPublicReview, showPendingReviewOpinions };
  `, context);
  const ui = context.ui;
  Object.assign(ui.state, { order: clone(order), orders: [clone(order)], selectedPhoto: photo.id,
    health: { model: { available: true, observer_protocol_sha256: 'synthetic-protocol' } } });
  function setSummary(feedback = pending, list = reviews) {
    Object.assign(ui.publicReviewCache, { key: ui.publicReviewKey(), error: null, summary: {
      order_id: order.id, feedback: clone(feedback), reviews: clone(list), current_review: clone(list.at(-1)?.receipt || null),
      can_review: true, can_replay: false, check: clone(ui.state.order.latest_check),
    } });
  }
  setSummary();
  return { ui, calls, elements, listeners, history, setSummary };
}
(async () => {
  const f = fresh(), before = JSON.stringify(f.ui.state.order);
  for (const lang of ['ko', 'zh']) {
    f.ui.state.lang = lang;
    const action = f.ui.renderAction(f.ui.state.order), header = f.ui.renderHeader(f.ui.state.order);
    const review = f.ui.renderPublicReview(f.ui.state.order);
    f.ui.renderOrderList(); const list = f.elements.get('order-list').innerHTML;
    assert.match(action, /action-warning/); assert.doesNotMatch(action, /action-ready/);
    assert.match(action, /data-action="public-review-opinions"/);
    assert.match(action, lang === 'ko' ? /AI 원래 판단.*현재 사진 수량 일치/ : /AI 原判断.*当前照片数量相符/);
    assert.match(action, lang === 'ko' ? /자동으로 해소되지는 않습니다/ : /不会自动消除/);
    for (const html of [header, list]) {
      assert.match(html, /data-digital-feedback="needs_clarification"/);
      assert.match(html, lang === 'ko' ? /AI 원래 판단.*사진 자료 수량 일치/ : /AI 原判断.*照片资料数量相符/);
    }
    assert.equal((review.match(/data-review-pending="true"/g) || []).length, 3, 'Later acknowledgement cannot clear any prior pending opinion');
    assert.match(review, /&lt;script&gt;synthetic&lt;\/script&gt;/);
    assert.match(review, /&lt;img src=x onerror=alert\(1\)&gt;/); assert.doesNotMatch(review, /<img src=x|<script>/);
    assert.equal(f.history.open, false, 'Rendering does not pretend to perform the user action');
  }
  const button = { disabled: false, dataset: { action: 'public-review-opinions' } };
  for (const fn of f.listeners.get('click')) await fn({ target: { closest() { return button; } } });
  assert.equal(f.history.open, true); assert.equal(f.calls.focus, 1); assert.equal(f.calls.scroll, 1);
  assert.deepEqual(f.calls.api, []); assert.deepEqual(f.calls.posts, []);
  assert.equal(JSON.stringify(f.ui.state.order), before, 'Display/action must not mutate original AI/order/feedback records');

  // Server currentness is authoritative: stale review text alone never creates a current alert.
  const stale = fresh(); stale.setSummary(emptyFeedback(), reviews.map(item => ({ ...item, current: false })));
  assert.doesNotMatch(stale.ui.renderAction(stale.ui.state.order), /action-warning|public-review-opinions/);
  assert.doesNotMatch(stale.ui.renderPublicReview(stale.ui.state.order), /data-review-pending="true"/);
  assert.match(stale.ui.renderPublicReview(stale.ui.state.order), /이전 기록/);
  const acknowledged = { ...emptyFeedback('recorded'), current_count: 1, counts: { ...emptyFeedback().counts, acknowledged: 1 } };
  stale.setSummary(acknowledged, [reviews[3]]);
  assert.equal(stale.ui.digitalReviewFeedback().status, 'recorded');
  assert.doesNotMatch(stale.ui.renderAction(stale.ui.state.order), /action-warning|public-review-opinions/);

  for (const change of [
    x => { x.order.revision++; }, x => { x.order.evidence_epoch++; },
    x => { x.order.photos[0].sha256 = 'b'.repeat(64); },
    x => { x.order.photos.push({ ...photo, id: 'new-photo', created_at: '2026-01-02T00:00:00Z' }); x.selectedPhoto = 'new-photo'; },
    x => { x.order.latest_check.id = 'new-check'; }, x => { x.order.latest_check.valid = false; },
    x => { x.order.latest_check.observed.nut = 0; },
    x => { x.health.model.observer_protocol_sha256 = 'changed'; }, x => { x.order.active_inspection = 'new-job'; },
  ]) {
    const v = fresh(); change(v.ui.state);
    assert.equal(v.ui.digitalReviewFeedback(), null, 'Changed snapshot/runtime must not reuse cached feedback');
    assert.doesNotMatch(v.ui.renderAction(v.ui.state.order), /data-action="public-review-opinions"/);
  }
  const historical = fresh(); historical.ui.state.order.photos.unshift({ ...photo, id: 'old', created_at: '2025-12-31T00:00:00Z' });
  historical.ui.state.selectedPhoto = 'old';
  assert.doesNotMatch(historical.ui.renderAction(historical.ui.state.order), /public-review-opinions|action-warning/);
  assert.doesNotMatch(historical.ui.renderHeader(historical.ui.state.order), /data-digital-feedback="needs_clarification"/);
  assert.doesNotMatch(historical.ui.renderPublicReview(historical.ui.state.order), /data-review-pending="true"/);
  historical.ui.showPendingReviewOpinions(); assert.equal(historical.calls.focus, 0);

  const loading = fresh(); loading.ui.publicReviewCache.key = null;
  assert.equal(loading.ui.digitalReviewFeedback(), null, 'Selected order must wait for matching summary, not silently use its stale GET projection');
  assert.match(loading.ui.renderAction(loading.ui.state.order), /아직 확인하지 못했습니다/);
  assert.doesNotMatch(loading.ui.renderAction(loading.ui.state.order), /action-ready|public-review-opinions/);
  await loading.ui.refreshPublicReview(true);
  assert.equal(loading.ui.digitalReviewFeedback(), null);
  assert.match(loading.ui.renderPublicReview(loading.ui.state.order), /SYNTHETIC read failure/);
  assert.equal(loading.calls.api.length, 1); assert.equal(loading.calls.posts.length, 0);
  const inactive = fresh(); inactive.setSummary(emptyFeedback('not_applicable'));
  assert.doesNotMatch(inactive.ui.renderAction(inactive.ui.state.order), /action-ready|public-review-opinions/);
  assert.match(inactive.ui.renderAction(inactive.ui.state.order), /해결되었다는 뜻은 아닙니다/);

  // Non-selected list rows use only the server projection and retain source-specific wording.
  const list = fresh(); const catalog = clone(order); catalog.id = 'other-catalog'; delete catalog.document_source; catalog.demo_source = { sample_id: 'synthetic' };
  list.ui.state.orders = [catalog]; list.ui.renderOrderList();
  assert.match(list.elements.get('order-list').innerHTML, /공개 사진 수량 일치/);
  assert.match(list.elements.get('order-list').innerHTML, /data-digital-feedback="needs_clarification"/);
  const malformed = fresh(); malformed.ui.publicReviewCache.summary.feedback.pending_count = -1;
  assert.equal(malformed.ui.digitalReviewFeedback(), null);
  const physical = fresh(); delete physical.ui.state.order.document_source;
  assert.equal(physical.ui.digitalReviewFeedback(), null); assert.equal(physical.ui.digitalFeedbackBadge(physical.ui.state.order), '');
  console.log('Digital review feedback UI passed: all current pending opinions, ack retention, server scopes/cache failure, bilingual AI distinction, explicit expand/focus, escaping; synthetic CPU / 0 models / 0 users.');
})().catch(error => { console.error(error); process.exitCode = 1; });
