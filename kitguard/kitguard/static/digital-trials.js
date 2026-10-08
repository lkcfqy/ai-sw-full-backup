'use strict';
(() => {
  const parts = ['bolt', 'nut', 'washer', 'bracket'];
  const translations = {
    zh: {
      title:'公开照片任务对照', intro:'只用这台电脑，比较手工审查和 KitGuard 辅助审查。每人六个任务，预留 10–15 分钟；不需要购买零件、拍照或外部 GPU。',
      create:'开始新的参与者记录', code:'匿名编号', codeHint:'用 P01、P02 等编号，请勿填写姓名、学号或电话。', purpose:'记录用途', human:'真人自愿试用（本人声明）', rehearsal:'工程演练（不计真人）',
      index:'参与者顺序号', indexHint:'第 1、3、5 人先手工；第 2、4、6 人先 AI。三组照片轮换顺序。', consent:'我是自愿参加的人类参与者，同意保存匿名任务结果。我会独立完成，手工任务不使用 AI。', createButton:'冻结任务并创建记录',
      scope:'照片是已经用于开发的公开样例。这里测数字审查流程；不代表现场试验，也不是新图准确率。', protocol:'记录规则', rules:'开始后显示照片和要求，计时持续到提交，包含模型等待与人工复核。改版任务先记录 R1，再揭示 R2。关闭浏览器不会暂停；不要查看其他人的结果。',
      manual:'手工审查', kitguard:'KitGuard 辅助审查', quantity:'数量差异', identity:'小零件复核', revision:'订单改版', start:'开始任务 · 同时开始计时', task:'任务', next:'下一项', finished:'已记录', planned:'预定任务',
      current:'当前订单要求', version:'最终回答对应版本', observed:'你最终确认的数量', conclusion:'你的审查结论', matched:'照片数量与要求一致', mismatch:'照片数量与要求不一致', needs_more_evidence:'证据不足，需要进一步确认',
      bolt:'螺栓', nut:'螺母', washer:'垫圈', bracket:'支架', submit:'提交最终回答 · 停止计时', first:'保存 R1 回答 · 继续计时', firstSaved:'R1 回答已保存；尚未停止计时。', change:'揭示并应用订单 R2', changed:'订单已经改为 R2，旧版本的结论不适用于 R2。照片是明确复用的同一公开照片，没有实物变动。',
      inspect:'运行当前版本的本机 AI', checking:'本机模型正在核验，等待计入总用时…', aiHelp:'先运行 AI，再自行复核。模型的计数和结论可以不同于你的最终回答。', aiResult:'当前 AI 观察', noAI:'当前版本尚无有效 AI 观察。',
      ready:'模型判断数量一致', correct:'模型判断需要调整数量', recapture:'模型要求更多证据', manual_review:'模型要求人工确认', unknown:'未知',
      manualHint:'查看照片并独立计数，不使用 AI。两种方法都需要自己填写最后的数量、结论与版本。', timer:'正在计时（显示约值，以服务器结果为准）',
      help:'打开帮助', helpBody:'按四个粗类别计数，不判断规格或 SKU。螺栓有杆，螺母用于螺纹紧固，垫圈是环片，支架是连接构件。无法确认时请选择证据不足，数量可留空。本按钮只记录帮助页使用次数。',
      stopped:'失败或放弃', note:'原因', fail:'记录失败', abandon:'记录放弃', close:'关闭记录并公开结果', closeHint:'未开始的任务也保留在六项分母中。关闭后不能改写或继续。',
      report:'数字任务结果', reportHint:'这是同一参与者对三组重复照片的描述性结果。时间更短且回答正确才有价值；不能据此声称普遍提效。', engineeringNotice:'这是工程演练。自动化操作、既有作者标签和开发停留会影响结果与用时，不能作为人工基线、用户收益或模型准确率。', humans:'完成全部有效任务的真人（本人声明）', physical:'实物完工', purposeLabel:'用途', correctLabel:'正确 / 预定', wrongLabel:'错误', uncertainLabel:'证据不足', errorsLabel:'失败 / 放弃 / 中断 / 未开始', versionErrors:'版本错误', helpCount:'帮助打开次数', median:'完成任务用时中位数',
      paired:'AI − 手工用时（负值为 AI 更快）', noPair:'没有两种方法均完成且有效的配对', export:'下载结果 JSON', print:'打印结果', new:'新参与者', protocolHash:'冻结协议 SHA-256',
      sessions:'本浏览器保存的入口', restore:'恢复', noSessions:'尚无保存的入口。', refresh:'重新读取当前记录', activeElsewhere:'已有任务正在进行。先恢复并结束该任务。',
      choose:'请选择', saved:'记录已保存', failedRequest:'请求未完成', busy:'正在处理…', invalidCounts:'明确结论请填写四类 0–100 整数；证据不足可全部留空。', invalidNote:'失败或放弃需要填写原因。',
      not_started:'未开始', preparing:'准备中', running:'进行中', changing:'改版中', completed:'已完成', failed:'失败', abandoned:'放弃', interrupted:'服务中断', closed:'已关闭', open:'进行中',
    },
    ko: {
      title:'공개 사진 과제 비교', intro:'이 컴퓨터로 수기 검토와 KitGuard 보조 검토를 비교합니다. 1명당 6개 과제, 10–15분을 준비하세요. 부품 구매·촬영·외부 GPU가 필요하지 않습니다.',
      create:'새 참여자 기록', code:'익명 번호', codeHint:'P01, P02 같은 번호를 쓰세요. 이름·학번·전화번호는 입력하지 않습니다.', purpose:'기록 목적', human:'자발적 사람 시험 (자기 진술)', rehearsal:'엔지니어링 리허설 (사람 수 제외)',
      index:'참여 순서 번호', indexHint:'1·3·5번은 수기 먼저, 2·4·6번은 AI 먼저. 사진 3세트의 순서도 순환합니다.', consent:'자발적으로 참여하는 사람이며 익명 과제 결과 저장에 동의합니다. 독립적으로 수행하고 수기 과제에는 AI를 사용하지 않습니다.', createButton:'과제 고정 · 기록 생성',
      scope:'이미 개발에 사용한 공개 예시 사진입니다. 디지털 검토 절차를 측정하며 현장 시험이나 새 이미지 정확도가 아닙니다.', protocol:'기록 규칙', rules:'시작 후 사진·요구 수량을 공개하고 제출까지 시간을 기록합니다. 모델 대기와 사람 검토 포함. 변경 과제는 R1 응답 후 R2를 공개합니다. 브라우저 종료는 일시 정지가 아닙니다. 다른 사람의 결과를 보지 마세요.',
      manual:'수기 검토', kitguard:'KitGuard 보조 검토', quantity:'수량 차이', identity:'작은 부품 재검토', revision:'주문 변경', start:'과제 시작 · 시간 기록 시작', task:'과제', next:'다음 과제', finished:'저장됨', planned:'예정 과제',
      current:'현재 주문 요구 수량', version:'최종 응답의 버전', observed:'직접 최종 확인한 수량', conclusion:'본인의 검토 결론', matched:'사진 수량과 요구 수량 일치', mismatch:'사진 수량과 요구 수량 불일치', needs_more_evidence:'근거 부족 · 추가 확인 필요',
      bolt:'볼트', nut:'너트', washer:'와셔', bracket:'브래킷', submit:'최종 응답 제출 · 시간 기록 종료', first:'R1 응답 저장 · 시간 기록 계속', firstSaved:'R1 응답 저장됨. 시간 기록은 계속됩니다.', change:'주문 R2 공개 · 적용', changed:'주문이 R2로 변경되어 이전 버전의 판단은 R2에 적용할 수 없습니다. 같은 공개 사진을 명시적으로 재사용했으며 실물 변경은 없습니다.',
      inspect:'현재 버전의 로컬 AI 실행', checking:'로컬 모델 검사 중 — 대기도 전체 시간에 포함됩니다…', aiHelp:'AI 실행 후 직접 다시 확인하세요. 모델 수량·결론과 본인의 최종 응답은 달라도 됩니다.', aiResult:'현재 AI 관찰', noAI:'현재 버전의 유효한 AI 관찰이 없습니다.',
      ready:'모델: 수량 일치', correct:'모델: 수량 조정 필요', recapture:'모델: 근거 추가 필요', manual_review:'모델: 사람 확인 필요', unknown:'미확정',
      manualHint:'사진을 보고 AI 없이 직접 세세요. 두 방법 모두 최종 수량·결론·버전을 직접 입력합니다.', timer:'시간 기록 중 (표시는 근사값, 서버 결과가 기준)',
      help:'도움말 열기', helpBody:'4개 큰 종류만 세며 규격·SKU는 판단하지 않습니다. 볼트는 몸통, 너트는 나사 체결, 와셔는 고리판, 브래킷은 연결 부품입니다. 불명확하면 근거 부족을 선택하고 수량을 비워도 됩니다. 이 버튼은 도움말 사용 횟수만 기록합니다.',
      stopped:'실패 또는 포기', note:'사유', fail:'실패 기록', abandon:'포기 기록', close:'기록 종료 · 결과 공개', closeHint:'미시작도 6개 예정 과제에 포함됩니다. 종료 후 수정·추가는 불가능합니다.',
      report:'디지털 과제 결과', reportHint:'같은 참여자가 같은 사진 3세트를 반복한 기술적 결과입니다. 정확한 응답과 짧은 시간이 함께 필요하며 일반적인 효율 향상을 주장할 수 없습니다.', engineeringNotice:'엔지니어링 리허설입니다. 자동 조작·기존 저자 라벨·개발 대기가 결과와 시간에 영향을 주며 수기 기준·사용자 효과·모델 정확도로 사용할 수 없습니다.', humans:'전체 유효 과제를 마친 사람 (자기 진술)', physical:'실물 완료', purposeLabel:'목적', correctLabel:'정확 / 예정', wrongLabel:'오류', uncertainLabel:'근거 부족', errorsLabel:'실패 / 포기 / 중단 / 미시작', versionErrors:'버전 오류', helpCount:'도움말 사용', median:'완료 과제 시간 중앙값',
      paired:'AI − 수기 시간 (음수는 AI가 빠름)', noPair:'두 방법 모두 완료·유효한 짝이 없습니다.', export:'결과 JSON 다운로드', print:'결과 인쇄', new:'새 참여자', protocolHash:'고정 프로토콜 SHA-256',
      sessions:'이 브라우저에 저장한 접근', restore:'복원', noSessions:'저장된 접근이 없습니다.', refresh:'현재 기록 다시 읽기', activeElsewhere:'진행 중인 과제가 있습니다. 먼저 복원하여 종료하세요.',
      choose:'선택하세요', saved:'기록을 저장했습니다.', failedRequest:'요청을 완료하지 못했습니다.', busy:'처리 중…', invalidCounts:'명확한 결론에는 4개 0–100 정수를 입력하세요. 근거 부족은 모두 비워도 됩니다.', invalidNote:'실패·포기 사유를 입력하세요.',
      not_started:'미시작', preparing:'준비 중', running:'진행 중', changing:'변경 중', completed:'완료', failed:'실패', abandoned:'포기', interrupted:'서비스 중단', closed:'종료됨', open:'진행 중',
    },
  };
  const ui = document.querySelector('#digital-app');
  let lang = localStorage.getItem('kitguard-language') === 'zh' ? 'zh' : 'ko';
  let batch = null, token = null, busy = false, order = null, job = null, feedbackTimer;
  const drafts = new Map();
  const t = key => translations[lang][key] || key;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const seconds = ms => ms == null ? '—' : `${(ms / 1000).toFixed(1)} s`;
  function savedSessions() { try { return JSON.parse(localStorage.getItem('kitguard-digital-trials') || '[]'); } catch { return []; } }
  function saveAccess() {
    const rows = savedSessions().filter(s => s.id !== batch.id);
    rows.unshift({id:batch.id, token, code:batch.participant_code, index:batch.allocation_index, status:batch.status});
    localStorage.setItem('kitguard-digital-trials', JSON.stringify(rows));
    history.replaceState(null, '', `#${batch.id}:${token}`);
  }
  function notify(message) {
    const target = document.querySelector('#digital-feedback');
    target.textContent = message; target.hidden = false;
    clearTimeout(feedbackTimer); feedbackTimer = setTimeout(() => { target.hidden = true; }, 11000);
  }
  async function request(path, method='GET', body=null) {
    const response = await fetch(path, {method, headers:{'Content-Type':'application/json', ...(token ? {'X-Digital-Trial-Token':token} : {})},
      ...(body == null ? {} : {body:JSON.stringify(body)})});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : t('failedRequest'));
    return result;
  }
  const taskPath = (task, action) => `/api/digital-task-trials/${batch.id}/tasks/${task.id}/${action}`;
  const current = () => batch?.tasks.find(task => ['preparing','running','changing'].includes(task.status));
  async function refresh() {
    if (!batch) return;
    batch = (await request(`/api/digital-task-trials/${batch.id}`)).batch;
    const task = current();
    order = task?.order_id ? (await request(`/api/orders/${task.order_id}`)).order : null;
    saveAccess(); render();
  }
  function button(action, label, extra='') { return `<button data-action="${action}" ${busy ? 'disabled' : ''} ${extra}>${esc(t(label))}</button>`; }
  function bom(counts) { return `<div class="bom-row">${parts.map(p => `<span>${esc(t(p))} <strong>${esc(counts[p] ?? t('unknown'))}</strong></span>`).join('')}</div>`; }
  function progress() { return `<div class="task-progress" aria-label="${esc(t('planned'))}">${batch.tasks.map(task => `<span class="${current()?.id === task.id ? 'active' : ''}">${task.id} · ${esc(t(task.method))} · ${esc(t(task.status))}</span>`).join('')}</div>`; }
  function creation() {
    const sessions = savedSessions();
    return `<section><h2>${esc(t('create'))}</h2><form id="create-form"><div class="grid"><label>${esc(t('code'))}<input name="code" required pattern="[A-Za-z0-9_-]{1,32}" maxlength="32" placeholder="P01"><small>${esc(t('codeHint'))}</small></label><label>${esc(t('purpose'))}<select name="purpose" id="purpose"><option value="self_reported_human">${esc(t('human'))}</option><option value="engineering_rehearsal">${esc(t('rehearsal'))}</option></select></label><label>${esc(t('index'))}<input name="index" type="number" min="1" max="100" value="1" required><small>${esc(t('indexHint'))}</small></label></div><label class="check" id="consent-label"><input name="consent" type="checkbox" required><span>${esc(t('consent'))}</span></label><button type="submit" ${busy ? 'disabled' : ''}>${esc(t('createButton'))}</button></form></section><section class="sessions"><h2>${esc(t('sessions'))}</h2>${sessions.length ? sessions.map((s,i) => `<button data-action="restore" data-index="${i}" class="secondary">${esc(s.code)} · ${esc(t(s.status))} · ${esc(t('restore'))}</button>`).join('') : `<p>${esc(t('noSessions'))}</p>`}</section>`;
  }
  function answerForm(task) {
    const first = task.case_key === 'revision' && !task.first_answer;
    const pendingChange = task.case_key === 'revision' && task.first_answer && !task.change_revealed_at;
    if (pendingChange) return `<p class="saved-answer">${esc(t('firstSaved'))}</p>${button('change','change')}`;
    return `<form id="answer-form" data-draft="${batch.id}:${task.id}:R${task.binding.revision}"><fieldset><legend>${esc(t('observed'))}</legend><div class="counts-grid">${parts.map(p => `<label>${esc(t(p))}<input name="${p}" type="number" min="0" max="100" step="1" aria-label="${esc(t(p))}"></label>`).join('')}</div></fieldset><label>${esc(t('conclusion'))}<select name="conclusion" required><option value="">${esc(t('choose'))}</option><option value="matched">${esc(t('matched'))}</option><option value="mismatch">${esc(t('mismatch'))}</option><option value="needs_more_evidence">${esc(t('needs_more_evidence'))}</option></select></label><label>${esc(t('version'))}<select name="revision" required><option value="">${esc(t('choose'))}</option><option value="1">R1</option><option value="2">R2</option></select></label><button type="submit" ${busy || job?.status === 'running' ? 'disabled' : ''}>${esc(t(first ? 'first' : 'submit'))}</button></form>`;
  }
  function taskUI(task) {
    const check = order?.latest_check?.valid && order.latest_check.revision === task.binding?.revision ? order.latest_check : null;
    return `<section class="current-task"><h2>${esc(t('task'))} ${task.id} · ${esc(t(task.method))} · ${esc(t(task.case_key))}</h2><p class="timer" id="task-timer"></p>${task.binding ? `<div class="task-layout"><div><img class="task-image" src="${esc(task.binding.photo_url)}" alt="${esc(t(task.case_key))}"><p class="photo-caption">MVTec · CC BY-NC-SA 4.0 · ${esc(task.sample_id)}<br>SHA-256 ${esc(task.binding.photo_sha256)}</p></div><div><h3>${esc(t('current'))} R${task.binding.revision}</h3>${bom(task.binding.requirements)}${task.change_revealed_at ? `<p class="notice">${esc(t('changed'))}</p>` : ''}<p class="small">${esc(t(task.method === 'manual' ? 'manualHint' : 'aiHelp'))}</p>${task.method === 'kitguard' ? `<div class="model-output">${button('inspect', job?.status === 'running' ? 'checking' : 'inspect', job?.status === 'running' ? 'disabled' : '')}${check ? `<p>${esc(t('aiResult'))} · ${esc(t(check.decision))}</p>${bom(check.observed)}<small>MLX ${esc(check.backend)} · ${seconds(check.latency_ms)}</small>` : `<p>${esc(t('noAI'))}</p>`}</div>` : ''}${answerForm(task)}</div></div>` : `<p>${esc(t('busy'))}</p>`}<div class="actions">${button('help','help','class="secondary"')}${button('refresh','refresh','class="secondary"')}</div><details class="terminal-controls"><summary>${esc(t('stopped'))}</summary><label>${esc(t('note'))}<textarea id="stop-note" maxlength="1000"></textarea></label>${button('fail','fail','class="secondary"')}${button('abandon','abandon','class="secondary"')}</details></section>`;
  }
  function reportUI() {
    const r = batch.report;
    const metrics = ['correctLabel','wrongLabel','uncertainLabel','errorsLabel','versionErrors','helpCount','median'];
    const rows = metrics.map(key => `<tr><th scope="row">${esc(t(key))}</th>${['manual','kitguard'].map(method => {
      const m=r.methods[method]; const values={correctLabel:`${m.correct} / ${m.planned}`,wrongLabel:m.wrong,uncertainLabel:m.uncertain,errorsLabel:`${m.failed} / ${m.abandoned} / ${m.interrupted} / ${m.not_started}`,versionErrors:m.version_errors,helpCount:m.help_opens,median:seconds(m.completed_median_ms)};
      return `<td>${esc(values[key])}${key === 'median' ? ` (n=${m.completed_time_n})` : ''}</td>`;
    }).join('')}</tr>`).join('');
    return `<section><h2>${esc(t('report'))}</h2><p>${esc(t('reportHint'))}</p>${batch.purpose === 'engineering_rehearsal' ? `<p class="notice">${esc(t('engineeringNotice'))}</p>` : ''}<div class="summary-grid"><div><strong>${r.completed_self_reported_humans}</strong><small>${esc(t('humans'))}</small></div><div><strong>0</strong><small>${esc(t('physical'))}</small></div><div><strong>6</strong><small>${esc(t('planned'))} / ${esc(t(batch.purpose === 'engineering_rehearsal' ? 'rehearsal' : 'human'))}</small></div></div><div class="table-scroll"><table class="result-table"><thead><tr><th></th><th scope="col">${esc(t('manual'))}</th><th scope="col">${esc(t('kitguard'))}</th></tr></thead><tbody>${rows}</tbody></table></div><h3>${esc(t('paired'))}</h3>${r.pairs.map(p => `<p>${esc(t(p.case_key))}: ${p.both_completed_eligible ? seconds(p.kitguard_minus_manual_ms) : esc(t('noPair'))}</p>`).join('')}<div class="actions">${button('export','export')}${button('print','print','class="secondary"')}${button('new','new','class="secondary"')}</div><h3>${esc(t('protocolHash'))}</h3><p class="hash">${esc(batch.protocol_sha256)}</p><details><summary>${esc(t('protocol'))}</summary>${batch.limitations.map(line => `<p>${esc(line)}</p>`).join('')}</details></section>`;
  }
  function render() {
    const previousForm = document.querySelector('#answer-form');
    if (previousForm) drafts.set(previousForm.dataset.draft, Object.fromEntries(new FormData(previousForm)));
    document.documentElement.lang = lang;
    document.querySelector('#language').value = lang;
    document.querySelector('#header-label').textContent = t('title');
    ui.innerHTML = `<div class="digital-heading"><p class="eyebrow">LOCAL · PUBLIC PHOTOS · SIX TASKS</p><h1>${esc(t('title'))}</h1><p>${esc(t('intro'))}</p></div><p class="notice">${esc(t('scope'))}</p>${batch ? `<p>${esc(batch.participant_code)} · ${esc(t(batch.purpose === 'engineering_rehearsal' ? 'rehearsal' : 'human'))}</p>${progress()}` : `<details><summary>${esc(t('protocol'))}</summary><p>${esc(t('rules'))}</p></details>`}${!batch ? creation() : batch.status === 'closed' ? reportUI() : current() ? taskUI(current()) : `<section><h2>${esc(t('next'))}</h2>${batch.tasks.find(task => task.status === 'not_started') ? `<p>${esc(t(batch.tasks.find(task => task.status === 'not_started').method))} · ${esc(t(batch.tasks.find(task => task.status === 'not_started').case_key))}</p>${button('start','start')}` : `<p>${esc(t('finished'))} 6 / 6</p>`}<p class="small">${esc(t('closeHint'))}</p>${button('close','close','class="secondary"')}</section>`}`;
    const form=document.querySelector('#answer-form'), draft=form ? drafts.get(form.dataset.draft) : null;
    if (draft) Object.entries(draft).forEach(([key,value]) => {if (form.elements.namedItem(key)) form.elements.namedItem(key).value=value;});
    updateTimer();
  }
  function updateTimer() {
    const task=current(), target=document.querySelector('#task-timer');
    if (task && target) target.textContent = `${t('timer')} · ${Math.max(0,Math.round((Date.now()-Date.parse(task.started_at))/1000))} s`;
  }
  function readAnswer(form) {
    const data=new FormData(form), raw=parts.map(p => data.get(p).trim());
    let counts=null;
    if (raw.some(v => v !== '')) {
      if (raw.some(v => !/^\d+$/.test(v) || Number(v) > 100)) throw new Error(t('invalidCounts'));
      counts=Object.fromEntries(parts.map((p,i) => [p,Number(raw[i])]));
    }
    if (!counts && data.get('conclusion') !== 'needs_more_evidence') throw new Error(t('invalidCounts'));
    return {counts, revision:Number(data.get('revision')), conclusion:data.get('conclusion')};
  }
  async function run(action) {
    if (busy) return;
    busy=true; ui.querySelectorAll('button').forEach(b => b.disabled=true);
    try { await action(); } catch (error) { notify(error.message); }
    finally { busy=false; ui.querySelectorAll('button').forEach(b => b.disabled=job?.status === 'running' && (b.dataset.action === 'inspect' || b.closest('#answer-form') !== null)); }
  }
  ui.addEventListener('change', event => {
    if (event.target.id === 'purpose') {
      const human=event.target.value === 'self_reported_human';
      const input=ui.querySelector('[name=consent]'); input.required=human; input.checked=false;
      ui.querySelector('#consent-label').hidden=!human;
    }
  });
  ui.addEventListener('submit', event => {
    event.preventDefault(); const form=event.target;
    run(async () => {
      if (form.id === 'create-form') {
        const data=new FormData(form), response=await request('/api/digital-task-trials','POST',{
          participant_code:data.get('code'),purpose:data.get('purpose'),allocation_index:Number(data.get('index'))-1,
          consent_confirmed:data.get('purpose') === 'self_reported_human' && data.has('consent')});
        batch=response.batch; token=response.token; job=null; order=null; saveAccess(); render();
      } else if (form.id === 'answer-form') {
        const task=current(), answer=readAnswer(form), first=task.case_key === 'revision' && !task.first_answer;
        await request(taskPath(task,first ? 'first-answer' : 'finish'),'POST',first ? answer : {outcome:'completed',answer,note:''});
        job=null; await refresh(); notify(t('saved'));
      }
    });
  });
  ui.addEventListener('click', event => {
    const control=event.target.closest('[data-action]'); if (!control) return;
    const action=control.dataset.action;
    run(async () => {
      const task=current();
      if (action === 'restore') { const saved=savedSessions()[Number(control.dataset.index)]; batch={id:saved.id};token=saved.token;job=null; await refresh(); }
      else if (action === 'start') { const next=batch.tasks.find(row=>row.status === 'not_started'); await request(taskPath(next,'start'),'POST',{confirmed:true});job=null;await refresh(); }
      else if (action === 'change') { await request(taskPath(task,'reveal-change'),'POST',{confirmed:true});job=null;await refresh(); }
      else if (action === 'help') { await request(taskPath(task,'help'),'POST',{confirmed:true});notify(t('helpBody')); }
      else if (action === 'refresh') { await refresh(); }
      else if (action === 'fail' || action === 'abandon') { const note=document.querySelector('#stop-note').value.trim();if (!note) throw new Error(t('invalidNote'));await request(taskPath(task,'finish'),'POST',{outcome:action === 'fail' ? 'failed' : 'abandoned',note});job=null;await refresh(); }
      else if (action === 'close') { await request(`/api/digital-task-trials/${batch.id}/close`,'POST',{confirmed:true});await refresh(); }
      else if (action === 'new') { batch=null;token=null;order=null;job=null;history.replaceState(null,'',location.pathname);render(); }
      else if (action === 'print') { window.print(); }
      else if (action === 'export') {
        const payload=await request(`/api/digital-task-trials/${batch.id}/export`);
        const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
        const anchor=document.createElement('a');anchor.href=url;anchor.download=`kitguard-${batch.id}-digital-tasks.json`;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
      } else if (action === 'inspect') {
        const result=await request(`/api/orders/${task.order_id}/inspection-jobs`,'POST',{
          expected_revision:task.binding.revision,photo_id:task.binding.photo_id,request_key:crypto.randomUUID()});
        job=result.job;render();
      }
    });
  });
  document.querySelector('#language').addEventListener('change',event => {lang=event.target.value;render();});
  setInterval(updateTimer,1000);
  let polling=false;
  setInterval(async () => {
    if (polling || busy || !current() || current().method !== 'kitguard') return;
    polling=true;
    try {
      if (!job) {
        const response=await request(`/api/orders/${current().order_id}/inspection-jobs`);
        job=response.jobs?.find(j=>j.revision === current().binding.revision) || null;
        if (job?.status === 'running') render();
      }
      if (job?.status === 'running') {
        const response=await request(`/api/inspection-jobs/${job.id}`);job=response.job;
        if (job.status !== 'running') { await refresh();if (job.error) notify(job.error.message); }
      }
    } catch (error) { notify(error.message); } finally {polling=false;}
  },2500);
  async function initialize() {
    const match=location.hash.slice(1).match(/^(digital_trial_[a-f0-9]+):([A-Za-z0-9_-]{16,200})$/);
    if (match) {batch={id:match[1]};token=match[2];try {await refresh();} catch(error) {batch=null;token=null;notify(error.message);render();}}
    else render();
  }
  initialize();
})();
