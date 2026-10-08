'use strict';
const TEXT = {
  ko: {brand:'자율 검토',back:'검증 워크스페이스',eyebrow:'LOCAL AGENT / PUBLIC PHOTO MISSION',
    title:'목표를 맡기면, 증거까지 정리합니다.',body:'공개 사진 3종을 실제 로컬 모델로 검토합니다. Agent가 수량 차이와 불확실성을 분기하고, 예정된 주문 변경에 새 검증을 실행한 뒤 증거를 묶습니다.',
    scenario:'실행할 과제',all:'전체 · 3개 시나리오',quantity:'수량 차이',identity:'작은 부품 불확실성',revision:'주문 변경 R1 → R2',
    start:'자율 검토 시작',starting:'시작 중',cancel:'다음 단계 중지',cancelWait:'현재 추론 후 중지',
    ready:'로컬 모델 준비됨',busy:'로컬 모델 처리 중',offline:'모델 확인 필요',runtime:'실행은 브라우저를 닫아도 계속됩니다.',
    notice:'0명 · 실물 없이 실행. R2는 시작 전 정한 모의 주문 변경이며, AI가 BOM을 임의로 수정하지 않습니다.',
    planned:'시나리오 실행',checks:'실제 검증 기록',time:'전체 소요 시간',people:'참여자 / 실물 완료',
    plannedNote:'성공 정확도 대신 실행 상태',checksNote:'계획',timeNote:'모델 로드·대기·준비 포함',peopleNote:'자동 엔지니어링 실행',
    heading:'실행 결과와 다음 행동',export:'증거 ZIP 저장',noFinding:'실행 대기',
    quantities_match:'수량 일치 기록',quantity_difference:'수량 차이 기록',needs_more_evidence:'추가 자료 필요',
    matchNote:'현재 BOM의 네 가지 굵은 종류 수량 비교 결과입니다.',diffNote:'차이를 보존합니다. BOM이나 실물을 자동으로 고치지 않습니다.',unknownNote:'불확실성을 유지합니다. 같은 사진으로 억지 재시도하지 않습니다.',
    bom:'요구',ai:'AI',part:'부품',delta:'차이',steps:'계획 · 도구 · 분기 근거',order:'주문 상세 열기',
    current:'현재 연결 유효',historical:'이후 변경으로 역사 기록',not_recorded:'아직 기록 없음',
    running:'실행 중',completed:'실행 종료',failed:'실행 실패',cancelled:'후속 단계 중지',interrupted:'서비스 중단',not_started:'대기',
    empty1:'차이를 찾고 기록',empty1Body:'사전 BOM과 실제 관찰 수량이 다르면 차이 목록을 만듭니다. 정답을 실행 입력으로 쓰지 않습니다.',
    empty2:'애매함을 그대로 남김',empty2Body:'작은 링 부품이 불확실하면 추가 자료 요청으로 끝냅니다. 독립 검토를 했다고 표시하지 않습니다.',
    empty3:'새 버전은 새 검증',empty3Body:'모의 R2에서 R1을 무효화합니다. 같은 사진을 명시적으로 재사용하고 새 모델 추론을 합니다.',
    boundaries:'이 결과가 뜻하는 것',boundaryBody:'기존 개발 사진의 자동 실행 증거입니다. 사람의 작업 시간 절감이나 새 이미지 정확도를 증명하지 않습니다. Agent 계획은 명시적 규칙이며, 사진 관찰은 실제 MLX 모델이 수행합니다.',
    history:'최근 실행',choose:'실행 기록 선택',restarted:'중단된 실행은 그대로 보존합니다. 새 실행으로 다시 검토하세요.',
    tool_prepare_public_photo:'공개 원본 검증 · 주문 생성',tool_local_vision:'현재 버전 로컬 추론',tool_list_differences:'차이 목록 기록',tool_request_more_evidence:'추가 자료 요청',tool_package_findings:'수량 일치 기록',tool_apply_planned_revision:'예정된 R2 · R1 무효화',tool_replay_verified_photo:'동일 사진 검증 · 재사용',
    reason_prepare_public_photo:'고정된 공개 원본과 사전 BOM을 사용합니다. 저장 예측을 쓰지 않습니다.',reason_local_vision:'현재 버전·사진·범위에 연결되는 새 AI 검증이 필요합니다.',reason_list_differences:'실제 비교에 차이가 있습니다. 요구 수량을 유지하고 차이를 기록합니다.',reason_request_more_evidence:'실제 관찰이 불확실합니다. 같은 자료로 확실하다고 단정하지 않습니다.',reason_package_findings:'네 가지 종류 수량이 현재 BOM과 일치합니다. 디지털 자료 결과를 묶습니다.',reason_apply_planned_revision:'사전에 정한 모의 주문 변경입니다. 옛 AI 검증이 유효하지 않음을 확인합니다.',reason_replay_verified_photo:'같은 사진이며 새 실물 촬영이 아닙니다. 새 버전에서 새 추론을 실행합니다.'},
  zh: {brand:'自主审查',back:'核验工作台',eyebrow:'LOCAL AGENT / PUBLIC PHOTO MISSION',
    title:'交给它一个目标，拿到一份证据。',body:'用真实本地模型审查三种公开照片。Agent 根据数量差异与不确定性选择分支，对预定的订单改版重新核验，最后整理证据。',
    scenario:'选择任务',all:'完整演示 · 三种场景',quantity:'数量差异',identity:'小零件不确定',revision:'订单改版 R1 → R2',
    start:'开始自主审查',starting:'正在启动',cancel:'停止后续步骤',cancelWait:'当前推理结束后停止',
    ready:'本地模型已就绪',busy:'本地模型正在处理',offline:'需要检查模型',runtime:'关闭或刷新浏览器后，任务继续运行。',
    notice:'0 位参与者 · 无需实物。R2 是开始前固定的模拟订单变更，AI 不会擅自改 BOM。',
    planned:'场景执行',checks:'实际核验记录',time:'整次用时',people:'参与者 / 实物完成',
    plannedNote:'展示执行状态，不代表准确率',checksNote:'计划',timeNote:'包含加载、推理等待与准备',peopleNote:'自动工程执行',
    heading:'执行结果与下一步',export:'下载证据 ZIP',noFinding:'等待执行',
    quantities_match:'已记录数量相符',quantity_difference:'已记录数量差异',needs_more_evidence:'需要更多资料',
    matchNote:'四种粗类别的可见数量与当前 BOM 比较结果。',diffNote:'保留差异，不会自动修改需求或实物。',unknownNote:'保留不确定性，不反复用同一照片硬凑结果。',
    bom:'需求',ai:'AI',part:'部件',delta:'差值',steps:'计划、工具与分支依据',order:'打开订单详情',
    current:'当前证据绑定有效',historical:'后续变化，已成为历史记录',not_recorded:'尚未记录',
    running:'执行中',completed:'执行结束',failed:'执行失败',cancelled:'后续步骤已停止',interrupted:'服务中断',not_started:'等待',
    empty1:'发现并记录差异',empty1Body:'实际观察数量与预定 BOM 不同时，生成差异清单。执行时不输入作者真值。',
    empty2:'不确定就保留不确定',empty2Body:'小环状零件无法确认时，以请求补资料结束。不会冒充已经做过独立复核。',
    empty3:'新版本，做新核验',empty3Body:'模拟 R2 让 R1 失效。明确复用同一照片，实际重新运行模型。',
    boundaries:'这些结果说明什么',boundaryBody:'这是既有开发照片上的自动执行证据，不证明真人提效或新图准确率。Agent 计划采用明确规则，照片观察由真实 MLX 模型完成。',
    history:'最近运行',choose:'选择运行记录',restarted:'中断的记录已保留。可启动新任务重新核验。',
    tool_prepare_public_photo:'校验公开原图并建单',tool_local_vision:'当前版本本地推理',tool_list_differences:'记录差异清单',tool_request_more_evidence:'请求更多资料',tool_package_findings:'整理数量相符记录',tool_apply_planned_revision:'执行预定 R2，使 R1 失效',tool_replay_verified_photo:'校验并复用同一照片',
    reason_prepare_public_photo:'使用固定公开原图与预定 BOM，不使用缓存预测。',reason_local_vision:'当前版本、照片和范围需要新的 AI 核验。',reason_list_differences:'实际数量比较存在差异，保持需求并列出差异。',reason_request_more_evidence:'实际观察不确定，同一资料不能凭声明变成确定。',reason_package_findings:'四种类别数量与当前 BOM 相符，整理数字资料结果。',reason_apply_planned_revision:'执行预定的模拟订单变更，确认旧 AI 检查已经失效。',reason_replay_verified_photo:'同一照片，不是新拍摄实物；新版本必须重新推理。'}
};
let lang = 'ko'; try { lang = localStorage.getItem('kitguard-lang') === 'zh' ? 'zh' : 'ko'; } catch { /* Optional. */ }
TEXT.ko.own_goal='현재 사진 · 내 BOM'; TEXT.zh.own_goal='当前照片 · 我的 BOM';
TEXT.ko.tool_verify_bound_order='현재 목표 입력 확인'; TEXT.zh.tool_verify_bound_order='确认当前任务输入';
TEXT.ko.reason_verify_bound_order='선택한 버전·사진·BOM·검사 범위를 확인합니다. 요구를 임의로 바꾸지 않습니다.';
TEXT.zh.reason_verify_bound_order='确认所选版本、照片、BOM 与核验范围，不擅自改需求。';
const goalId = new URLSearchParams(location.search).get('order');
const state = {run:null, runs:[], health:null, scenario:goalId?'order':'all', goal:null, pending:false, error:null};
const opened = new Set(); let timer, generation = 0;
const t = key => TEXT[lang][key] || key;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const parts = ['bolt','nut','washer','bracket'];
const partName = p => ({bolt:lang==='zh'?'螺纹件':'나사류',nut:lang==='zh'?'螺母':'너트',washer:lang==='zh'?'垫圈':'와셔',bracket:lang==='zh'?'角码':'브래킷'}[p]);
const isRunning = () => state.run?.status === 'running';
async function api(path, body) {
  const response = await fetch(path, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {cache:'no-store'});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `${response.status}`);
  return data;
}
function caseCard(c) {
  const check = c.snapshot?.latest_check || c.checks[c.checks.length - 1], photo = (c.snapshot || c.prepared_snapshot)?.photos?.at(-1);
  const bom = c.snapshot?.requirements || c.bom;
  const rows = parts.map(p => {const n = check?.observed[p], d = n == null ? null : n - bom[p]; return `<tr><td>${esc(partName(p))}</td><td>${bom[p]}</td><td class="${check && n == null ? 'count-unknown' : d ? 'count-diff':''}">${check ? n ?? '?' : '—'}</td><td>${d == null ? '—' : d > 0 ? `+${d}` : d}</td></tr>`;}).join('');
  const note = c.finding === 'quantities_match' ? t('matchNote') : c.finding === 'quantity_difference' ? t('diffNote') : c.finding === 'needs_more_evidence' ? t('unknownNote') : '';
  return `<article class="case-card" data-case="${esc(c.id)}"><div class="case-top"><h3>${esc(t(c.id==='order'?'own_goal':c.id))}</h3><span class="pill ${esc(c.status)}">${esc(t(c.status))}</span></div><div class="case-photo">${photo ? `<img src="/api/photos/${encodeURIComponent(photo.id)}" alt="${esc(t(c.id==='order'?'own_goal':c.id))}">` : `<span class="placeholder">${esc(t('noFinding'))}</span>`}</div><div class="case-body"><div class="finding"><strong>${esc(t(c.finding || 'noFinding'))}</strong><p>${esc(note)}</p></div><table class="counts"><thead><tr><th>${esc(t('part'))}</th><th>${esc(t('bom'))}</th><th>${esc(t('ai'))}</th><th>${esc(t('delta'))}</th></tr></thead><tbody>${rows}</tbody></table>${c.error ? `<p class="historical">${esc(c.error)}</p>`:''}${c.live_binding?.status === 'historical' ? `<p class="historical">${esc(t('historical'))} · ${esc(c.live_binding.reason)}</p>` : ''}<div class="case-link">${c.order_id ? `<a href="/?order=${encodeURIComponent(c.order_id)}" target="_blank" rel="noopener">${esc(t('order'))} ↗</a>`:''}<span>${check ? `R${check.revision} · ${(check.latency_ms/1000).toFixed(1)}s` : ''}</span></div></div><details class="steps" data-details="${esc(c.id)}" ${opened.has(c.id)?'open':''}><summary>${esc(t('steps'))} · ${c.steps.length}</summary><ol>${c.steps.map(s => `<li class="${esc(s.status)}"><b>${String(s.index).padStart(2,'0')} · ${esc(t('tool_'+s.tool))} <span class="pill ${esc(s.status)}">${esc(t(s.status))}</span></b><p>${esc(t('reason_'+s.tool))}</p>${s.result?.check_id ? `<code>${esc(s.result.check_id)} · ${s.result.latency_ms}ms</code>` : s.result?.revision ? `<code>R${s.result.revision} · old_check_valid: ${s.result.old_check_valid}</code>` : ''}</li>`).join('')}</ol></details></article>`;
}
function render() {
  const savedScroll={x:window.scrollX,y:window.scrollY}, activeId=document.activeElement?.id;
  document.querySelectorAll('details[data-details]').forEach(d => {if(d.open) opened.add(d.dataset.details); else opened.delete(d.dataset.details);});
  document.documentElement.lang = lang; document.title = `KitGuard · ${t('brand')}`;
  const run = state.run, model = state.health?.model, busy = state.health?.inference?.busy;
  const checks = run?.cases.reduce((n,c)=>n+c.checks.length,0) || 0;
  const done = run?.cases.filter(c=>c.status === 'completed').length || 0;
  document.getElementById('app').innerHTML = `<header class="bar"><a class="brand" href="/">KitGuard<small>${esc(t('brand'))}</small></a><div class="bar-actions"><a class="workspace-link" href="/">${esc(t('back'))} ↗</a><div class="languages"><button data-action="lang" data-lang="ko" class="${lang==='ko'?'active':''}" aria-pressed="${lang==='ko'}">한국어</button><button data-action="lang" data-lang="zh" class="${lang==='zh'?'active':''}" aria-pressed="${lang==='zh'}">中文</button></div></div></header><main id="mission"><section class="hero"><div><p class="eyebrow">${esc(state.scenario==='order'?'LOCAL AGENT / YOUR PHOTO + BOM':t('eyebrow'))}</p><h1>${esc(t('title'))}</h1><p>${esc(state.scenario==='order'?(lang==='zh'?'审查当前资料照片与您指定的 BOM，记录差异或请求更多资料，最后导出证据。':'현재 자료 사진과 직접 지정한 BOM을 검토하고, 차이 또는 추가 자료 요청을 증거로 정리합니다.'):t('body'))}</p></div><div class="hero-mark" aria-hidden="true"><svg viewBox="0 0 64 64" fill="none"><path d="M13 20h38v32H13zM22 12v15m20-15v15M13 31h38M23 40l6 6 12-13" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg></div></section><section class="controls"><label>${esc(t('scenario'))}<select id="scenario" ${isRunning()||state.pending?'disabled':''}>${[...(goalId?['order']:[]),'all','quantity','identity','revision'].map(s=>`<option value="${s}" ${state.scenario===s?'selected':''}>${esc(t(s==='order'?'own_goal':s))}</option>`).join('')}</select></label><button class="btn primary" data-action="start" ${isRunning()||state.pending||busy||!model?.available||(state.scenario==='order'&&!state.goal)?'disabled':''}>${state.pending?'<span class="spinner"></span>':'↗'} ${esc(t(state.pending?'starting':'start'))}</button>${isRunning()?`<button class="btn danger" data-action="cancel" ${run.cancel_requested||state.pending?'disabled':''}>${esc(t(run.cancel_requested?'cancelWait':'cancel'))}</button>`:''}<div class="runtime"><span class="dot ${model?.available&&!busy?'ok':''}"></span>${esc(t(!model?.available?'offline':busy?'busy':'ready'))}<br>${esc(t('runtime'))}</div></section><p class="notice">${esc(state.scenario==='order'?(lang==='zh'?'仅审查数字资料，不修改 BOM 或确认实物完成。来源说明由用户声明。':'디지털 자료만 검토합니다. BOM 수정·실물 완료를 하지 않으며 출처 설명은 사용자 선언입니다.'):t('notice'))}</p>${state.scenario==='order'&&state.goal?`<div class="goal-input"><strong>${esc(state.goal.title)} · R${state.goal.revision}</strong><p>${parts.map(p=>`${esc(partName(p))} ${state.goal.requirements[p]}`).join(' · ')}</p><a href="/?order=${encodeURIComponent(state.goal.id)}">${esc(t('order'))} ↗</a></div>`:''}${state.error?`<div class="error" role="alert">${esc(state.error)}</div>`:''}${run ? `<section class="summary"><div class="metric"><span>${esc(t('planned'))}</span><strong>${done} / ${run.planned_cases}</strong><small>${esc(t('plannedNote'))}</small></div><div class="metric"><span>${esc(t('checks'))}</span><strong>${checks} / ${run.planned_checks}</strong><small>${esc(t('checksNote'))} · ${run.planned_checks}</small></div><div class="metric"><span>${esc(t('time'))}</span><strong>${run.elapsed_ms==null?'—':(run.elapsed_ms/1000).toFixed(1)+'s'}</strong><small>${esc(t('timeNote'))}</small></div><div class="metric"><span>${esc(t('people'))}</span><strong>0 / 0</strong><small>${esc(t('peopleNote'))}</small></div></section><div class="mission-head"><div><h2>${esc(t('heading'))} <span class="pill ${esc(run.status)}">${esc(t(run.status))}</span></h2><p>${esc(run.id)}</p></div>${!isRunning()?`<a class="btn quiet" href="/api/autonomous-missions/${encodeURIComponent(run.id)}/evidence.zip" download>↓ ${esc(t('export'))}</a>`:''}</div>${run.error?`<p class="historical">${esc(run.error)} ${run.status==='interrupted'?esc(t('restarted')):''}</p>`:''}<section class="case-grid">${run.cases.map(caseCard).join('')}</section>` : `<section class="empty">${[1,2,3].map(i=>`<div><span>0${i} / ${['OBSERVE','ROUTE','RECHECK'][i-1]}</span><b>${esc(t('empty'+i))}</b><p>${esc(t('empty'+i+'Body'))}</p></div>`).join('')}</section>`}<footer class="footer"><div><h3>${esc(t('boundaries'))}</h3><p>${esc(t('boundaryBody'))}</p></div><div><h3>${esc(t('history'))}</h3><select class="history" id="history" aria-label="${esc(t('history'))}"><option value="">${esc(t('choose'))}</option>${state.runs.map(r=>`<option value="${esc(r.id)}" ${run?.id===r.id?'selected':''}>${esc(t(r.scenario==='order'?'own_goal':r.scenario))} · ${esc(t(r.status))} · ${esc(r.created_at.slice(11,19))}</option>`).join('')}</select></div></footer></main>`;
  if(['scenario','history'].includes(activeId)) document.getElementById(activeId)?.focus({preventScroll:true});
  window.scrollTo(savedScroll.x,savedScroll.y);
}
async function refresh(id) {
  const currentGeneration = ++generation; clearTimeout(timer);
  try {
    const results = await Promise.all([api('/api/health'),api('/api/autonomous-missions'),id?api(`/api/autonomous-missions/${encodeURIComponent(id)}`):Promise.resolve(null),goalId&&!state.goal?api(`/api/orders/${encodeURIComponent(goalId)}`):Promise.resolve(null)]);
    if (generation !== currentGeneration) return;
    [state.health] = results; state.runs = results[1].runs; if(results[2]) state.run = results[2].run; if(results[3]) {const order=results[3].order;if(!(order.document_source||order.demo_source)||!order.photos.length)throw new Error(lang==='zh'?'请选择有当前照片的数字资料订单':'현재 사진이 있는 디지털 자료 주문을 선택하세요');state.goal=order;}
    state.error = null; render();
  } catch(e) {if(generation !== currentGeneration) return; state.error=e.message; render();}
  if(generation === currentGeneration) timer=setTimeout(()=>refresh(state.run?.id),isRunning()?1200:5000);
}
document.addEventListener('click', async e => {
  const button=e.target.closest('[data-action]'); if(!button||button.disabled) return;
  if(button.dataset.action==='lang'){lang=button.dataset.lang;try{localStorage.setItem('kitguard-lang',lang);}catch{/* Optional. */}render();return;}
  state.pending=true;state.error=null;render();
  try{
    if(button.dataset.action==='start'){
      let request; try{request=JSON.parse(sessionStorage.getItem('kitguard-mission-pending'));}catch{/* Optional. */}
      const binding=state.scenario==='order'?{order_id:state.goal.id,expected_revision:state.goal.revision,expected_evidence_epoch:state.goal.evidence_epoch,expected_photo_id:state.goal.photos.at(-1).id}:{};
      const plan={scenario:state.scenario,...binding};
      if(!request||JSON.stringify({...request,request_key:undefined})!==JSON.stringify(plan)) request={...plan,request_key:'mission_'+crypto.randomUUID().replaceAll('-','')};
      try{sessionStorage.setItem('kitguard-mission-pending',JSON.stringify(request));}catch{/* Optional. */}
      const result=await api('/api/autonomous-missions',request);state.run=result.run;
      try{sessionStorage.removeItem('kitguard-mission-pending');}catch{/* Optional. */}
      history.replaceState(null,'','#'+state.run.id);
    }else if(button.dataset.action==='cancel'){state.run=(await api(`/api/autonomous-missions/${encodeURIComponent(state.run.id)}/cancel`,{confirmed:true})).run;}
    state.pending=false;await refresh(state.run?.id);
  }catch(error){state.pending=false;state.error=error.message;render();}
});
document.addEventListener('change',e=>{if(e.target.id==='scenario'){state.scenario=e.target.value;render();}if(e.target.id==='history'&&e.target.value){history.replaceState(null,'','#'+e.target.value);refresh(e.target.value);}});
render();
(async()=>{
  let id=/^#mission_[a-zA-Z0-9_-]+$/.test(location.hash)?location.hash.slice(1):null;
  if(!id&&!goalId){try{const listing=await api('/api/autonomous-missions');id=listing.runs[0]?.id;}catch{/* Refresh shows the error. */}}
  await refresh(id);
})();
