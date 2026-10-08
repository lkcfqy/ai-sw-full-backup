/* Read-only snapshot. No order mutation or model execution. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const words = {
    ko: {skip:'본문으로 건너뛰기',title:'시연 전에, 한 번 확인하세요.',intro:'실행 중인 서버의 설정과 파일을 확인합니다. 주문을 바꾸거나 모델을 실행하지 않습니다.',scope:'확인할 기능',main:'주문 작업대',detector:'검출 실험',all:'둘 다',check:'지금 확인하기',download:'최신 점검 JSON 저장',limitsTitle:'이 점검의 범위',snapshot:'결과는 확인한 시점의 상태입니다. 모델을 실제로 실행할 수 있는지, 사진을 정확히 세는지는 별도 확인이 필요합니다.',back:'작업대로 돌아가기',openDetector:'검출 실험 열기',waiting:'점검 대기',waitingText:'기능을 선택한 뒤 확인하세요. 꺼진 검출 실험은 작업대 점검에 영향을 주지 않습니다.',checking:'서버 상태 확인 중',checkingText:'파일·설정·사용 상태를 읽고 있습니다.',passed:'읽기 전용 사전 점검 통과',passedText:'필수 확인 항목이 일치합니다. 모델 실행·정확도 검증을 뜻하지 않습니다.',failed:'시연 전 확인이 필요합니다',failedText:'아래 항목의 안내를 확인하고 다시 점검하세요.',pass:'확인',fail:'조치 필요',warn:'참고',info:'미검증',details:'확인 근거',at:'확인 시각',network:'서버에 연결하지 못했습니다. 현재 프로젝트의 서버와 포트를 확인한 뒤 다시 시도하세요.',limits:'모델을 로드하거나 추론하지 않습니다. 전체 가중치 해시, 실제 쓰기, 카메라 권한, 정확도는 확인하지 않습니다.',pendingChange:'기능 선택이 바뀌었습니다. 다시 확인하세요.'},
    zh: {skip:'跳到正文',title:'演示之前，先检查一遍。',intro:'检查运行服务的配置和文件，不更改工单，不运行模型。',scope:'检查范围',main:'工单工作台',detector:'检测实验',all:'两者均检查',check:'立即检查',download:'保存最新检查报告',limitsTitle:'本次检查的范围',snapshot:'结果只代表检查时刻的状态。模型能否实际运行、照片计数是否准确，仍需单独验证。',back:'返回工作台',openDetector:'打开检测实验',waiting:'等待检查',waitingText:'选择范围后开始检查。未启用的检测实验不会影响工作台检查。',checking:'正在检查服务状态',checkingText:'正在读取文件、配置和占用状态。',passed:'只读预检查通过',passedText:'必需检查项符合预期，这不代表已通过推理或准确率验证。',failed:'演示前还有事项需处理',failedText:'请按下方提示处理后重新检查。',pass:'已确认',fail:'需处理',warn:'提示',info:'未验证',details:'查看依据',at:'检查时间',network:'无法连接服务，请检查当前项目服务与端口后重试。',limits:'不加载模型、不推理，未核验全量权重散列、实际写入、相机权限或准确率。',pendingChange:'检查范围已更改，请重新检查。'}
  };
  let lang='ko', report=null, busy=false, failed=false;
  try {if(localStorage.getItem('kitguard-language')==='zh') lang='zh';} catch { /* Optional preference. */ }
  const t = key => words[lang][key] || key;
  const local = value => value?.[lang] || value?.ko || '';
  function element(tag, value, className) {const el=document.createElement(tag);el.textContent=value;if(className)el.className=className;return el;}
  function render() {
    document.documentElement.lang=lang;
    document.title=lang==='ko'?'KitGuard · 시연 전 점검':'KitGuard · 演示前检查';
    document.querySelectorAll('[data-i18n]').forEach(el=>{el.textContent=t(el.dataset.i18n);});
    document.querySelectorAll('[data-lang]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.lang===lang)));
    $('check').disabled=busy;$('mode').disabled=busy;$('download').disabled=busy||!report;
    const state=busy?'checking':failed?'failed':report?(report.ready?'passed':'failed'):'waiting';
    $('summary-title').textContent=t(state);$('summary-text').textContent=t(state+'Text');
    $('summary').dataset.state=state==='passed'?'pass':state==='failed'?'fail':'';
    $('checked-at').textContent=report?`${t('at')} · ${new Date(report.checked_at).toLocaleString(lang==='ko'?'ko-KR':'zh-CN')} · ${report.version||'—'}`:'';
    $('limits-text').textContent=report?local(report.limitations):t('limits');
    $('error').hidden=!failed;$('error').textContent=failed?t('network'):'';
    $('checks').replaceChildren();
    if(!report)return;
    const ordered=[...report.checks].sort((a,b)=>Number(b.state==='fail')-Number(a.state==='fail'));
    for(const check of ordered) {
      const card=element('article','','check-card'), heading=element('div','','card-heading');
      heading.append(element('h3',local(check.label)),element('span',t(check.state),'badge '+check.state));
      card.append(heading,element('p',local(check.message)));
      if(check.state==='fail'&&check.action)card.append(element('p',local(check.action),'action'));
      if(check.detail!==null&&check.detail!==undefined){const details=element('details','');details.append(element('summary',t('details')),element('pre',JSON.stringify(check.detail,null,2)));card.append(details);}
      $('checks').append(card);
    }
  }
  async function check() {
    if(busy)return;
    busy=true;failed=false;report=null;render();
    const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),15000);
    try {
      const response=await fetch(`/api/readiness?mode=${encodeURIComponent($('mode').value)}`,{cache:'no-store',signal:controller.signal});
      if(!response.ok)throw new Error('HTTP');
      const data=await response.json();
      if(data.schema!=='kitguard.readiness.v1'||!Array.isArray(data.checks)||typeof data.ready!=='boolean')throw new Error('Schema');
      report=data;
    } catch {failed=true;} finally {clearTimeout(timeout);busy=false;render();}
  }
  $('check').addEventListener('click',check);
  $('mode').addEventListener('change',()=>{report=null;failed=false;render();$('summary-text').textContent=t('pendingChange');});
  $('download').addEventListener('click',()=>{
    if(!report||busy)return;
    const link=document.createElement('a');
    link.href=`/api/readiness?mode=${encodeURIComponent(report.mode)}&download=true`;
    document.body.append(link);link.click();link.remove();
  });
  document.querySelectorAll('[data-lang]').forEach(el=>el.addEventListener('click',()=>{lang=el.dataset.lang;try{localStorage.setItem('kitguard-language',lang);}catch{/* Optional. */}render();}));
  const mode=new URLSearchParams(location.search).get('mode');if(['main','detector','all'].includes(mode))$('mode').value=mode;
  render();
})();
