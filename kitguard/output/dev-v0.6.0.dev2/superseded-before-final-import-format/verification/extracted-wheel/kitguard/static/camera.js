/* On-device capture and review. Uploads use the existing versioned evidence API. */
'use strict';
const CAPTURE_TEXT = {
  ko: {
    title: '새 실물 증거 촬영', referenceTitle: '기준 부품 한 개 촬영',
    description: '촬영 → 사진 확인 → 저장. 확인 전에는 사진을 보내지 않습니다.',
    purpose: '검사 사진', reference: '{part} 기준 사진', bound: '{title} · R{revision}',
    starting: '카메라 권한과 영상을 기다리고 있습니다.', live: '실시간 미리보기 · 아직 저장되지 않음', review: '저장 전 사진 확인', paused: '미리보기가 중단되었습니다. 다시 열면 촬영을 계속할 수 있습니다.',
    privacy: '부품만 촬영하세요. 얼굴·신분증·화면·개인 문서는 프레임에서 빼세요. 마이크는 사용하지 않으며, 미리보기 영상은 서버로 보내지 않습니다.',
    guide: '촬영 전에 확인', whole: '모든 부품과 트레이 가장자리가 프레임 안에 보이게 하세요.', separate: '부품을 겹치지 않게 한 칸에 하나씩 놓으세요. 인쇄 트레이 없이도 사용 가능합니다.', clear: '카메라를 고정하고 빛 반사·그림자를 피하세요. 나사 머리, 구멍과 윤곽이 구분되는지 직접 확인하세요.', scope: '볼트·너트·와셔·L형 브래킷 4종만 다룹니다. 종류별 0–3개, 합계 1–12개 주문이며 규격·재질을 인증하지 않습니다.', single: '선택한 종류의 기준 부품 한 개만 크게 촬영하세요. 다른 종류나 손은 프레임에서 빼세요.',
    capture: '사진 찍기', retake: '다시 촬영', use: '이 사진을 R{revision}에 저장', useReference: '이 기준 사진 저장', saving: '사진을 저장하는 중…', native: '기기 카메라 / 사진 선택', switch: '카메라 전환', resume: '카메라 다시 열기', dimensions: '{width} × {height}px · {size} MB',
    reviewNote: '잘린 부품, 겹침, 흐림, 반사와 불필요한 개인정보를 확인하세요. 이 화면은 자동 품질 판정이나 수량 확인이 아닙니다.', evidenceNote: '사진 저장 후 별도로 검증을 실행해야 합니다. 촬영은 작업 완료나 실제 보충의 증명이 아닙니다.', referenceNote: '새 기준 사진을 저장하면 이전 검증이 무효화됩니다. 수량은 검사 사진에서만 셉니다.',
    phoneNote: '현재 앱은 이 컴퓨터의 localhost에서 실행됩니다. 다른 휴대전화에서는 기기 카메라로 새 사진을 찍어 AirDrop·케이블 등으로 이 컴퓨터에 옮긴 뒤 선택하세요. 휴대전화의 localhost는 이 컴퓨터가 아닙니다.',
    denied: '카메라 권한이 거부되었습니다. 브라우저 사이트 설정에서 권한을 허용하거나 기기 카메라 / 사진 선택을 사용하세요.', missing: '사용 가능한 카메라를 찾지 못했습니다. 외부 카메라를 연결하거나 새로 촬영한 사진을 선택하세요.', busy: '다른 앱이 카메라를 사용하거나 기기를 시작할 수 없습니다. 카메라 사용 앱을 닫고 다시 시도하세요.', unsupported: '이 브라우저에서 실시간 카메라를 사용할 수 없습니다. localhost 또는 지원되는 보안 연결에서 열거나 기기 카메라 / 사진 선택을 사용하세요.', failed: '카메라 영상을 열지 못했습니다. 다시 시도하거나 새로 촬영한 사진을 선택하세요.',
    stopped: '카메라 연결이 종료되었습니다. 다시 열거나 사진을 선택하세요.', invalid: 'JPG, PNG 또는 WEBP 사진을 선택하세요(12 MB 이하). HEIC는 JPG로 내보낸 뒤 선택하세요.', invalidDimensions: '사진 크기가 지원 범위를 벗어났습니다(양쪽 32px 이상, 최대 8192px·1600만 화소).', stale: '촬영을 시작한 뒤 작업지시가 변경되었습니다. 이 사진을 새 버전에 자동 연결하지 않습니다. 창을 닫고 현재 주문에서 다시 촬영하세요.', processing: '이 기기에서 사진을 준비하는 중입니다.', loadingFailed: '사진을 읽지 못했습니다. 다시 촬영하거나 다른 지원 형식을 선택하세요.', captureUnavailable: '카메라 영상이 아직 준비되지 않았습니다.', discard: '취소하면 아직 저장하지 않은 사진이 폐기됩니다.',
  },
  zh: {
    title: '拍摄新的实物证据', referenceTitle: '拍摄单件参考零件',
    description: '拍摄 → 复核照片 → 保存。确认保存前不会上传。',
    purpose: '待检照片', reference: '{part}参考照片', bound: '{title} · R{revision}',
    starting: '正在等待相机权限和画面。', live: '实时预览 · 尚未保存', review: '保存前复核照片', paused: '预览已暂停。重新打开相机后可继续拍摄。',
    privacy: '只拍零件，将人脸、证件、屏幕和私人文件移出画面。不使用麦克风，预览视频不会发送到服务器。',
    guide: '拍摄前检查', whole: '让全部零件和托盘边缘完整入镜。', separate: '将零件分开放置，每格一件、避免重叠；没有打印托盘也能拍摄。', clear: '保持相机稳定，避开反光和阴影。自行查看螺栓头、孔洞与轮廓是否清楚。', scope: '仅处理螺栓、螺母、垫圈和 L 形角码四类。工单每类 0–3 件、合计 1–12 件，不认证规格或材质。', single: '仅将所选类别的一件参考零件清楚放大入镜，移开其他类别和手。',
    capture: '拍摄照片', retake: '重新拍摄', use: '将此照片保存到 R{revision}', useReference: '保存此参考照片', saving: '正在保存照片…', native: '设备拍摄 / 选择照片', switch: '切换镜头', resume: '重新打开相机', dimensions: '{width} × {height}px · {size} MB',
    reviewNote: '检查是否裁掉零件、存在重叠、模糊、反光或无关个人信息。本页不自动判定照片质量，也不确认零件数量。', evidenceNote: '保存照片后仍须另行运行核验。拍照不代表完成工单，也不能证明实际补件已经发生。', referenceNote: '保存新参考照片会使旧核验失效。仅从待检照片中计数。',
    phoneNote: '当前工作台只在这台电脑的 localhost 运行。另一部手机可先拍摄新照片，再通过 AirDrop、数据线等传到这台电脑后选择；手机的 localhost 不是这台电脑。',
    denied: '相机权限被拒绝。请在浏览器网站设置中允许使用相机，或使用“设备拍摄 / 选择照片”。', missing: '没有找到可用相机。请连接外置摄像头，或选择刚拍摄的照片。', busy: '相机被其他应用占用，或无法启动。请关闭占用相机的应用后重试。', unsupported: '此浏览器无法使用实时相机。请通过 localhost 或受支持的安全连接打开，或使用“设备拍摄 / 选择照片”。', failed: '无法打开相机画面，请重试或选择刚拍摄的照片。',
    stopped: '相机连接已结束。请重新打开相机或选择照片。', invalid: '请选择不超过 12 MB 的 JPG、PNG 或 WEBP。HEIC 请先导出为 JPG。', invalidDimensions: '照片尺寸超出支持范围：两边至少 32px、最长边最多 8192px，且不超过 1600 万像素。', stale: '开始拍摄后工单已经变化。不会自动将这张照片改挂到新版本；请关闭此窗口，在当前工单下重新拍摄。', processing: '正在此设备上准备照片。', loadingFailed: '无法读取照片。请重新拍摄或选择其他支持格式。', captureUnavailable: '相机画面尚未准备好。', discard: '取消会丢弃尚未保存的照片。',
  },
};
let captureSession = null;
let capturePickerSession = null;
function ct(key, values = {}) { let value = CAPTURE_TEXT[state.lang]?.[key] || CAPTURE_TEXT.ko[key] || key; for (const [name, item] of Object.entries(values)) value = value.replaceAll(`{${name}}`, String(item)); return value; }
function captureCanClose() { return captureSession?.phase !== 'saving'; }
function captureActive(session) { return captureSession === session && document.getElementById('camera-dialog').open; }
function captureStopStream(session) { if (!session) return; session.request += 1; const stream = session.stream; if (stream) stream.getTracks().forEach(track => track.stop()); if (state.stream === stream) state.stream = null; session.stream = null; }
function stopCamera() { const session = captureSession; captureSession = null; if (capturePickerSession === session) capturePickerSession = null; captureStopStream(session); if (session?.url) URL.revokeObjectURL(session.url); }
function captureErrorText(error) { return ct(({ NotAllowedError: 'denied', SecurityError: 'denied', NotFoundError: 'missing', DevicesNotFoundError: 'missing', NotReadableError: 'busy', TrackStartError: 'busy', OverconstrainedError: 'failed' })[error?.name] || 'failed'); }
function cameraMarkup(session) {
  const review = session.phase === 'review', pending = ['starting', 'processing', 'saving'].includes(session.phase), live = session.phase === 'live';
  const purpose = session.part ? ct('reference', { part: partLabel(session.part) }) : ct('purpose');
  const mode = review ? 'review' : session.phase === 'starting' ? 'starting' : session.phase === 'processing' ? 'processing' : session.phase === 'saving' ? 'saving' : live ? 'live' : 'paused';
  return `<div class="modal-header"><div><p class="eyebrow">CAPTURE · REVIEW · SAVE</p><h2 id="capture-title">${esc(ct(session.part ? 'referenceTitle' : 'title'))}</h2><p>${esc(ct('description'))}</p></div><button class="icon-btn" type="button" data-action="close-modal" aria-label="${esc(t('close'))}" ${session.phase === 'saving' ? 'disabled' : ''}>${icon('close')}</button></div><div class="modal-content capture-content"><div class="capture-binding"><span class="badge revision">${esc(ct('bound', { title: session.title, revision: session.revision }))}</span><strong>${esc(purpose)}</strong></div><p class="capture-privacy">${icon('lock')}<span>${esc(ct('privacy'))}</span></p><div class="capture-layout"><div class="capture-visual"><div class="capture-frame">${session.file ? `<img id="capture-review" src="${esc(session.url)}" alt="${esc(ct('review'))}">` : `<video id="camera-preview" class="camera-preview" playsinline autoplay muted aria-label="${esc(ct('title'))}"></video>`}<span class="capture-frame-label" aria-live="polite">${esc(ct(mode))}</span></div>${session.file ? `<p class="capture-dimensions">${esc(ct('dimensions', { width: session.width, height: session.height, size: (session.file.size / 1024 / 1024).toFixed(2) }))}</p><p class="capture-review-note">${esc(ct('reviewNote'))}</p>` : `<div class="capture-device-tools"><button type="button" class="btn btn-quiet btn-sm" data-action="capture-switch" ${!live || session.devices.length < 2 ? 'disabled' : ''}>${icon('refresh')}${esc(ct('switch'))}</button><span>${esc(session.deviceLabel || '')}</span></div>`}</div><aside class="capture-guide"><h3>${esc(ct('guide'))}</h3><ol><li>${esc(ct(session.part ? 'single' : 'whole'))}</li><li>${esc(ct('separate'))}</li><li>${esc(ct('clear'))}</li></ol><p>${esc(ct('scope'))}</p>${session.part ? '' : `<a class="audit-inline-link" href="/api/templates/tray.svg" target="_blank" rel="noopener">${icon('grid')}${esc(t('printTray'))}</a>`}</aside></div><p class="capture-evidence-note">${esc(ct(session.part ? 'referenceNote' : 'evidenceNote'))}</p><details class="capture-phone-help"><summary>${esc(ct('native'))}</summary><p>${esc(ct('phoneNote'))}</p></details><div class="modal-error ${session.error ? 'visible' : ''}" role="alert">${esc(session.error || '')}</div><p id="camera-status" class="sr-only" role="status" aria-live="polite">${esc(ct(mode))}</p></div><div class="modal-footer capture-footer"><button class="btn btn-quiet" type="button" data-action="close-modal" title="${esc(ct('discard'))}" ${session.phase === 'saving' ? 'disabled' : ''}>${esc(t('cancel'))}</button><button class="btn btn-secondary" type="button" data-action="capture-native" ${['processing', 'saving'].includes(session.phase) ? 'disabled' : ''}>${icon('upload')}${esc(ct('native'))}</button>${session.file ? `<button class="btn btn-secondary" type="button" data-action="capture-retake" ${pending ? 'disabled' : ''}>${icon('camera')}${esc(ct('retake'))}</button><button class="btn btn-primary" type="button" data-action="capture-save" data-mutate ${pending ? 'disabled' : ''}>${icon('upload')}${esc(session.phase === 'saving' ? ct('saving') : session.part ? ct('useReference') : ct('use', { revision: session.revision }))}</button>` : live || pending ? `<button class="btn btn-primary" type="button" data-action="capture" id="capture-button" ${!live ? 'disabled' : ''}>${icon('camera')}${esc(ct('capture'))}</button>` : `<button class="btn btn-primary" type="button" data-action="capture-restart">${icon('camera')}${esc(ct('resume'))}</button>`}</div>`;
}
function renderCamera(session) { if (!captureActive(session)) return; const dialog = document.getElementById('camera-dialog'); dialog.innerHTML = cameraMarkup(session); if (session.stream) { const video = dialog.querySelector('video'); if (video) { video.srcObject = session.stream; video.play().catch(() => {}); } } }
async function openCamera(part = null) {
  if (!state.order || state.busy || ['completed', 'manual_reviewed'].includes(state.order.status) || (part && !PARTS.includes(part))) return;
  stopCamera();
  const session = { orderId: state.order.id, title: state.order.title, revision: state.order.revision, part, phase: 'starting', request: 0, stream: null, file: null, url: null, devices: [], deviceId: null, deviceLabel: '', error: null };
  captureSession = session; const dialog = document.getElementById('camera-dialog'); dialog.setAttribute('aria-labelledby', 'capture-title'); dialog.classList.add('modal-capture'); openModal('camera-dialog', cameraMarkup(session)); await captureStart(session);
}
async function captureStart(session, deviceId = null) {
  if (!captureActive(session)) return;
  captureStopStream(session); const request = session.request; session.phase = 'starting'; session.error = null; renderCamera(session);
  try {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) { session.phase = 'error'; session.error = ct('unsupported'); renderCamera(session); return; }
    const stream = await navigator.mediaDevices.getUserMedia({ video: { ...(deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: 'environment' } }), width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
    if (!captureActive(session) || request !== session.request) { stream.getTracks().forEach(track => track.stop()); return; }
    session.stream = stream; state.stream = stream;
    const track = stream.getVideoTracks()[0]; session.deviceId = track?.getSettings?.().deviceId || deviceId; session.deviceLabel = track?.label || '';
    track?.addEventListener('ended', () => { if (!captureActive(session) || request !== session.request) return; captureStopStream(session); session.phase = 'error'; session.error = ct('stopped'); renderCamera(session); }, { once: true });
    const video = document.getElementById('camera-preview'); video.srcObject = stream;
    await video.play();
    if (!captureActive(session) || request !== session.request) return;
    if (navigator.mediaDevices.enumerateDevices) { try { session.devices = (await navigator.mediaDevices.enumerateDevices()).filter(item => item.kind === 'videoinput'); } catch { session.devices = []; } }
    if (!captureActive(session) || request !== session.request) return;
    session.phase = 'live'; renderCamera(session);
  } catch (error) { if (!captureActive(session) || request !== session.request) return; captureStopStream(session); session.phase = 'error'; session.error = captureErrorText(error); renderCamera(session); }
}
async function capturePhoto() {
  const session = captureSession, video = document.getElementById('camera-preview');
  if (!session || !captureActive(session) || session.phase !== 'live' || state.busy) return;
  if (!video?.videoWidth || video.readyState < 2) { modalError('camera-dialog', ct('captureUnavailable')); return; }
  const canvas = document.createElement('canvas'), ratio = Math.min(1, 2048 / Math.max(video.videoWidth, video.videoHeight)); canvas.width = Math.round(video.videoWidth * ratio); canvas.height = Math.round(video.videoHeight * ratio); canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  const request = session.request; session.phase = 'processing'; document.getElementById('capture-button').disabled = true;
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.95));
  if (!captureActive(session) || request !== session.request) return;
  if (!blob) { session.phase = 'live'; session.error = ct('loadingFailed'); renderCamera(session); return; }
  await captureDraft(session, new File([blob], `capture-${Date.now()}.jpg`, { type: 'image/jpeg' }));
}
async function captureDraft(session, file) {
  if (!captureActive(session)) return;
  try { validateFile(file); } catch { session.error = ct('invalid'); renderCamera(session); return; }
  captureStopStream(session); const request = session.request; session.phase = 'processing'; session.error = null; renderCamera(session); const url = URL.createObjectURL(file);
  try {
    const img = new Image(); img.src = url; await img.decode();
    if (!captureActive(session) || request !== session.request) { URL.revokeObjectURL(url); return; }
    if (Math.min(img.naturalWidth, img.naturalHeight) < 32 || Math.max(img.naturalWidth, img.naturalHeight) > 8192 || img.naturalWidth * img.naturalHeight > 16000000) throw new Error(ct('invalidDimensions'));
    if (session.url) URL.revokeObjectURL(session.url); session.file = file; session.url = url; session.width = img.naturalWidth; session.height = img.naturalHeight; session.phase = 'review'; session.error = null; renderCamera(session); document.querySelector('#camera-dialog [data-action="capture-save"]')?.focus();
  } catch (error) { URL.revokeObjectURL(url); if (!captureActive(session) || request !== session.request) return; session.phase = session.file ? 'review' : 'error'; session.error = error.message === ct('invalidDimensions') ? error.message : ct('loadingFailed'); renderCamera(session); }
}
async function captureSave() {
  const session = captureSession;
  if (!session || !captureActive(session) || session.phase !== 'review' || !session.file || state.busy) return;
  if (state.order?.id !== session.orderId || state.order?.revision !== session.revision) { session.error = ct('stale'); renderCamera(session); return; }
  session.phase = 'saving'; session.error = null; renderCamera(session);
  const form = new FormData(); form.append('photo', session.file); form.append('expected_revision', session.revision);
  const endpoint = session.part ? `references/${session.part}` : 'photos';
  const result = await mutate(session.part ? 'reference' : 'upload', () => post(`/api/orders/${encodeURIComponent(session.orderId)}/${endpoint}`, form), session.part ? 'referenceUploaded' : 'photoUploaded', 'camera-dialog');
  if (!captureActive(session)) return;
  if (result) { document.getElementById('camera-dialog').close(); if (session.part && document.getElementById('references-dialog').open) openReferences(); }
  else { session.phase = 'review'; session.error = state.order?.revision !== session.revision ? ct('stale') : state.error || t('requestFailed'); renderCamera(session); }
}
async function captureRetake() { const session = captureSession; if (!session || state.busy || ['saving', 'processing'].includes(session.phase)) return; if (session.url) URL.revokeObjectURL(session.url); session.file = null; session.url = null; await captureStart(session); }
function captureNative() { const session = captureSession; if (!session || state.busy || ['saving', 'processing'].includes(session.phase)) return; captureStopStream(session); session.phase = session.file ? 'review' : 'paused'; renderCamera(session); capturePickerSession = session; const input = document.getElementById('capture-file'); input.value = ''; input.click(); }
document.addEventListener('click', async event => {
  const button = event.target.closest('[data-action]'); if (!button || button.disabled) return;
  if (button.dataset.action === 'capture-save') await captureSave();
  else if (button.dataset.action === 'capture-retake') await captureRetake();
  else if (button.dataset.action === 'capture-native') captureNative();
  else if (button.dataset.action === 'capture-restart' && captureSession) await captureStart(captureSession);
  else if (button.dataset.action === 'capture-switch' && captureSession?.devices.length > 1) { const session = captureSession; const index = session.devices.findIndex(item => item.deviceId === session.deviceId); await captureStart(session, session.devices[(index + 1) % session.devices.length].deviceId); }
});
document.getElementById('capture-file').addEventListener('change', event => { const file = event.target.files?.[0], session = capturePickerSession; capturePickerSession = null; if (file && session && captureActive(session)) captureDraft(session, file); });
document.addEventListener('visibilitychange', () => { const session = captureSession; if (document.hidden && session && !session.file && ['starting', 'live', 'processing'].includes(session.phase)) { captureStopStream(session); session.phase = 'paused'; renderCamera(session); } });
window.addEventListener('pagehide', () => { document.getElementById('camera-dialog').close(); stopCamera(); });

document.getElementById('camera-dialog').addEventListener('cancel', event => { if (!captureCanClose()) event.preventDefault(); else stopCamera(); });
