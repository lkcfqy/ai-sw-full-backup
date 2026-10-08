'use strict';
// Synthetic rendering contracts only; no browser, server, or inference.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({
  document: { addEventListener() {} },
  state: { lang: 'zh', order: { references: { nut: { id: 'CURRENT_REFERENCE_MUST_NOT_LEAK' } } } },
  PARTS: ['bolt', 'nut', 'washer', 'bracket'],
  partLabel: part => part,
  esc: value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char])),
});
vm.runInContext(fs.readFileSync('kitguard/static/audit.js', 'utf8'), context);
vm.runInContext('globalThis.renderReference = auditReferenceEvidenceMarkup', context);
const evidence = {
  images: [{ part: 'nut', image_index: 2, photo_id: '<img src=x onerror=alert(1)>', prepared_size: [76, 76],
    stored_sha256: 'a'.repeat(64), prepared_sha256: 'b'.repeat(64), upload_source_sha256: 'c'.repeat(64) }],
  stages: [{ stage: 'original', reference_image_indices: [2], status: 'completed' },
    { stage: 'rotate_90_ccw', reference_image_indices: [2], status: 'completed' },
    { stage: 'identity', reference_image_indices: [], status: 'skipped_no_candidates' }],
  prepared_bytes_retained: false, preprocessing: 'recorded_preprocessing', pillow_version: 'test',
};
for (const lang of ['ko', 'zh']) {
  context.state.lang = lang;
  const legacy = context.renderReference({ reference_ids: { nut: 'historical-id' } });
  assert.match(legacy, /data-reference-evidence="unrecorded"/);
  assert.doesNotMatch(legacy, /CURRENT_REFERENCE|historical-id|data-reference-stage/);
  const html = context.renderReference({ reference_evidence: evidence });
  assert.equal((html.match(/data-reference-stage=/g) || []).length, 3);
  const identity = html.match(/<tr data-reference-stage="identity">(.*?)<\/tr>/s)[1];
  assert.match(identity, lang === 'zh' ? /未执行：没有候选/ : /미실행: 후보 없음/);
  assert.match(identity, lang === 'zh' ? /无类别参考输入/ : /종류별 기준 입력 없음/);
  assert.doesNotMatch(identity, /#2|nut/);
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /&lt;img/);
  assert.doesNotMatch(html.split('<details class="audit-photo-metadata">')[0], /b{64}/);
  assert.match(html, /b{64}/);
  const none = context.renderReference({ reference_evidence: { images: [], stages: [{ stage: 'original', status: 'completed', reference_image_indices: [] }] } });
  assert.match(none, /data-reference-evidence="recorded"/);
  assert.doesNotMatch(none, /data-reference-stage="identity"/);
}
console.log('Reference input history, stage identity, collapsed SHA and escaping UI contracts passed.');
