/* A reviewer marks visible objects. AI observations stay immutable. */
'use strict';
const RESOLUTION_TEXT = {
  zh: {
    title: '逐件复核与审核结论', start: '在照片上逐件复核', edit: '重新形成审核结论',
    lead: '选择类别，再点照片中的每件物体。数量由标记汇总，AI 原观察单独保留。',
    matched: '复核数量相符', mismatch: '复核发现数量差异', needs_more_evidence: '已记录补资料要求',
    result: '数字审核结论', counted: '逐件标记并比较订单', request: '照片不足，提出资料要求',
    part: '当前标记类别', bolt: '螺纹件', nut: '螺母', washer: '垫圈', bracket: '角码',
    undo: '撤销最后一点', clear: '清除标记', remove: '移除此标记', mark: '在照片上标记物体',
    points: '已标记', quantity: '复核', required: '订单', ai: 'AI 原观察', difference: '复核差额',
    reviewer: '审查人代号', note: '判断依据／需要补充什么资料',
    noteHint: '说明标记、与 AI 的分歧，以及如何处理已有意见。资料不足时写明需要的照片或规格。',
    purpose: '记录用途', personal_review: '本人审查记录', engineering_rehearsal: '功能演练记录',
    scope: '我已查看当前检查范围。确定数量时已逐件标记所有可见目标；看不清时选择补资料。',
    confirm: '我理解这只是照片资料审核，不批准实物出库。', save: '保存审核结论',
    saved: '审核结论已保存，AI 原判断和历史意见保持可查。',
    boundary: '标记是审查人的声明，系统不验证标记是否正确。此结论不计为 AI 准确率或用户试验成绩。',
    nextMatched: '当前资料已复核，可导出审核证据。改版或新增意见后须重新审查。',
    nextMismatch: '差异已记录。核实订单要求或取得更多资料后，再决定下一步。',
    nextEvidence: '资料要求已记录；收到其他照片时，请建立新的资料工单。',
    history: '审核结论历史', current: '当前结论', expired: '历史结论 · 当前不适用',
    opinions: '本次已查看的审查意见', noOpinions: '当前暂无审查意见',
    noCheck: '先完成当前照片的 AI 核验，再进行逐件复核。',
    accessible: '键盘标记：坐标为照片宽高的千分比', add: '添加坐标标记', max: '最多标记100件',
  },
  ko: {
    title: '항목별 확인과 검토 결론', start: '사진에서 항목별 확인', edit: '검토 결론 다시 작성',
    lead: '종류를 고른 뒤 사진의 물체를 하나씩 클릭하세요. 표시에서 수량을 합산하며 AI 관찰은 따로 보존합니다.',
    matched: '검토 수량 일치', mismatch: '검토 수량 차이 발견', needs_more_evidence: '추가 자료 요청 기록됨',
    result: '디지털 검토 결론', counted: '항목 표시 후 주문 비교', request: '사진 부족 · 추가 자료 요청',
    part: '표시할 종류', bolt: '나사류', nut: '너트', washer: '와셔', bracket: '브래킷',
    undo: '마지막 표시 취소', clear: '표시 지우기', remove: '이 표시 삭제', mark: '사진에서 물체 표시',
    points: '표시한 물체', quantity: '검토', required: '주문', ai: 'AI 원관찰', difference: '검토 차이',
    reviewer: '검토자 코드', note: '판단 근거 / 추가로 필요한 자료',
    noteHint: '표시 근거, AI와의 차이, 기존 의견의 처리 내용을 설명하세요. 사진이 부족하면 필요한 자료를 명시하세요.',
    purpose: '기록 용도', personal_review: '본인 검토 기록', engineering_rehearsal: '기능 리허설 기록',
    scope: '현재 검사 범위를 확인했습니다. 확정 수량은 보이는 대상을 모두 표시하며, 불명확하면 추가 자료를 요청합니다.',
    confirm: '사진 자료 검토이며 실물 출고를 승인하지 않음을 확인합니다.', save: '검토 결론 저장',
    saved: '검토 결론을 저장했습니다. AI 판단과 이전 의견은 보존됩니다.',
    boundary: '표시는 검토자의 진술이며 시스템이 정답을 보증하지 않습니다. AI 정확도나 사용자 시험 성과로 집계하지 않습니다.',
    nextMatched: '현재 자료 검토를 마쳤습니다. 증거를 내려받을 수 있으며, 주문이나 의견이 바뀌면 다시 검토하세요.',
    nextMismatch: '차이를 기록했습니다. 주문 요구사항을 확인하거나 추가 자료를 받은 뒤 다음 단계를 결정하세요.',
    nextEvidence: '필요한 자료를 기록했습니다. 다른 사진은 새 자료 주문으로 등록하세요.',
    history: '검토 결론 이력', current: '현재 결론', expired: '이전 결론 · 현재 적용 안 됨',
    opinions: '이번에 확인할 검토 의견', noOpinions: '현재 검토 의견 없음',
    noCheck: '현재 사진의 AI 검사를 먼저 마친 뒤 항목을 확인하세요.',
    accessible: '키보드 표시: 좌표는 사진 너비·높이의 천분율', add: '좌표 표시 추가', max: '최대 100개까지 표시할 수 있습니다',
  },
};
const resolutionDraft = { orderId: null, request: null, points: [], part: 'bolt', summary: null };
function rsText(key) { return RESOLUTION_TEXT[state.lang]?.[key] || RESOLUTION_TEXT.ko[key] || key; }
function activeResolution(order = state.order) {
  if (!digitalOnlyOrder(order)) return null;
  if (order.id === state.order?.id) {
    if (selectedPhoto()?.id !== latestPhoto(order)?.id) return null;
    return publicReviewCache.key === publicReviewKey(order) && !publicReviewCache.error
      ? publicReviewCache.summary?.resolution?.current || null : null;
  }
  return order.digital_resolution_current || null;
}
function resolutionCounts(points) { return Object.fromEntries(PARTS.map(part => [part, points.filter(p => p.part === part).length])); }
function resolutionTable(counts, check, requirements) {
  return `<table class="resolution-table"><thead><tr><th>${esc(rsText('part'))}</th><th>${esc(rsText('required'))}</th><th>${esc(rsText('ai'))}</th><th>${esc(rsText('quantity'))}</th><th>${esc(rsText('difference'))}</th></tr></thead><tbody>${PARTS.map(p => {
    const d = counts ? counts[p] - requirements[p] : null;
    return `<tr><th>${esc(rsText(p))}</th><td>${requirements[p]}</td><td>${check?.observed?.[p] ?? '—'}</td><td><b>${counts?.[p] ?? '—'}</b></td><td class="${d ? 'resolution-difference' : ''}">${d === null ? '—' : d > 0 ? `+${d}` : d}</td></tr>`;
  }).join('')}</tbody></table>`;
}
function renderResolutionAction(order) {
  const r = activeResolution(order); if (!r) return '';
  return `<section class="panel action-panel ${r.outcome === 'matched' ? 'action-ready' : 'action-warning'}" aria-live="polite"><p class="action-label">${icon('check')}${esc(rsText('result'))}</p><h3>${esc(rsText(r.outcome))}</h3><p>${esc(rsText(r.outcome === 'matched' ? 'nextMatched' : r.outcome === 'mismatch' ? 'nextMismatch' : 'nextEvidence'))}</p><p class="digital-original-decision">${esc(prText('resultLabel'))} · ${esc(prText(r.check_snapshot.decision))}</p><p class="resolution-purpose">${esc(rsText(r.purpose))} · ${esc(r.operator_code)}</p><p class="public-review-note">${esc(r.note)}</p><a class="btn btn-primary btn-full" href="/api/orders/${encodeURIComponent(order.id)}/evidence.zip" download>${icon('download')}${state.lang === 'zh' ? '导出审核证据' : '검토 증거 내려받기'}</a></section>`;
}
function renderResolutionPanel(order, summary, disabled) {
  const current = summary?.resolution?.current;
  const history = summary?.resolution?.history || [];
  return `<div class="resolution-panel"><h3>${esc(rsText('title'))}</h3><p>${esc(rsText('lead'))}</p>${current ? resolutionTable(current.reviewed_counts, current.check_snapshot, current.requirements_snapshot) : ''}<button class="btn btn-primary btn-full" data-action="digital-resolve" ${disabled || !summary?.can_review ? 'disabled' : ''}>${icon('edit')}${esc(rsText(current ? 'edit' : 'start'))}</button>${!summary?.can_review ? `<small>${esc(rsText('noCheck'))}</small>` : ''}${history.length ? `<details class="resolution-history"><summary>${esc(rsText('history'))} · ${history.length}</summary>${[...history].reverse().map(({receipt:r, current:linked}) => `<article><strong>${esc(rsText(r.outcome))}</strong><p>R${r.expected_revision} · ${esc(rsText(linked ? 'current' : 'expired'))}</p><small>${esc(r.operator_code)} · ${esc(rsText(r.purpose))} · ${esc(formatDate(r.created_at))}</small><p class="public-review-note">${esc(r.note)}</p></article>`).join('')}</details>` : ''}</div>`;
}
function redrawResolutionPoints() {
  const form = document.getElementById('digital-resolution-form'); if (!form) return;
  const counted = form.elements.assessment.value === 'counted';
  form.querySelector('.resolution-marking').hidden = !counted;
  const points = resolutionDraft.points;
  form.querySelector('.resolution-points').innerHTML = points.map((p,i) => `<button type="button" class="resolution-point part-${p.part}" style="left:${p.x/10}%;top:${p.y/10}%" data-resolution-remove="${i}" title="${esc(rsText('remove'))} ${i+1} ${esc(rsText(p.part))}" aria-label="${esc(rsText('remove'))} ${i+1} ${esc(rsText(p.part))}">${i+1}</button>`).join('');
  form.querySelector('.resolution-counts').innerHTML = resolutionTable(counted ? resolutionCounts(points) : null, resolutionDraft.summary.check, state.order.requirements);
  form.querySelector('.resolution-point-list').innerHTML = points.map((p,i) => `<span>${i+1} ${esc(rsText(p.part))}</span>`).join('') || '0';
}
function addResolutionPoint(x,y) {
  if (state.busy || !resolutionDraft.request) return;
  if (resolutionDraft.points.length >= 100) { toast(rsText('max')); return; }
  x = Math.max(0,Math.min(1000,Math.round(x))); y = Math.max(0,Math.min(1000,Math.round(y)));
  if (resolutionDraft.points.some(p => p.x === x && p.y === y)) return;
  resolutionDraft.points.push({part: resolutionDraft.part, x, y}); redrawResolutionPoints();
}
async function openResolutionDialog() {
  if (state.busy || !digitalOnlyOrder(state.order) || selectedPhoto()?.id !== latestPhoto()?.id) return;
  const orderId = state.order.id;
  try {
    const summary = await api(`/api/orders/${encodeURIComponent(orderId)}/public-review-summary`);
    if (state.order?.id !== orderId || state.busy) return;
    if (!summary.can_review || !summary.resolution?.request) { toast(rsText('noCheck')); return; }
    Object.assign(resolutionDraft, { orderId, request: summary.resolution.request, points: [], part: 'bolt', summary });
    const opinions = summary.reviews.filter(r => r.current);
    openModal('digital-resolution-dialog', `<div class="modal-header"><div><p class="eyebrow">R${state.order.revision} · KITGUARD REVIEW</p><h2>${esc(rsText('title'))}</h2><p>${esc(rsText('lead'))}</p></div><button type="button" class="icon-btn" data-action="close-modal" aria-label="${esc(t('close'))}">${icon('close')}</button></div><form id="digital-resolution-form" data-key="${crypto.randomUUID()}"><div class="modal-content resolution-layout"><div class="resolution-photo-column"><label class="field"><span>${esc(rsText('result'))}</span><select name="assessment"><option value="counted">${esc(rsText('counted'))}</option><option value="needs_more_evidence">${esc(rsText('request'))}</option></select></label><div class="resolution-marking"><div class="resolution-toolbar"><label>${esc(rsText('part'))}<select name="part">${PARTS.map(p=>`<option value="${p}">${esc(rsText(p))}</option>`).join('')}</select></label><button type="button" class="btn btn-quiet" data-action="resolution-undo">${esc(rsText('undo'))}</button><button type="button" class="btn btn-quiet" data-action="resolution-clear">${esc(rsText('clear'))}</button></div><div class="resolution-stage" role="group" aria-label="${esc(rsText('mark'))}"><img src="${esc(imageUrl(latestPhoto()))}" alt="${esc(rsText('mark'))}" draggable="false"><div class="resolution-points"></div></div><div class="resolution-point-list" aria-live="polite"></div><details><summary>${esc(rsText('accessible'))}</summary><div class="resolution-coordinates"><label>X<input type="number" name="point_x" min="0" max="1000" value="500"></label><label>Y<input type="number" name="point_y" min="0" max="1000" value="500"></label><button type="button" class="btn btn-secondary" data-action="resolution-add-coordinate">${esc(rsText('add'))}</button></div></details></div><div class="resolution-counts"></div></div><div class="resolution-form-column"><label class="field"><span>${esc(rsText('reviewer'))}</span><input name="operator_code" required maxlength="80" autocomplete="off"></label><label class="field"><span>${esc(rsText('purpose'))}</span><select name="purpose"><option value="personal_review">${esc(rsText('personal_review'))}</option><option value="engineering_rehearsal">${esc(rsText('engineering_rehearsal'))}</option></select></label><details class="resolution-opinions" ${opinions.length ? 'open' : ''}><summary>${esc(rsText('opinions'))} · ${opinions.length}</summary>${opinions.map(({receipt:r})=>`<article><strong>${esc(prText(r.conclusion))}</strong><p>${esc(r.operator_code)} · ${esc(r.note)}</p></article>`).join('') || `<p>${esc(rsText('noOpinions'))}</p>`}</details><label class="field"><span>${esc(rsText('note'))}</span><textarea name="note" required maxlength="2000" rows="4" placeholder="${esc(rsText('noteHint'))}"></textarea></label><label class="confirm-box"><input name="confirmed_scope" type="checkbox" required><span>${esc(rsText('scope'))}</span></label><label class="confirm-box"><input name="confirmed_digital_only" type="checkbox" required><span>${esc(rsText('confirm'))}</span></label><p class="resolution-boundary">${esc(rsText('boundary'))}</p><div class="modal-error" role="alert"></div></div></div><div class="modal-footer"><button type="button" class="btn btn-quiet" data-action="close-modal">${esc(t('cancel'))}</button><button type="submit" class="btn btn-primary" data-mutate>${esc(rsText('save'))}</button></div></form>`);
    redrawResolutionPoints();
  } catch(error) { showError(error); }
}
document.addEventListener('click', event => {
  const button = event.target.closest('[data-action]');
  if (button && !button.disabled && button.dataset.action === 'digital-resolve') openResolutionDialog();
  const form = event.target.closest('#digital-resolution-form'); if (!form || state.busy) return;
  const remove = event.target.closest('[data-resolution-remove]');
  if (remove) { resolutionDraft.points.splice(Number(remove.dataset.resolutionRemove), 1); redrawResolutionPoints(); return; }
  const stage = event.target.closest('.resolution-stage');
  if (stage) { const r = stage.getBoundingClientRect(); addResolutionPoint((event.clientX-r.left)/r.width*1000, (event.clientY-r.top)/r.height*1000); }
  if (button?.dataset.action === 'resolution-undo') { resolutionDraft.points.pop(); redrawResolutionPoints(); }
  if (button?.dataset.action === 'resolution-clear') { resolutionDraft.points = []; redrawResolutionPoints(); }
  if (button?.dataset.action === 'resolution-add-coordinate') {
    const x = form.elements.point_x.valueAsNumber, y = form.elements.point_y.valueAsNumber;
    if (Number.isInteger(x) && Number.isInteger(y) && x>=0 && x<=1000 && y>=0 && y<=1000) addResolutionPoint(x,y);
  }
});
document.addEventListener('change', event => {
  if (!event.target.closest('#digital-resolution-form')) return;
  if (event.target.name === 'part') resolutionDraft.part = event.target.value;
  if (event.target.name === 'assessment') redrawResolutionPoints();
});
document.addEventListener('submit', async event => {
  const form = event.target; if (form.id !== 'digital-resolution-form') return;
  event.preventDefault();
  if (state.busy || resolutionDraft.orderId !== state.order?.id || !resolutionDraft.request) return;
  const payload = {...resolutionDraft.request, operator_code: form.elements.operator_code.value.trim(),
    purpose: form.elements.purpose.value, assessment: form.elements.assessment.value,
    points: form.elements.assessment.value === 'counted' ? resolutionDraft.points.map(p=>({...p})) : [],
    note: form.elements.note.value.trim(), confirmed_scope: form.elements.confirmed_scope.checked,
    confirmed_digital_only: form.elements.confirmed_digital_only.checked, idempotency_key: form.dataset.key};
  const result = await mutate('digital-resolution', () => post(`/api/orders/${encodeURIComponent(resolutionDraft.orderId)}/digital-resolution`, payload), null, 'digital-resolution-dialog');
  if (result) { document.getElementById('digital-resolution-dialog').close(); resolutionDraft.request = null; await refreshPublicReview(true); toast(rsText('saved')); }
});
