/* Optional, read-only model object evidence. No inference or completion logic. */
'use strict';

const SPATIAL_STRINGS = {
  ko: {
    show: '물체 번호 표시', hide: '물체 번호 숨기기', estimated: '모델 추정 위치',
    list: '저장된 물체 목록 · {count}개', item: '번호', position: '사진 내 위치',
    note: '위치는 모델이 추정한 값입니다. 수량은 저장된 목록에서 프로그램이 계산하며, 물체의 중복·누락이나 분류 오류가 남을 수 있습니다. 위치 표시는 실제 물체의 상태나 작업 수행을 증명하지 않습니다.',
    frame: '사진의 왼쪽 위가 (0%, 0%)입니다. 번호는 저장된 목록 순서이며 실제 트레이 번호가 아닙니다.',
    uncertain: '수량 미확인 종류', none: '없음', empty: '모델이 목록에 기록한 물체가 없습니다.',
    test: '엔지니어링 테스트', stored: '저장된 R{revision} 관찰', noCountClaim: '목록의 항목 수이며 확정된 실물 수량이 아닙니다.'
  },
  zh: {
    show: '显示物体编号', hide: '隐藏物体编号', estimated: '模型估计位置',
    list: '已保存的物体清单 · {count} 项', item: '编号', position: '照片内位置',
    note: '位置由模型估计。数量由程序根据保存的清单计算，仍可能存在重复、遗漏或分类错误。位置标记不能证明物体的实际状态或物料操作已经发生。',
    frame: '照片左上角为 (0%, 0%)。编号只表示保存的清单顺序，不是真实托盘编号。',
    uncertain: '数量仍不明确的类别', none: '无', empty: '模型没有在清单中记录物体。',
    test: '工程测试', stored: '已保存的 R{revision} 观察', noCountClaim: '这是清单项数，不是已经确认的实物数量。'
  }
};

function spatialText(key, values = {}) {
  let value = SPATIAL_STRINGS[state.lang]?.[key] || SPATIAL_STRINGS.ko[key] || key;
  for (const [name, replacement] of Object.entries(values)) value = value.replaceAll(`{${name}}`, String(replacement));
  return value;
}

function spatialEvidence(check, photo) {
  if (!check || !photo || check.photo_id !== photo.id) return null;
  if (check.photo_sha256 && photo.sha256 && check.photo_sha256 !== photo.sha256) return null;
  const evidence = check.object_evidence;
  if (!evidence || evidence.protocol !== 'spatial_inventory_v1' || evidence.coordinate_frame !== 'normalized_original') return null;
  if (!Array.isArray(evidence.objects) || evidence.objects.length > 20 || !Array.isArray(evidence.uncertain_parts)) return null;
  if (evidence.uncertain_parts.length > 4 || new Set(evidence.uncertain_parts).size !== evidence.uncertain_parts.length || evidence.uncertain_parts.some(part => !PARTS.includes(part))) return null;
  // Reject the whole malformed list. Silently dropping entries could imply a complete inventory.
  if (evidence.objects.some(item => !item || !PARTS.includes(item.part) || !Array.isArray(item.center) || item.center.length !== 2 || item.center.some(value => typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 1))) return null;
  return evidence;
}

function spatialPhotoCheck(order, photo) {
  if (!photo) return null;
  const candidates = [order.latest_check, ...[...(order.checks || [])].reverse()];
  return candidates.find(check => spatialEvidence(check, photo)) || null;
}

function spatialBinding(check, photo) { return `${check.id || ''}:${photo.id}`; }

function spatialOverlayMarkup(check, photo, scope) {
  const evidence = spatialEvidence(check, photo);
  if (!evidence) return '';
  return `<div class="spatial-overlay" id="${scope}-spatial-overlay" data-spatial-binding="${esc(spatialBinding(check, photo))}" aria-hidden="true" hidden>${evidence.objects.map((item, index) => `<span class="spatial-point" style="left:${item.center[0] * 100}%;top:${item.center[1] * 100}%" title="${esc(`${index + 1} · ${partLabel(item.part)}`)}">${index + 1}</span>`).join('')}</div>`;
}

function spatialControlsMarkup(check, photo, scope) {
  const evidence = spatialEvidence(check, photo);
  if (!evidence) return '';
  return `<div class="spatial-controls ${scope === 'workspace' ? 'spatial-controls-compact' : ''}"><div class="spatial-toolbar"><button class="btn btn-secondary btn-sm" type="button" data-action="spatial-toggle" data-spatial-binding="${esc(spatialBinding(check, photo))}" aria-controls="${scope}-spatial-overlay" aria-pressed="false" ${evidence.objects.length ? '' : 'disabled'}>${icon('scan')}<span>${esc(spatialText('show'))}</span></button><span class="spatial-estimate-label">${esc(spatialText('estimated'))} · ${esc(spatialText('stored', { revision: check.revision }))}</span>${check.backend === 'test' ? `<span class="spatial-test-label">${esc(spatialText('test'))}</span>` : ''}</div><details class="spatial-inventory"><summary>${esc(spatialText('list', { count: evidence.objects.length }))}</summary><p class="spatial-evidence-note">${esc(spatialText('note'))}</p><p>${esc(spatialText('frame'))}</p><p class="spatial-uncertain"><strong>${esc(spatialText('uncertain'))}:</strong> ${esc(evidence.uncertain_parts.length ? evidence.uncertain_parts.map(partLabel).join(' · ') : spatialText('none'))}</p>${evidence.objects.length ? `<div class="spatial-list-scroll"><table class="spatial-table"><caption>${esc(spatialText('noCountClaim'))}</caption><thead><tr><th scope="col">${esc(spatialText('item'))}</th><th scope="col">${esc(t('part'))}</th><th scope="col">${esc(spatialText('position'))}</th></tr></thead><tbody>${evidence.objects.map((item, index) => `<tr data-spatial-index="${index + 1}"><th scope="row">${index + 1}</th><td>${esc(partLabel(item.part))}</td><td>x ${(item.center[0] * 100).toFixed(1)}% · y ${(item.center[1] * 100).toFixed(1)}%</td></tr>`).join('')}</tbody></table></div>` : `<p>${esc(spatialText('empty'))}</p>`}</details></div>`;
}

function spatialToggle(button) {
  const scope = button.closest('[data-spatial-scope]');
  const overlay = scope?.querySelector('.spatial-overlay');
  if (!overlay || overlay.dataset.spatialBinding !== button.dataset.spatialBinding) return;
  const visible = button.getAttribute('aria-pressed') !== 'true';
  overlay.hidden = !visible;
  button.setAttribute('aria-pressed', String(visible));
  button.querySelector('span').textContent = spatialText(visible ? 'hide' : 'show');
  // No persistent visibility state: changing a photo/check always renders fresh, hidden markers.
}
