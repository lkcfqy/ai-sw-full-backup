/* Durable inspection recovery and explicit human review. No inference fallback. */
'use strict';
Object.assign(STRINGS.ko, {
  manual_reviewed: '사람 확인 기록', manualReview: '사람이 직접 확인하고 기록', manualReviewTitle: '실물 직접 확인 기록', manualReviewDescription: 'AI 결과를 바꾸지 않고, 직접 센 수량과 처리 결과를 별도로 남깁니다.',
  operatorCode: '작업자 코드', actualCounts: '실물에서 직접 센 수량', manualReason: '직접 확인하는 이유 / 처리 메모', manualPhysical: '사진이 아닌 실제 부품을 직접 확인했습니다.', manualBom: '현재 작업지시와 대조했습니다. 수량이 다르면 미해결로 기록됩니다.', manualSaved: '사람 확인 기록을 저장했습니다.',
  manualMatched: '사람 확인 · 수량 일치', manualUnresolved: '사람 확인 · 미해결', manualRecordNote: 'AI 검사 성공이나 자동 출하가 아닙니다. 수정하려면 새 버전으로 다시 처리하세요.', reopen: '새 버전으로 다시 처리', reopenTitle: '처리 기록을 보존하고 다시 시작', reopenDescription: '수량은 그대로 두고 새 버전을 만듭니다. 이전 사진·검사로 새 버전을 완료할 수 없습니다.', reopenConfirm: '이전 기록을 보존하고 새 사진부터 다시 시작합니다.', reopenSaved: '새 버전이 열렸습니다. 새로 촬영하세요.',
  backgroundBusy: '모델이 이전 작업을 처리 중입니다. 새 검사는 기다려 주세요.', reconnectingJob: '서버 기록에서 진행 상태를 복구합니다. 화면을 새로 고쳐도 검사를 중복 실행하지 않습니다.', jobFailed: '검사 미완료',
  jobInterrupted: '이전 검사가 중단되었습니다', retryInspection: '다시 검사', jobRecoveryHelp: '표시된 사유를 확인하고, 필요하면 모델 상태를 확인한 뒤 다시 검사하세요. 이전 실패 기록은 유지됩니다.',
});
Object.assign(STRINGS.zh, {
  manual_reviewed: '已记录人工复核', manualReview: '人工核对并记录', manualReviewTitle: '直接核对实物', manualReviewDescription: '分别保存人工实点数量和处理结果，保留 AI 原结论。',
  operatorCode: '操作者代号', actualCounts: '直接清点实物的数量', manualReason: '转人工原因或处理说明', manualPhysical: '我已直接清点实际零件，而非只看照片。', manualBom: '我已对照当前工单。数量不符会记录为未解决。', manualSaved: '已保存人工复核记录。',
  manualMatched: '人工核对 · 数量相符', manualUnresolved: '人工核对 · 未解决', manualRecordNote: '这是人工处理记录，不计为 AI 核验成功或自动出库。需继续处理时，请开启新版本。', reopen: '开启新版本重新处理', reopenTitle: '保留原记录，重新处理', reopenDescription: '保持需求数量并生成新版本。旧照片和核验结果不能用于完成新版本。', reopenConfirm: '保留原记录，从新照片开始重新处理。', reopenSaved: '已开启新版本，请重新拍照。',
  backgroundBusy: '模型仍在处理上一项任务，请等待结束后再运行新的核验。', reconnectingJob: '正在恢复服务器中的任务状态；刷新页面不会重复运行核验。', jobFailed: '核验未完成',
  jobInterrupted: '上次核验已中断', retryInspection: '重试核验', jobRecoveryHelp: '请按所示原因处理，必要时检查模型状态后重试。原失败记录会保留。',
});
let inspectionPollTimer = null;
let inspectionPollGeneration = 0;
function finalizedOrder(order = state.order) { return ['completed', 'manual_reviewed'].includes(order?.status); }
function pendingRequestKey(order, photo) { return `kitguard-inspect:${order.id}:${order.revision}:${photo.id}`; }
function savedInspectionRequest(order, photo) {
  const key = pendingRequestKey(order, photo);
  let requestKey;
  try { requestKey = localStorage.getItem(key); } catch { /* Storage is optional. */ }
  if (!requestKey) {
    requestKey = crypto.randomUUID();
    try { localStorage.setItem(key, requestKey); } catch { /* Server-side recovery remains available. */ }
  }
  return { photo_id: photo.id, expected_revision: order.revision, request_key: requestKey };
}
function forgetInspectionRequest(job) {
  try { const key = `kitguard-inspect:${job.order_id}:${job.revision}:${job.photo_id}`; if (localStorage.getItem(key) === job.request_key) localStorage.removeItem(key); } catch { /* Optional. */ }
}
function currentInspectionFailure() {
  const order = state.order, job = state.inspectionJob, photo = latestPhoto(order);
  if (!order || !job || !photo || !['failed', 'interrupted'].includes(job.status) || state.busy || order.active_inspection || finalizedOrder(order)) return null;
  if (job.order_id !== order.id || job.revision !== order.revision || job.photo_id !== photo?.id || selectedPhoto()?.id !== photo?.id
      || !Number.isInteger(job.evidence_epoch) || job.evidence_epoch !== order.evidence_epoch || job.photo_sha256 !== photo.sha256) return null;
  const started = Date.parse(job.created_at);
  if (!Number.isFinite(started)) return null;
  // A newer synchronous inspection may have no durable job row of its own.
  if ((order.events || []).some(event => event.kind === 'inspection_started' && Date.parse(event.created_at) > started)
      || Date.parse(order.latest_check?.created_at) >= started) return null;
  return job;
}
function workflowRuntimeNotice() {
  const busy = state.health?.inference?.busy;
  let notice = busy && state.busy !== 'inspect' ? `<div class="notice-banner" role="status"><span class="spinner"></span>${esc(t('backgroundBusy'))}</div>` : '';
  const failed = currentInspectionFailure();
  if (failed) notice += `<div class="notice-banner inspection-recovery" role="alert" data-inspection-recovery="${esc(failed.id)}"><div><strong>${esc(t(failed.status === 'interrupted' ? 'jobInterrupted' : 'jobFailed'))}</strong>${failed.error?.message ? `<p>${esc(failed.error.message)}</p>` : ''}<p>${esc(t('jobRecoveryHelp'))}</p></div><div class="inspection-recovery-actions"><button class="btn btn-secondary btn-sm" data-action="model">${esc(t('modelTitle'))}</button><button class="btn btn-primary btn-sm" data-action="inspect" ${busy || !state.health?.model?.available ? 'disabled' : ''}>${esc(t('retryInspection'))}</button></div></div>`;
  return notice;
}
async function recoverInspectionState() {
  const orderId = state.order?.id;
  if (!orderId) return;
  const generation = ++inspectionPollGeneration;
  clearTimeout(inspectionPollTimer);
  return await pollInspectionState(orderId, generation, false);
}
async function pollInspectionState(orderId, generation, repeated) {
  if (state.order?.id !== orderId || generation !== inspectionPollGeneration) return;
  try {
    const [orderResult, jobResult, health] = await Promise.all([
      api(`/api/orders/${encodeURIComponent(orderId)}`),
      api(`/api/orders/${encodeURIComponent(orderId)}/inspection-jobs`), api('/api/health'),
    ]);
    if (state.order?.id !== orderId || generation !== inspectionPollGeneration) return;
    if (state.busy && state.busy !== 'inspect') { inspectionPollTimer = setTimeout(() => pollInspectionState(orderId, generation, true), 1200); return false; }
    state.order = orderResult.order; state.health = health;
    const jobs = jobResult.jobs || [];
    const active = jobs.find(job => job.status === 'running');
    const latest = jobs[0];
    const hadJob = state.inspectionJob;
    state.inspectionJob = active || latest || null;
    if (active || state.order.active_inspection) {
      if (state.busy !== 'inspect') setBusy('inspect');
      const started = active?.created_at || [...(state.order.events || [])].reverse().find(event => event.kind === 'inspection_started')?.created_at;
      state.startedAt = Date.parse(started) || Date.now();
    } else {
      if (state.busy === 'inspect') clearBusy();
      if (latest && latest.status !== 'running') {
        forgetInspectionRequest(latest);
        if (hadJob?.id === latest.id && hadJob.status === 'running') {
          if (latest.status === 'succeeded') { state.error = null; toast(t('checkFinished')); }
          else if (state.error === t('reconnectingJob')) state.error = null;
          await refreshOrders();
        }
      }
    }
    render();
    if (active || state.order.active_inspection || health.inference?.busy) {
      inspectionPollTimer = setTimeout(() => pollInspectionState(orderId, generation, true), 1200);
    }
    return true;
  } catch (error) {
    if (state.order?.id !== orderId || generation !== inspectionPollGeneration) return;
    if (state.busy === 'inspect' || repeated) {
      state.error = t('reconnectingJob'); render();
      inspectionPollTimer = setTimeout(() => pollInspectionState(orderId, generation, true), 1800);
    }
    return false;
  }
}
async function startInspectionJob() {
  const order = state.order, photo = selectedPhoto();
  if (!order || !photo || state.busy || finalizedOrder() || state.health?.inference?.busy) return;
  setBusy('inspect'); state.error = null;
  try {
    const response = await post(`/api/orders/${encodeURIComponent(order.id)}/inspection-jobs`, savedInspectionRequest(order, photo));
    state.inspectionJob = response.job;
    if (response.job.status !== 'running') {
      forgetInspectionRequest(response.job);
    }
    await recoverInspectionState();
  } catch (error) {
    // Acceptance may have succeeded even if its HTTP response was lost.
    state.error = error.message;
    const confirmed = await recoverInspectionState();
    if (confirmed && state.busy === 'inspect' && !state.order?.active_inspection && !state.health?.inference?.busy) clearBusy();
    render();
  }
}
function manualReviewButton(order, check) {
  return !finalizedOrder(order) && latestPhoto(order)?.revision === order.revision && !digitalOnlyOrder(order) && check?.backend !== 'test' && !order.active_inspection ? `<button class="btn btn-quiet btn-full" data-action="manual-review" ${state.busy ? 'disabled' : ''}>${icon('hand')}${esc(t('manualReview'))}</button>` : '';
}
function manualReviewCard(order) {
  const review = [...(order.manual_reviews || [])].reverse().find(item => item.revision === order.revision);
  if (!review) return '';
  return `<div class="manual-review-receipt"><strong>${esc(t(review.matches_requirements ? 'manualMatched' : 'manualUnresolved'))}</strong><p>${esc(review.operator_code)} · ${esc(formatDate(review.created_at))}</p><div class="manual-counts">${PARTS.map(part => `<span>${esc(partLabel(part))} <b>${esc(review.actual_counts[part])}</b></span>`).join('')}</div><p>${esc(review.reason)}</p><small>${esc(t('manualRecordNote'))}</small></div>`;
}
function reopenButton(order) { return finalizedOrder(order) ? `<button class="btn btn-secondary btn-full" data-action="reopen" ${state.busy ? 'disabled' : ''}>${icon('branch')}${esc(t('reopen'))}</button>` : ''; }
function openManualReview() {
  if (state.busy || finalizedOrder() || latestPhoto()?.revision !== state.order?.revision || digitalOnlyOrder(state.order)) return;
  const order = state.order, check = currentCheck();
  const counts = `<div class="quantity-fields">${PARTS.map(part => `<label class="quantity-field"><span>${esc(partLabel(part))}</span><input name="${part}" type="number" min="0" max="100" step="1" required inputmode="numeric" placeholder="—"></label>`).join('')}</div>`;
  openModal('workflow-dialog', `${modalHeader('manualReviewTitle', 'manualReviewDescription')}<form id="manual-review-form" data-revision="${order.revision}" data-epoch="${order.evidence_epoch}" data-photo="${esc(latestPhoto().id)}" data-check="${esc(check?.id || '')}" data-key="${crypto.randomUUID()}"><div class="modal-content"><span class="badge revision">R${order.revision}</span><label class="field"><span>${esc(t('operatorCode'))}</span><input name="operator_code" required maxlength="40" autocomplete="off"></label><p class="field-label">${esc(t('actualCounts'))}</p>${counts}<label class="field"><span>${esc(t('manualReason'))}</span><textarea name="reason" required maxlength="1000" rows="3"></textarea></label><label class="confirm-box"><input name="physical" type="checkbox" required><span>${esc(t('manualPhysical'))}</span></label><label class="confirm-box"><input name="bom" type="checkbox" required><span>${esc(t('manualBom'))}</span></label><div class="modal-error" role="alert"></div></div><div class="modal-footer"><button type="button" class="btn btn-quiet" data-action="close-modal">${esc(t('cancel'))}</button><button class="btn btn-primary" type="submit" data-mutate>${esc(t('manualReview'))}</button></div></form>`);
}
function openReopen() {
  if (state.busy || !finalizedOrder()) return;
  openModal('workflow-dialog', `${modalHeader('reopenTitle', 'reopenDescription')}<form id="reopen-form" data-revision="${state.order.revision}" data-key="${crypto.randomUUID()}"><div class="modal-content"><label class="field"><span>${esc(t('manualReason'))}</span><textarea name="reason" required maxlength="1000" rows="3"></textarea></label><label class="confirm-box"><input name="confirmed" type="checkbox" required><span>${esc(t('reopenConfirm'))}</span></label><div class="modal-error" role="alert"></div></div><div class="modal-footer"><button class="btn btn-quiet" type="button" data-action="close-modal">${esc(t('cancel'))}</button><button class="btn btn-primary" type="submit" data-mutate>${esc(t('reopen'))}</button></div></form>`);
}
document.addEventListener('click', event => {
  const button = event.target.closest('[data-action]'); if (!button || button.disabled) return;
  if (button.dataset.action === 'manual-review') openManualReview();
  if (button.dataset.action === 'reopen') openReopen();
});
document.addEventListener('submit', async event => {
  const form = event.target;
  if (!['manual-review-form', 'reopen-form'].includes(form.id)) return;
  event.preventDefault(); if (state.busy || !state.order) return;
  const reopening = form.id === 'reopen-form';
  const body = { expected_revision: Number(form.dataset.revision), reason: form.elements.namedItem('reason').value.trim(), idempotency_key: form.dataset.key };
  if (reopening) body.confirmed = form.elements.namedItem('confirmed').checked;
  else Object.assign(body, { expected_evidence_epoch: Number(form.dataset.epoch), photo_id: form.dataset.photo, check_id: form.dataset.check || null,
    operator_code: form.elements.namedItem('operator_code').value.trim(), actual_counts: Object.fromEntries(PARTS.map(part => [part, Number(form.elements.namedItem(part).value)])),
    confirmed_physical: form.elements.namedItem('physical').checked, confirmed_current_bom: form.elements.namedItem('bom').checked });
  const result = await mutate(reopening ? 'reopen' : 'manual-review', () => post(`/api/orders/${encodeURIComponent(state.order.id)}/${reopening ? 'reopen' : 'manual-review'}`, body), reopening ? 'reopenSaved' : 'manualSaved', 'workflow-dialog');
  if (result) document.getElementById('workflow-dialog').close();
});
