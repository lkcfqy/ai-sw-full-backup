'use strict';
// Fresh-page polling and rendering contracts with synthetic server snapshots only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const clone = value => JSON.parse(JSON.stringify(value));
const photo = { id: 'synthetic-photo', revision: 1, sha256: 'a'.repeat(64), created_at: '2026-01-01T00:00:00Z' };
const order = { id: 'synthetic-order', revision: 1, evidence_epoch: 1, status: 'needs_action', photos: [photo],
  latest_check: null, active_inspection: null, events: [{ kind: 'inspection_started', created_at: '2026-01-01T00:00:01.001Z' }] };
const failure = { id: 'synthetic-job', order_id: order.id, revision: 1, evidence_epoch: 1, photo_id: photo.id,
  photo_sha256: photo.sha256, status: 'failed', created_at: '2026-01-01T00:00:01.005Z', request_key: 'synthetic-old-key',
  error: { message: 'SYNTHETIC failure <script>not executable</script>' } };

function fresh(terminal = failure) {
  const storage = new Map([[`kitguard-inspect:${order.id}:1:${photo.id}`, failure.request_key]]);
  const server = { order: clone(order), jobs: [clone(terminal)], health: { ok: true, model: { available: true }, inference: { busy: false } } };
  const calls = { renders: [], posts: [], toasts: [], refreshes: 0, uuid: 0 };
  const context = vm.createContext({
    document: { addEventListener() {}, getElementById() { return { addEventListener() {} }; }, querySelectorAll() { return []; } },
    window: { addEventListener() {} },
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
    crypto: { randomUUID() { return `synthetic-new-key-${++calls.uuid}`; } },
    setTimeout() { return 1; }, clearTimeout() {}, setInterval() { return 1; }, clearInterval() {},
    apiFixture: async path => {
      if (path === '/api/health') return clone(server.health);
      if (path.endsWith('/inspection-jobs')) return { jobs: clone(server.jobs) };
      return { order: clone(server.order) };
    },
    postFixture: async (path, body) => {
      calls.posts.push({ path, body: clone(body) });
      server.jobs.unshift({ ...clone(failure), id: 'synthetic-retry', request_key: body.request_key, status: 'running', error: null,
        created_at: '2026-01-01T00:00:03Z' });
      server.order.active_inspection = 'synthetic-token';
      return { job: clone(server.jobs[0]) };
    },
    calls,
  });
  for (const file of ['app.js', 'workflow.js']) vm.runInContext(fs.readFileSync(`kitguard/static/${file}`, 'utf8'), context);
  vm.runInContext(`
    api = apiFixture; post = postFixture;
    render = () => calls.renders.push(workflowRuntimeNotice());
    refreshOrders = async () => { calls.refreshes++; };
    toast = message => calls.toasts.push(message);
    setBusy = kind => { state.busy = kind; render(); };
    clearBusy = () => { state.busy = null; render(); };
    globalThis.ui = { state, recoverInspectionState, workflowRuntimeNotice, startInspectionJob };
  `, context);
  const ui = context.ui;
  Object.assign(ui.state, { order: clone(server.order), selectedPhoto: photo.id, health: clone(server.health), error: null });
  return { ui, server, calls, storage };
}

(async () => {
  // Empty in-memory job is the actual fresh-page path, not running→failed.
  for (const status of ['failed', 'interrupted']) {
    const { ui, server, calls, storage } = fresh({ ...failure, status });
    assert.equal(ui.state.inspectionJob, undefined);
    await ui.recoverInspectionState();
    assert.equal(calls.posts.length, 0, 'Restoring a failure must never start inference');
    assert.equal(storage.size, 0, 'Terminal idempotency key is retired before an explicit retry');
    for (const lang of ['ko', 'zh']) {
      ui.state.lang = lang;
      const html = ui.workflowRuntimeNotice();
      assert.match(html, /role="alert".*data-inspection-recovery="synthetic-job"/);
      assert.match(html, /data-action="model"/); assert.match(html, /data-action="inspect"/);
      assert.match(html, /&lt;script&gt;/); assert.doesNotMatch(html, /<script>/);
      assert.match(html, lang === 'ko' ? /이전 실패 기록은 유지됩니다/ : /原失败记录会保留/);
      if (status === 'interrupted') assert.match(html, lang === 'ko' ? /이전 검사가 중단/ : /上次核验已中断/);
    }
    assert.equal(ui.state.health.model.available, true, 'A failed call does not change model availability');
    server.health.model.available = false;
    await ui.recoverInspectionState();
    assert.match(ui.workflowRuntimeNotice(), /data-action="inspect" disabled/);
    server.health.model.available = true; server.health.inference.busy = true;
    await ui.recoverInspectionState();
    assert.match(ui.workflowRuntimeNotice(), /data-action="inspect" disabled/);
  }

  const obsolete = [
    value => { value.order.id = 'another-order'; },
    value => { value.order.revision = 2; },
    value => { value.order.evidence_epoch = 2; }, // Includes reference replacement.
    value => { value.order.photos.push({ ...photo, id: 'new-photo', created_at: '2026-01-01T00:00:04Z' }); },
    value => { value.order.photos[0].sha256 = 'b'.repeat(64); },
    value => { value.order.status = 'manual_reviewed'; },
    value => { value.order.active_inspection = 'a-new-run'; },
    value => { value.order.events.push({ kind: 'inspection_started', created_at: '2026-01-01T00:00:03Z' }); },
    value => { value.order.latest_check = { created_at: '2026-01-01T00:00:03Z' }; },
    value => { value.jobs[0].status = 'succeeded'; },
  ];
  for (const change of obsolete) {
    const { ui, server } = fresh(); await ui.recoverInspectionState();
    change(server); ui.state.order = clone(server.order);
    await ui.recoverInspectionState();
    assert.doesNotMatch(ui.workflowRuntimeNotice(), /data-inspection-recovery=/);
  }
  const historical = fresh(); await historical.ui.recoverInspectionState();
  historical.ui.state.order.photos.unshift({ ...photo, id: 'historical-photo', created_at: '2025-12-31T00:00:00Z' });
  historical.ui.state.selectedPhoto = 'historical-photo';
  assert.doesNotMatch(historical.ui.workflowRuntimeNotice(), /data-inspection-recovery=/);

  // Explicit retry starts once with a fresh key, then a returned success clears the notice.
  const { ui, server, calls } = fresh(); await ui.recoverInspectionState();
  await ui.startInspectionJob();
  assert.equal(calls.posts.length, 1); assert.notEqual(calls.posts[0].body.request_key, failure.request_key);
  assert.equal(ui.state.busy, 'inspect'); assert.doesNotMatch(ui.workflowRuntimeNotice(), /data-inspection-recovery=/);
  server.order.active_inspection = null;
  server.order.latest_check = { created_at: '2026-01-01T00:00:04Z', backend: 'test' };
  server.jobs[0].status = 'succeeded';
  await ui.recoverInspectionState();
  assert.equal(ui.state.busy, null); assert.doesNotMatch(ui.workflowRuntimeNotice(), /data-inspection-recovery=/);
  assert.equal(server.jobs[1].status, 'failed', 'Recovery never rewrites historical failures');
  console.log('Synthetic inspection recovery: fresh page, bilingual notice, scoped expiry, no implicit retry, success clearing passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
