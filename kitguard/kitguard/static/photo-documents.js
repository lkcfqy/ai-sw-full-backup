/* User-declared local photographs. Source statements are never verified here. */
'use strict';
const PHOTO_DOCUMENT_TEXT = {
  ko: {
    create: '내 사진으로 자료 주문', title: '사진 자료 주문 만들기', description: '사진 한 장과 비교할 주문 수량을 등록합니다. 검사·검토·주문 변경·증거 저장은 기존 작업대에서 이어갑니다.',
    photo: '로컬 사진 한 장', source: '사진 출처 설명', sourceHint: '예: 직접 촬영한 사진, 보유 자료의 이름과 촬영자, 공개 자료를 받은 곳',
    url: '출처 URL · 선택', license: '이용 조건 설명 · 선택', optionalHint: 'URL에서 사진을 가져오지 않습니다. 기기의 파일을 선택하세요.',
    confirm: '디지털 자료만 검토합니다. 출처·이용 조건은 내 진술로 남으며, 이 주문은 실물 완료를 기록하지 않습니다.',
    unverified: '사용자 진술 · 출처 미검증', document: '사진 자료 주문', boundary: '사진과 출처 진술을 함께 고정합니다. 다른 사진은 새 자료 주문으로 등록하세요.',
    details: '등록한 출처와 사진 연결', noteMissing: '사진 출처 설명을 입력하세요.', confirmMissing: '디지털 자료 검토 범위를 확인하세요.', urlInvalid: '출처 URL은 http 또는 https 주소를 입력하세요.',
    declaredAt: '진술 등록 시각', root: '고정 원본 사진 ID', rawHash: '원래 업로드 SHA-256', storedHash: '저장 사진 SHA-256', statementHash: '출처 진술 SHA-256', bindingHash: '사진·진술 연결 SHA-256',
    success: '사진 자료 주문을 만들었습니다. 이제 사진 검사를 실행하세요.', another: '다른 사진으로 새 주문', absent: '미입력',
  },
  zh: {
    create: '用自己的照片建资料工单', title: '新建照片资料工单', description: '登记一张照片和要比较的订单数量，然后在现有工作台继续核验、审查、改版和保存证据。',
    photo: '一张本地照片', source: '照片来源说明', sourceHint: '例如：自己拍摄的照片、已有资料名称及拍摄者、获取公开资料的位置',
    url: '来源网址 · 选填', license: '使用条件说明 · 选填', optionalHint: '不会从网址下载照片，请选择本机文件。',
    confirm: '仅审查数字资料。来源与使用条件为本人自报，尚未核实；此工单不记录实物完工。',
    unverified: '用户自报 · 来源未核实', document: '照片资料工单', boundary: '照片与来源声明一并锁定。使用其他照片时，请另建资料工单。',
    details: '登记的来源与照片关联', noteMissing: '请填写照片来源说明。', confirmMissing: '请确认数字资料审查范围。', urlInvalid: '来源网址必须使用 http 或 https。',
    declaredAt: '声明登记时间', root: '固定根照片 ID', rawHash: '原始上传 SHA-256', storedHash: '存储照片 SHA-256', statementHash: '来源声明 SHA-256', bindingHash: '照片与声明关联 SHA-256',
    success: '照片资料工单已建立，现在可以运行照片核验。', another: '用其他照片另建工单', absent: '未填写',
  },
};
function pdText(key) { return PHOTO_DOCUMENT_TEXT[state.lang]?.[key] || PHOTO_DOCUMENT_TEXT.ko[key] || key; }
function safeSourceUrl(value) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password && !/[\\\x00-\x20\x7f]/.test(value) ? url.href : null; } catch { return null; }
}
function renderDocumentSource(order, readonly = false) {
  if (!order || !Object.prototype.hasOwnProperty.call(order, 'document_source')) return '';
  const source = order.document_source || {};
  const rows = [['source', source.source_note], ['url', source.source_url], ['license', source.license_note],
    ['declaredAt', source.declared_at], ['root', source.original_root_photo_id], ['rawHash', source.source_sha256],
    ['storedHash', source.storage_sha256], ['statementHash', source.statement_sha256], ['bindingHash', source.binding_sha256]];
  return `<section class="photo-document-source" data-source-verification="user_declared_unverified"><div><strong>${esc(pdText('document'))}</strong><span class="badge invalid">${esc(pdText('unverified'))}</span></div><p>${esc(pdText('boundary'))}</p><details><summary>${esc(pdText('details'))}</summary><dl>${rows.map(([key, value]) => `<div><dt>${esc(pdText(key))}</dt><dd>${key === 'url' && safeSourceUrl(value) ? `<a href="${esc(safeSourceUrl(value))}" target="_blank" rel="noopener noreferrer">${esc(value)}</a>` : esc(value || pdText('absent'))}</dd></div>`).join('')}</dl></details>${readonly ? '' : `<button class="btn btn-quiet btn-sm" data-action="new-photo-document" ${state.busy ? 'disabled' : ''}>${esc(pdText('another'))}</button>`}</section>`;
}
function renderSourceNotice(order) {
  if (order && Object.prototype.hasOwnProperty.call(order, 'document_source')) return renderDocumentSource(order);
  if (!order?.demo_source) return '';
  const source = order.demo_source, url = safeSourceUrl(source.source_url);
  return `<div class="notice-banner">${icon('info')}<span>${state.lang === 'zh' ? '公开照片演示：核验调用真实本地模型，但不能记录实物完工。' : '공개 사진 데모: 실제 로컬 모델로 검사하지만 실물 완료는 기록할 수 없습니다.'} ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(source.license)}</a>` : esc(source.license || '')}</span></div>`;
}
function openPhotoDocument() {
  if (state.busy) return;
  openModal('photo-document-dialog', `<div class="modal-header"><div><h2>${esc(pdText('title'))}</h2><p>${esc(pdText('description'))}</p></div><button class="icon-btn" type="button" data-action="close-modal" aria-label="${esc(t('close'))}">${icon('close')}</button></div><form id="photo-document-form"><div class="modal-content"><label class="field"><span>${esc(t('orderTitle'))}</span><input name="title" maxlength="100" required value="${esc(pdText('document'))}"></label><label class="field"><span>${esc(pdText('photo'))}</span><input type="file" name="photo" required accept="image/jpeg,image/png,image/webp"></label><p class="field-label">${esc(t('quantityLabel'))}</p>${quantitiesMarkup(DEFAULT_REQUIREMENTS)}<label class="field"><span>${esc(pdText('source'))}</span><textarea name="source_note" required maxlength="2000" rows="3" placeholder="${esc(pdText('sourceHint'))}"></textarea></label><label class="field"><span>${esc(pdText('url'))}</span><input type="url" name="source_url" maxlength="2048" placeholder="https://" autocomplete="off"></label><p class="form-note">${esc(pdText('optionalHint'))}</p><label class="field"><span>${esc(pdText('license'))}</span><textarea name="license_note" maxlength="500" rows="2"></textarea></label><label class="confirm-box"><input name="confirmed_digital_only" type="checkbox" required><span>${esc(pdText('confirm'))}</span></label><div class="modal-error" role="alert"></div></div><div class="modal-footer"><button type="button" class="btn btn-quiet" data-action="close-modal">${esc(t('cancel'))}</button><button class="btn btn-primary" type="submit" data-mutate>${esc(pdText('title'))}</button></div></form>`);
}
function photoDocumentSubmission(form) {
  const field = name => form.elements.namedItem(name);
  const photo = field('photo').files?.[0]; validateFile(photo);
  const title = field('title').value.trim(), source_note = field('source_note').value.trim();
  if (!title) throw new Error(t('invalidTitle'));
  if (!source_note) throw new Error(pdText('noteMissing'));
  if (!field('confirmed_digital_only').checked) throw new Error(pdText('confirmMissing'));
  const source_url = field('source_url').value.trim() || null, license_note = field('license_note').value.trim() || null;
  if (source_url && !safeSourceUrl(source_url)) throw new Error(pdText('urlInvalid'));
  return { photo, metadata: { title, requirements: getRequirements(form), source_note, source_url, license_note, confirmed_digital_only: true } };
}
async function submitPhotoDocument(form) {
  if (state.busy) return;
  let submission;
  try { submission = photoDocumentSubmission(form); } catch (error) { modalError('photo-document-dialog', error.message); return; }
  const body = new FormData(); body.append('photo', submission.photo); body.append('metadata', JSON.stringify(submission.metadata));
  const result = await mutate('photo-document', () => post('/api/photo-documents', body), null, 'photo-document-dialog');
  if (result) { state.sidebarOpen = false; document.getElementById('photo-document-dialog').close(); render(); toast(pdText('success')); }
}
document.addEventListener('click', event => {
  const button = event.target.closest('[data-action]');
  if (button && !button.disabled && button.dataset.action === 'new-photo-document') openPhotoDocument();
});
document.addEventListener('submit', event => {
  if (event.target.id === 'photo-document-form') { event.preventDefault(); submitPhotoDocument(event.target); }
});
