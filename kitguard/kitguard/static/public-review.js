/* Digital review of public photographs. Physical completion stays separate. */
'use strict';
const PUBLIC_REVIEW_TEXT = {
  zh: {
    title: '公开照片审查', description: '把照片核验交给本机 AI，再由审查人记录判断。订单改版后可以明确沿用同一公开照片重新核验。',
    loading: '正在核对当前审查状态…', retry: '重新读取', inspect: '运行照片核验', stepEvidence: '照片核验', original: '公开资料照片',
    scope: '按螺纹件、螺母、垫圈和角码四个粗类别检查照片数量。尺寸、螺纹、材质和具体型号需要其他证据；不明确的类别会保留为未确认。',
    fixedSource: '此公开样例固定使用来源照片。订单改版后，可在审查面板明确沿用同图重新核验；需要其他证据时，请记录“需要补充资料”及具体要求。',
    captureHint: '此任务使用公开照片。沿用同一图像只表示重新比较订单，不代表移动零件或重新拍摄。',
    ready: '当前照片数量相符', correct: '当前照片与订单有差异', recapture: '照片证据不足', manual: '需要人工进一步核查',
    replay: '沿用公开照片核验新版本', replayTitle: '为新订单版本登记同一照片',
    replayDescription: '保留原照片来源和旧版本记录。登记后需要重新运行模型，本操作不提供新的视觉证据。',
    replayConfirm: '我理解这是同一公开照片的回放，没有实际补件或重新拍摄。', replaySaved: '照片已登记到当前版本，请重新核验。',
    review: '记录数字审查', reviewTitle: '记录你对本次核验的判断',
    reviewDescription: '保存本次 AI 原判断、照片和订单版本。审查结论不代表现场零件已齐套，也不计为模型准确率。',
    reviewer: '审查人代号', conclusion: '你的审查结论', note: '依据或需要跟进的问题',
    noteHint: '例如：订单改版后差额变化正确；照片过于模糊，需要补资料。请记录你实际查看后的判断。',
    acknowledged: '已阅读并认可本次核验', needs_more_evidence: '需要补充资料', disputed: '不同意 AI 判断', inconclusive: '目前无法判断',
    digitalConfirm: '我已查看当前照片、订单和核验结果，此记录仅针对数字资料。', saved: '数字审查已记录。',
    noCheck: '先运行当前版本的照片核验，再记录审查。', busy: '等待当前操作结束后再审查。',
    currentReview: '当前核验最近一条意见', history: '审查历史', current: '对应当前证据', superseded: '历史记录 · 不适用于当前证据',
    resultLabel: 'AI 原判断', reviewLabel: '人工审查结论', noPhysical: '数字资料审查，不产生实物完工或出库记录。',
    nextPublic: '核对照片中的差异，并记录你的审查结论；需要其他证据时请说明。',
    toolTrace: '已执行的工具步骤', workflow: '订单 → 照片 → AI 核验 → 人工审查 → 证据包',
    digitalReady: '公开照片数量相符', publicStart: '使用公开照片开始',
    feedbackPending: '数字意见待澄清', feedbackCount: '条待澄清意见', feedbackView: '查看待澄清意见',
    feedbackNext: '先查看异议、补充资料要求或未能判断的原因，再决定下一步核对。后续认可意见不会自动消除这些记录。',
    feedbackUnknown: '尚未核对当前数字意见，请重新读取。', feedbackInactive: '当前没有适用的数字意见范围；历史意见保留，不表示已解决。',
    feedbackRecorded: '当前数字意见已记录', feedbackNone: '当前核验尚无数字意见', feedbackPendingRecord: '待澄清 · 对应当前核验',
    feedbackHistorical: '正在查看历史照片；当前意见提示仅在最新照片中显示。',
    showLatest: '当前正在查看历史照片。请先返回最新照片，再审查当前版本。',
  },
  ko: {
    title: '공개 사진 검토', description: '로컬 AI가 사진과 주문을 대조하고 검토자가 판단을 기록합니다. 주문 변경 후 같은 공개 사진을 명시적으로 재사용해 다시 검사할 수 있습니다.',
    loading: '현재 검토 상태 확인 중…', retry: '다시 확인', inspect: '사진 검사 실행', stepEvidence: '사진 검사', original: '공개 자료 사진',
    scope: '나사류·너트·와셔·브래킷의 거친 네 분류로 사진 수량을 확인합니다. 치수·나사산·재질·세부 규격은 별도 근거가 필요하며, 불명확한 분류는 미확인으로 남습니다.',
    fixedSource: '이 공개 예시는 출처 사진이 고정됩니다. 주문 변경 후 검토 패널에서 같은 사진을 명시적으로 재사용해 검사하세요. 다른 증거가 필요하면 “추가 자료 필요”와 요청 내용을 기록하세요.',
    captureHint: '공개 사진을 사용하는 과제입니다. 같은 사진 재사용은 주문 재비교이며, 부품 이동이나 새 촬영이 아닙니다.',
    ready: '현재 사진 수량 일치', correct: '현재 사진과 주문의 차이', recapture: '사진 증거 부족', manual: '추가 수동 검토 필요',
    replay: '같은 공개 사진으로 새 버전 검사', replayTitle: '새 주문 버전에 같은 사진 등록',
    replayDescription: '원본 출처와 이전 버전 기록을 보존합니다. 등록 후 모델 검사를 다시 실행해야 하며 새로운 시각 증거가 추가되지는 않습니다.',
    replayConfirm: '같은 공개 사진의 재사용이며 실제 보충 작업이나 새 촬영이 아님을 확인합니다.', replaySaved: '현재 버전에 사진을 등록했습니다. 다시 검사하세요.',
    review: '디지털 검토 기록', reviewTitle: '이번 검사에 대한 판단 기록',
    reviewDescription: 'AI의 원래 판단과 사진, 주문 버전을 함께 저장합니다. 실물 작업 완료나 모델 정확도 결과를 뜻하지 않습니다.',
    reviewer: '검토자 코드', conclusion: '검토 결론', note: '근거 또는 후속 확인 사항',
    noteHint: '예: 주문 변경 후 차이가 올바르게 반영됨; 사진이 흐려 추가 자료 필요. 실제 확인한 판단을 기록하세요.',
    acknowledged: '검사 내용을 읽고 동의함', needs_more_evidence: '추가 자료 필요', disputed: 'AI 판단에 동의하지 않음', inconclusive: '현재 판단 불가',
    digitalConfirm: '현재 사진, 주문, 검사 결과를 확인했으며 디지털 자료에 대한 검토만 기록합니다.', saved: '디지털 검토를 기록했습니다.',
    noCheck: '현재 주문 버전의 사진 검사를 먼저 실행하세요.', busy: '현재 작업이 끝난 뒤 검토하세요.',
    currentReview: '현재 검사의 가장 최근 의견', history: '검토 이력', current: '현재 증거에 해당', superseded: '이전 기록 · 현재 증거에 적용 안 됨',
    resultLabel: 'AI 원래 판단', reviewLabel: '사람의 검토 결론', noPhysical: '디지털 자료 검토이며 실물 완료나 출고 기록을 만들지 않습니다.',
    nextPublic: '사진의 차이를 확인하고 검토 결론을 기록하세요. 추가 증거가 필요하면 명시하세요.',
    toolTrace: '실행된 도구 단계', workflow: '주문 → 사진 → AI 검사 → 사람 검토 → 증거 묶음',
    digitalReady: '공개 사진 수량 일치', publicStart: '공개 사진으로 시작',
    feedbackPending: '디지털 의견 확인 필요', feedbackCount: '건의 미확인 의견', feedbackView: '확인이 필요한 의견 보기',
    feedbackNext: '이의, 추가 자료 요청 또는 판단 불가 사유를 먼저 확인하고 다음 확인 방법을 결정하세요. 나중에 동의 의견을 남겨도 기존 의견이 자동으로 해소되지는 않습니다.',
    feedbackUnknown: '현재 디지털 의견을 아직 확인하지 못했습니다. 다시 불러오세요.', feedbackInactive: '현재 검사에 적용할 의견 범위가 없습니다. 이전 의견은 보존되며, 해결되었다는 뜻은 아닙니다.',
    feedbackRecorded: '현재 디지털 의견 기록됨', feedbackNone: '현재 검사에 디지털 의견 없음', feedbackPendingRecord: '확인 필요 · 현재 검사 의견',
    feedbackHistorical: '이전 사진을 보고 있습니다. 현재 의견 알림은 최신 사진에서 표시합니다.',
    showLatest: '이전 사진을 보고 있습니다. 최신 사진으로 돌아온 뒤 현재 버전을 검토하세요.',
  },
};
const DOCUMENT_REVIEW_TEXT = {
  ko: {
    title: '사진 자료 검토', description: '등록한 사진과 주문을 로컬 AI로 대조하고 검토 의견을 기록합니다. 주문 변경 후 같은 사진을 명시적으로 재사용해 다시 검사하세요.',
    original: '등록한 자료 사진', fixedSource: '사진과 출처 진술이 고정된 자료 주문입니다. 주문 변경 후 같은 사진을 재사용해 검사할 수 있습니다. 다른 사진은 새 자료 주문으로 등록하세요.',
    captureHint: '사용자 출처 진술은 미검증입니다. 같은 사진 재사용은 주문 재비교이며 새 촬영이나 부품 보충이 아닙니다.',
    replay: '같은 자료 사진으로 새 버전 검사', replayConfirm: '같은 자료 사진의 재사용이며 실제 보충 작업이나 새 촬영이 아님을 확인합니다.', digitalReady: '사진 자료 수량 일치',
  },
  zh: {
    title: '照片资料审查', description: '由本机 AI 比较登记的照片与订单，再记录审查意见。订单改版后，可明确沿用同一照片重新核验。',
    original: '登记的资料照片', fixedSource: '此资料工单锁定照片与来源声明。订单改版后可以沿用同图重核；使用其他照片时，请另建资料工单。',
    captureHint: '用户自报来源尚未核实。同图回放只是重新比较订单，不代表新拍摄或补件。',
    replay: '沿用资料照片核验新版本', replayConfirm: '我理解这是同一资料照片的回放，没有实际补件或重新拍摄。', digitalReady: '照片资料数量相符',
  },
};
function prText(key) { return (state.order && Object.prototype.hasOwnProperty.call(state.order, 'document_source') && DOCUMENT_REVIEW_TEXT[state.lang]?.[key]) || PUBLIC_REVIEW_TEXT[state.lang]?.[key] || PUBLIC_REVIEW_TEXT.ko[key] || key; }
function publicOrderText(key) {
  if (!digitalOnlyOrder(state.order)) return null;
  return ({ inspect: prText('inspect'), stepEvidence: prText('stepEvidence'), original: prText('original'),
    protocolText: prText('scope'), captureHint: prText('captureHint'),
    correctTitle: prText('correct'), recaptureTitle: prText('recapture'), protocol1: prText('workflow'), protocol2: prText('noPhysical'),
    protocol3: prText('reviewDescription'), completionFootnote: prText('noPhysical') })[key] || null;
}
const publicReviewCache = { key: null, summary: null, error: null, pending: null };
let publicReviewFormContext = null;
function publicReviewKey(order = state.order) {
  const runtime = state.health?.model || {};
  const runtimeKey = JSON.stringify(['label', 'repo_id', 'revision', 'observer_protocol_sha256',
    'observation_mode', 'image_max_side', 'available'].map(key => runtime[key] ?? null));
  return digitalOnlyOrder(order) ? JSON.stringify([order.id, order.revision, order.evidence_epoch,
    order.latest_check, latestPhoto(order)?.id, latestPhoto(order)?.sha256,
    order.updated_at, !!order.active_inspection, runtimeKey]) : null;
}
// Scope and currentness are derived by the server; never infer them from an opinion alone.
function digitalReviewFeedback(order = state.order) {
  if (!digitalOnlyOrder(order)) return null;
  const selected = order.id === state.order?.id;
  const value = selected
    ? publicReviewCache.key === publicReviewKey(state.order) && !publicReviewCache.error
      ? publicReviewCache.summary?.feedback : null
    : order.digital_review_feedback;
  const conclusions = ['acknowledged', 'needs_more_evidence', 'disputed', 'inconclusive'];
  if (!value || value.schema_version !== 1 || !['needs_clarification', 'recorded', 'none', 'not_applicable'].includes(value.status)
      || !Number.isInteger(value.current_count) || value.current_count < 0
      || !Number.isInteger(value.pending_count) || value.pending_count < 0
      || !conclusions.every(key => Number.isInteger(value.counts?.[key]) && value.counts[key] >= 0)
      || !Array.isArray(value.pending_review_ids) || !value.pending_review_ids.every(id => typeof id === 'string')
      || value.pending_count !== value.pending_review_ids.length
      || value.pending_count !== conclusions.slice(1).reduce((sum, key) => sum + value.counts[key], 0)
      || value.current_count !== conclusions.reduce((sum, key) => sum + value.counts[key], 0)
      || (value.status === 'needs_clarification') !== (value.pending_count > 0)
      || (value.status !== 'not_applicable' && (!order.latest_check?.valid || value.check_id !== order.latest_check.id))) return null;
  return value;
}
function digitalFeedbackBadge(order) {
  if (!digitalOnlyOrder(order)) return '';
  if (order.id === state.order?.id && selectedPhoto()?.id !== latestPhoto(order)?.id) return '';
  const resolution = typeof activeResolution === 'function' ? activeResolution(order) : null;
  if (resolution) return `<span class="badge resolution-current-badge">${esc(rsText(resolution.outcome))}</span>`;
  const feedback = digitalReviewFeedback(order);
  if (feedback?.status === 'needs_clarification') return `<span class="badge digital-feedback-pending" data-digital-feedback="needs_clarification">${esc(prText('feedbackPending'))} · ${feedback.pending_count}</span>`;
  if (!feedback) return `<span class="badge digital-feedback-unknown" data-digital-feedback="unknown">${esc(prText('feedbackUnknown'))}</span>`;
  return '';
}
function pendingReviewButton(disabled = false) {
  return `<button class="btn btn-secondary btn-full" data-action="public-review-opinions" ${disabled ? 'disabled' : ''}>${icon('file')}${esc(prText('feedbackView'))}</button>`;
}
function showPendingReviewOpinions() {
  if (selectedPhoto()?.id !== latestPhoto()?.id || digitalReviewFeedback()?.status !== 'needs_clarification') return;
  const history = document.getElementById('public-review-history');
  if (!history) return;
  history.open = true;
  const target = history.querySelector('[data-review-pending="true"]') || history.querySelector('summary');
  if (target) { target.focus({ preventScroll: true }); target.scrollIntoView({ block: 'center', behavior: 'auto' }); }
}
async function refreshPublicReview(force = false) {
  const key = publicReviewKey();
  if (!key || publicReviewCache.pending === key || (!force && publicReviewCache.key === key)) return;
  const id = state.order.id; publicReviewCache.pending = key;
  try {
    const summary = await api(`/api/orders/${encodeURIComponent(id)}/public-review-summary`);
    if (publicReviewKey() !== key) return;
    Object.assign(publicReviewCache, { key, summary, error: null });
  } catch (error) {
    if (publicReviewKey() !== key) return;
    Object.assign(publicReviewCache, { key, summary: null, error: error.message });
  } finally {
    if (publicReviewCache.pending === key) publicReviewCache.pending = null;
    if (publicReviewKey() === key) render();
  }
}
function renderPublicReview(order) {
  if (!digitalOnlyOrder(order)) return '';
  const key = publicReviewKey(order);
  if (publicReviewCache.key !== key) queueMicrotask(() => refreshPublicReview());
  const summary = publicReviewCache.key === key ? publicReviewCache.summary : null;
  const error = publicReviewCache.key === key ? publicReviewCache.error : null;
  const historical = selectedPhoto()?.id !== latestPhoto(order)?.id;
  const disabled = state.busy || order.active_inspection || historical;
  const feedback = digitalReviewFeedback(order);
  const resolution = typeof activeResolution === 'function' ? activeResolution(order) : null;
  const pending = !historical && !resolution && feedback?.status === 'needs_clarification';
  const pendingIds = new Set(pending ? feedback.pending_review_ids : []);
  const reviews = summary?.reviews || [];
  const history = reviews.length ? `<details class="public-review-history" id="public-review-history"><summary>${esc(prText('history'))} · ${reviews.length}</summary>${[...reviews].reverse().map(item => {
    const receipt = item.receipt;
    const unresolved = item.current && pendingIds.has(receipt.id);
    return `<article tabindex="-1" data-review-pending="${unresolved ? 'true' : 'false'}"><div><b>R${esc(receipt.revision)}</b><span class="badge ${unresolved ? 'digital-feedback-pending' : item.current ? 'revision' : 'invalid'}">${esc(prText(unresolved ? 'feedbackPendingRecord' : item.current ? 'current' : 'superseded'))}</span></div><strong>${esc(prText(receipt.conclusion))}</strong><p>${esc(receipt.operator_code)} · ${esc(formatDate(receipt.created_at))}</p><p class="public-review-note">${esc(receipt.note)}</p></article>`;
  }).join('')}</details>` : '';
  const current = summary?.current_review;
  const status = current ? `<div class="public-review-receipt"><strong>${icon('file')}${esc(prText('currentReview'))}</strong><p>${esc(prText(current.conclusion))}</p><small>${esc(current.operator_code)} · ${esc(formatDate(current.created_at))}</small></div>` : '';
  const guidance = historical ? prText('showLatest') : state.busy || order.active_inspection ? prText('busy')
    : pending ? prText('feedbackNext') : summary?.can_review ? prText('nextPublic') : summary?.review_blockers?.join(' · ') || prText('noCheck');
  let controls = summary ? `<p class="public-review-guidance">${esc(guidance)}</p>` : `<p>${esc(error || prText('loading'))}</p>`;
  if (summary?.can_replay) controls = `<p class="public-review-guidance">${esc(prText('replayDescription'))}</p><button class="btn btn-secondary btn-full" data-action="public-replay" ${disabled ? 'disabled' : ''}>${icon('refresh')}${esc(prText('replay'))}</button>`;
  if (summary?.can_review) controls += `<button class="btn btn-primary btn-full" data-action="public-review" ${disabled ? 'disabled' : ''}>${icon('file')}${esc(prText('review'))}</button>`;
  if (historical) controls += `<button class="btn btn-secondary btn-full" data-action="show-latest">${esc(t('showLatest'))}</button>`;
  if (error) controls += `<button class="btn btn-secondary" data-action="public-review-refresh">${esc(prText('retry'))}</button>`;
  const feedbackNotice = historical ? `<p>${esc(prText('feedbackHistorical'))}</p>` : pending
    ? `<div class="digital-feedback-notice" role="status"><strong>${esc(prText('feedbackPending'))} · ${feedback.pending_count} ${esc(prText('feedbackCount'))}</strong><p>${esc(['disputed', 'needs_more_evidence', 'inconclusive'].filter(key => feedback.counts[key]).map(key => `${prText(key)} ${feedback.counts[key]}`).join(' · '))}</p>${pendingReviewButton(disabled)}</div>`
    : `<p class="public-review-feedback-status">${esc(prText(!feedback ? 'feedbackUnknown' : feedback.status === 'not_applicable' ? 'feedbackInactive' : feedback.status === 'recorded' ? 'feedbackRecorded' : 'feedbackNone'))}</p>`;
  return `<section class="panel public-review-panel" aria-labelledby="public-review-title"><div class="check-heading"><h2 id="public-review-title">${esc(prText('title'))}</h2><span class="badge revision">R${esc(order.revision)}</span></div><p>${esc(prText('description'))}</p>${summary?.check ? `<div class="public-review-ai"><small>${esc(prText('resultLabel'))}</small><strong>${esc(prText(summary.check.decision))}</strong></div>` : ''}${typeof renderResolutionPanel === 'function' ? renderResolutionPanel(order, summary, disabled) : ''}${resolution ? '' : feedbackNotice}${status}${controls}${history}<p class="public-review-boundary">${esc(prText('noPhysical'))}</p></section>`;
}
async function openPublicReviewDialog(replay) {
  if (state.busy || !digitalOnlyOrder(state.order)) return;
  if (selectedPhoto()?.id !== latestPhoto()?.id) { toast(prText('showLatest')); return; }
  const id = state.order.id;
  try {
    const summary = await api(`/api/orders/${encodeURIComponent(id)}/public-review-summary`);
    if (id !== state.order?.id || state.busy || selectedPhoto()?.id !== latestPhoto()?.id) return;
    if (!(replay ? summary.can_replay : summary.can_review)) {
      await refreshPublicReview(true); toast(prText('noCheck')); return;
    }
    publicReviewFormContext = { id, request: replay ? summary.replay_request : summary.review_request };
    const title = prText(replay ? 'replayTitle' : 'reviewTitle');
    const description = prText(replay ? 'replayDescription' : 'reviewDescription');
    const fields = replay ? '' : `<label class="field"><span>${esc(prText('reviewer'))}</span><input name="operator_code" required maxlength="80" autocomplete="off"></label><label class="field"><span>${esc(prText('conclusion'))}</span><select name="conclusion" required><option value="">—</option>${['acknowledged', 'needs_more_evidence', 'disputed', 'inconclusive'].map(value => `<option value="${value}">${esc(prText(value))}</option>`).join('')}</select></label><label class="field"><span>${esc(prText('note'))}</span><textarea name="note" required maxlength="2000" rows="4" placeholder="${esc(prText('noteHint'))}"></textarea></label>`;
    openModal('workflow-dialog', `<div class="modal-header"><div><h2>${esc(title)}</h2><p>${esc(description)}</p></div><button class="icon-btn" type="button" data-action="close-modal" aria-label="${esc(t('close'))}">${icon('close')}</button></div><form id="public-${replay ? 'replay' : 'review'}-form" data-key="${crypto.randomUUID()}"><div class="modal-content"><span class="badge revision">R${esc(state.order.revision)}</span>${fields}<label class="confirm-box"><input name="confirmed" type="checkbox" required><span>${esc(prText(replay ? 'replayConfirm' : 'digitalConfirm'))}</span></label><div class="modal-error" role="alert"></div></div><div class="modal-footer"><button type="button" class="btn btn-quiet" data-action="close-modal">${esc(t('cancel'))}</button><button class="btn btn-primary" type="submit" data-mutate>${esc(prText(replay ? 'replay' : 'review'))}</button></div></form>`);
  } catch (error) { showError(error); }
}
document.addEventListener('click', event => {
  const button = event.target.closest('[data-action]'); if (!button || button.disabled) return;
  if (button.dataset.action === 'public-review') openPublicReviewDialog(false);
  if (button.dataset.action === 'public-replay') openPublicReviewDialog(true);
  if (button.dataset.action === 'public-review-refresh') refreshPublicReview(true);
  if (button.dataset.action === 'public-review-opinions') showPendingReviewOpinions();
});
document.addEventListener('submit', async event => {
  const form = event.target;
  if (!['public-review-form', 'public-replay-form'].includes(form.id)) return;
  event.preventDefault();
  if (state.busy || !publicReviewFormContext || publicReviewFormContext.id !== state.order?.id) return;
  const replay = form.id === 'public-replay-form';
  const body = { ...publicReviewFormContext.request, idempotency_key: form.dataset.key };
  if (replay) body.confirmed_no_physical_capture = form.elements.namedItem('confirmed').checked;
  else Object.assign(body, { operator_code: form.elements.namedItem('operator_code').value.trim(),
    conclusion: form.elements.namedItem('conclusion').value, note: form.elements.namedItem('note').value.trim(),
    confirmed_digital_only: form.elements.namedItem('confirmed').checked });
  const result = await mutate(replay ? 'public-replay' : 'public-review',
    () => post(`/api/orders/${encodeURIComponent(publicReviewFormContext.id)}/${replay ? 'public-replay' : 'public-review'}`, body), null, 'workflow-dialog');
  if (result) {
    document.getElementById('workflow-dialog').close(); publicReviewFormContext = null;
    await refreshPublicReview(true); toast(prText(replay ? 'replaySaved' : 'saved'));
  }
});
