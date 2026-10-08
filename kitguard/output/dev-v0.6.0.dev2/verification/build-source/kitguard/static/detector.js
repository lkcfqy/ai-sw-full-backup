/* Separate detection preview. Never writes orders or declares task completion. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const words = {
    ko: {skip:'본문으로 건너뛰기',back:'작업대로 돌아가기 ↗',title:'부품 하나하나, 눈으로 확인하세요.',subtitle:'사진 속 볼트와 너트를 찾고, 표시된 상자를 실제 부품과 대조하세요.',connecting:'서비스 확인 중',available:'로컬 검출 준비됨',disabled:'검출 서비스가 꺼져 있습니다',serviceError:'검출 서비스에 연결할 수 없습니다',scopeTitle:'볼트 · 너트만 검출합니다',scope:'와셔와 브래킷은 아직 지원하지 않습니다. 누락·오검출이 있을 수 있으므로 사진을 직접 확인하세요.',photo:'01 / 사진 확인',clear:'새 사진',uploadTitle:'사진 한 장으로 시작하세요',uploadHint:'부품이 잘 보이는 사진을 끌어오거나 선택하세요.',choose:'사진 선택',camera:'카메라로 촬영',format:'JPEG · PNG · WebP / 최대 12 MB',photoTips:'겹침을 줄이고, 모든 부품을 프레임 안에 담으세요.',boxes:'검출 상자',sample:'공개 개발 사진으로 체험 ↗',sampleNote:'MVTec · CC BY-NC-SA 4.0 · 현장 검증으로 집계되지 않습니다.',results:'02 / 검출 결과',preview:'실험용',bolt:'볼트 / 나사',nut:'너트',washer:'와셔',bracket:'브래킷',unsupported:'미지원',estimate:'모델 추정',run:'이 사진 분석하기',selectFirst:'먼저 사진을 선택하세요.',ready:'사진이 준비되었습니다. 분석을 시작하세요.',running:'사진을 분석하고 있습니다',done:'검출이 끝났습니다. 상자와 실제 부품을 대조하세요.',failed:'분석을 완료하지 못했습니다. 사진과 서비스를 확인한 뒤 다시 시도하세요.',interrupted:'이전 분석이 중단되었습니다. 다시 분석할 수 있습니다.',disabledHelp:'검출 서비스를 시작한 뒤 이 페이지를 새로고침하세요.',download:'검출 기록 내려받기',checkTitle:'확인할 두 가지',checkOne:'모든 볼트와 너트에 상자가 하나씩 표시됐나요?',checkTwo:'빈 배경이나 다른 부품에 상자가 표시되지는 않았나요?',notRelease:'이 화면은 검출 결과를 확인하는 곳입니다. 주문 완료 여부는 작업대에서 확인합니다.',objects:'검출된 부품 목록',number:'번호',part:'종류',score:'모델 점수',location:'사진 내 위치',scoreNote:'점수는 모델의 출력값이며, 정답 확률이나 품질 보증이 아닙니다.',evidence:'사진과 모델 기록',footer:'사진은 이 컴퓨터에서 처리됩니다. 공개 데이터 학습 모델이며 실제 촬영 환경에서의 성능은 별도 확인이 필요합니다.',badType:'JPEG, PNG 또는 WebP 사진을 선택하세요.',tooLarge:'사진은 12 MB 이하여야 합니다.',readError:'사진을 읽을 수 없습니다. 다른 파일을 선택하세요.',noBoxes:'기준을 넘는 검출 상자가 없습니다. 물체가 없다는 뜻은 아닙니다.',publicPhoto:'공개 개발 사진 · 새 현장 샘플 아님',sourceHash:'업로드 원본 SHA-256',imageHash:'검출 이미지 SHA-256',modelHash:'모델 SHA-256',jobId:'검출 기록 ID',threshold:'고정 검출 기준',elapsed:'기록된 추론 시간',pending:'아직 기록되지 않음',network:'요청에 실패했습니다. 연결을 확인하고 다시 시도하세요.',busy:'다른 사진을 분석 중입니다. 잠시 후 다시 시도하세요.',retryStatus:'진행 상태 다시 확인',pollError:'진행 상태를 읽지 못했습니다. 분석이 계속되고 있을 수 있으니 상태를 다시 확인하세요.',seconds:'초',countUnit:'개'},
    zh: {skip:'跳到正文',back:'返回工单工作台 ↗',title:'把每一件零件，看清楚。',subtitle:'找出照片里的螺栓和螺母，对照检测框，检查有没有漏掉的零件。',connecting:'正在检查服务',available:'本地检测已就绪',disabled:'检测服务尚未启用',serviceError:'无法连接检测服务',scopeTitle:'当前覆盖螺栓与螺母',scope:'垫圈、角码尚未覆盖。模型可能漏检或误检，请对照照片检查。',photo:'01 / 检查照片',clear:'换一张照片',uploadTitle:'从一张零件照片开始',uploadHint:'拖入照片，或选择一张能看清零件的图片。',choose:'选择照片',camera:'使用相机拍摄',format:'JPEG · PNG · WebP / 最大 12 MB',photoTips:'尽量减少遮挡，让所有零件完整入镜。',boxes:'显示检测框',sample:'试用公开开发样例 ↗',sampleNote:'MVTec · CC BY-NC-SA 4.0 · 不计入新照片或现场验证。',results:'02 / 检测结果',preview:'实验功能',bolt:'螺栓 / 螺钉',nut:'螺母',washer:'垫圈',bracket:'角码',unsupported:'未覆盖',estimate:'模型估计',run:'分析这张照片',selectFirst:'请先选择一张照片。',ready:'照片已准备好，可以开始分析。',running:'正在分析照片',done:'检测完成，请对照照片检查每一个框。',failed:'本次分析未完成，请检查照片和服务后重试。',interrupted:'之前的分析已中断，可以重新分析。',disabledHelp:'请先启动检测服务，再刷新这个页面。',download:'下载检测记录',checkTitle:'请检查两件事',checkOne:'每个螺栓和螺母是否都恰好对应一个框？',checkTwo:'有没有把背景或其他零件误框出来？',notRelease:'这个页面用于检查检测结果。工单是否完成，请在工作台确认。',objects:'检测到的零件',number:'编号',part:'类别',score:'模型分数',location:'照片中的位置',scoreNote:'分数是模型输出，不等于正确概率或质量保证。',evidence:'查看照片与模型记录',footer:'照片在这台电脑上处理。模型使用公开数据训练，真实拍摄环境中的效果仍需单独验证。',badType:'请选择 JPEG、PNG 或 WebP 格式的照片。',tooLarge:'照片不能超过 12 MB。',readError:'无法读取照片，请换一个图片文件。',noBoxes:'没有超过固定阈值的检测框，这不表示照片里没有物体。',publicPhoto:'公开开发样例 · 非新现场样本',sourceHash:'上传原图 SHA-256',imageHash:'检测图片 SHA-256',modelHash:'模型 SHA-256',jobId:'检测记录编号',threshold:'固定检测阈值',elapsed:'记录的推理耗时',pending:'尚未记录',network:'请求失败，请检查连接后重试。',busy:'另一张照片正在分析，请稍后重试。',retryStatus:'重新检查进度',pollError:'暂时无法读取进度，后台可能仍在分析，请重新检查状态。',seconds:'秒',countUnit:'件'}
  };
  let lang='ko'; try { lang=localStorage.getItem('kitguard-language')==='zh'?'zh':'ko'; } catch { /* Optional storage. */ }
  let file=null, previewURL=null, service=null, job=null, active=false, pollingFailed=false, isSample=false, timer=null, started=0;
  let statusKey='selectFirst';
  const t=key=>words[lang][key] || key;
  const setError=message=>{ $('error-message').textContent=message; $('error-message').hidden=!message; };
  function renderStatus(){
    $('job-status').textContent=t(statusKey)+(active&&!pollingFailed ? ` · ${Math.max(0,Math.floor((Date.now()-started)/1000))} ${t('seconds')}`:'');
    $('run-detection').textContent=t(pollingFailed?'retryStatus':active?'running':'run');
    $('run-detection').disabled=(!file && !pollingFailed)||(!service?.available && !pollingFailed)||(active&&!pollingFailed);
    $('clear-photo').disabled=active||(!file&&!job);
    $('load-sample').disabled=active;
    $('photo-input').disabled=active; $('camera-input').disabled=active; $('take-photo').disabled=active;
    $('photo-name').textContent=isSample?t('publicPhoto'):file?.name || t('photoTips');
  }
  function language(){
    document.documentElement.lang=lang;
    document.title=lang==='zh'?'KitGuard · 零件检测验证':'KitGuard · 부품 검출 확인';
    document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n));
    document.querySelectorAll('[data-lang]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.lang===lang)));
    if(service){ $('service-status').textContent=t(service.available?'available':'disabled'); }
    $('photo-preview').alt=t('photo');
    renderStatus(); if(job?.status==='completed') renderResult();
  }
  async function request(url, options={}){
    const response=await fetch(url,options);
    let data; try {data=await response.json();} catch {throw new Error(t('network'));}
    if(!response.ok){const message=typeof data.detail==='string'?data.detail:t('network');throw new Error(response.status===503?t('busy'):message);}
    return data;
  }
  function resetResult(){
    job=null; $('count-bolt').textContent='—';$('count-nut').textContent='—';
    $('boxes-overlay').replaceChildren();$('detection-detail').hidden=true;$('result-actions').hidden=true;$('boxes-control').hidden=true;
    history.replaceState(null,'',location.pathname);
  }
  function choosePhoto(selected, sample=false){
    if(active || !selected)return;
    if(!['image/jpeg','image/png','image/webp'].includes(selected.type)){setError(t('badType'));return;}
    if(selected.size>12*1024*1024){setError(t('tooLarge'));return;}
    if(previewURL)URL.revokeObjectURL(previewURL);
    resetResult();file=selected;isSample=sample;pollingFailed=false;setError('');
    previewURL=URL.createObjectURL(file);$('photo-preview').src=previewURL;
    $('photo-preview').onerror=()=>{setError(t('readError'));file=null;statusKey='selectFirst';renderStatus();};
    $('empty-photo').hidden=true;$('photo-stage').hidden=false;statusKey=service?.available?'ready':'disabledHelp';renderStatus();
  }
  function svgElement(name, attributes){
    const el=document.createElementNS('http://www.w3.org/2000/svg',name);
    Object.entries(attributes).forEach(([key,value])=>el.setAttribute(key,String(value)));return el;
  }
  function renderResult(){
    const result=job.result, items=(result.predictions||[]).filter(p=>p.retained_at_frozen_threshold);
    $('count-bolt').textContent=result.counts.bolt;$('count-nut').textContent=result.counts.nut;
    $('result-actions').hidden=false;$('boxes-control').hidden=false;$('detection-detail').hidden=false;
    $('object-count').textContent=`${items.length} ${t('countUnit')}`;
    const width=job.image.width,height=job.image.height,overlay=$('boxes-overlay');
    overlay.setAttribute('viewBox',`0 0 ${width} ${height}`);overlay.replaceChildren();
    $('object-rows').replaceChildren();
    for(const [index,item] of items.entries()){
      const [x1,y1,x2,y2]=item.bbox_xyxy,part=item.label===1?'bolt':'nut',color=part==='bolt'?'#087265':'#386d9d';
      overlay.append(svgElement('rect',{x:x1,y:y1,width:x2-x1,height:y2-y1,stroke:color}));
      const label=svgElement('text',{x:Math.max(4,x1),y:Math.max(width/45,y1-7),'font-size':Math.max(12,width/47),fill:color});
      label.textContent=`${index+1} ${t(part)}`;overlay.append(label);
      const row=document.createElement('tr');
      [String(index+1),t(part),Number(item.score).toFixed(3),item.bbox_xyxy.map(n=>Math.round(n)).join(', ')].forEach(value=>{const cell=document.createElement('td');cell.textContent=value;row.append(cell);});
      $('object-rows').append(row);
    }
    if(!items.length){const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=4;cell.textContent=t('noBoxes');row.append(cell);$('object-rows').append(row);}
    overlay.toggleAttribute('hidden',!$('show-boxes').checked);
    const evidence=[['jobId',job.id],['sourceHash',job.image.source_sha256],['imageHash',job.image.sha256],['modelHash',result.checkpoint_sha256||job.model?.checkpoint_sha256],['threshold',result.threshold],['elapsed',Number.isFinite(result.inference_seconds)?`${result.inference_seconds.toFixed(3)} ${t('seconds')}`:t('pending')]];
    $('evidence-records').replaceChildren();
    evidence.forEach(([key,value])=>{const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=t(key);dd.textContent=String(value??t('pending'));$('evidence-records').append(dt,dd);});
  }
  function displayJob(value){
    job=value;
    if(job.image){$('photo-preview').src=`/api/detector-lab/jobs/${encodeURIComponent(job.id)}/image`;$('empty-photo').hidden=true;$('photo-stage').hidden=false;}
    if(job.status==='completed') {active=false;pollingFailed=false;statusKey='done';renderResult();}
    else if(['failed','interrupted'].includes(job.status)){active=false;pollingFailed=false;statusKey=job.status;setError(typeof job.error==='string'?job.error:job.error?.message||t(statusKey));}
    else {active=true;pollingFailed=false;statusKey='running';}
    renderStatus();
  }
  async function poll(){
    clearTimeout(timer);
    try {displayJob((await request(`/api/detector-lab/jobs/${encodeURIComponent(job.id)}`)).job);}
    catch {pollingFailed=true;statusKey='pollError';renderStatus();return;}
    if(active)timer=setTimeout(poll,800);
  }
  async function run(){
    if(pollingFailed){pollingFailed=false;setError('');await poll();return;}
    if(!file||active||!service?.available)return;
    setError('');resetResult();active=true;started=Date.now();statusKey='running';renderStatus();
    const form=new FormData();form.append('photo',file);
    try {const data=await request('/api/detector-lab/jobs',{method:'POST',body:form});displayJob(data.job);history.replaceState(null,'',`${location.pathname}?job=${encodeURIComponent(job.id)}`);if(active)timer=setTimeout(poll,500);}
    catch(error){active=false;statusKey='ready';setError(error.message);renderStatus();}
  }
  document.querySelectorAll('[data-lang]').forEach(button=>button.addEventListener('click',()=>{lang=button.dataset.lang;try{localStorage.setItem('kitguard-language',lang);}catch{/* Optional. */}language();}));
  $('photo-input').addEventListener('change',event=>choosePhoto(event.target.files[0]));
  $('camera-input').addEventListener('change',event=>choosePhoto(event.target.files[0]));
  $('take-photo').addEventListener('click',()=>$('camera-input').click());
  $('clear-photo').addEventListener('click',()=>{if(active)return;resetResult();file=null;isSample=false;setError('');$('photo-input').value='';$('camera-input').value='';if(previewURL)URL.revokeObjectURL(previewURL);previewURL=null;$('photo-preview').removeAttribute('src');$('photo-stage').hidden=true;$('empty-photo').hidden=false;statusKey='selectFirst';renderStatus();});
  $('run-detection').addEventListener('click',run);
  ['input','change','click'].forEach(kind=>$('show-boxes').addEventListener(kind,()=>{$('boxes-overlay').toggleAttribute('hidden',!$('show-boxes').checked);}));
  $('load-sample').addEventListener('click',async()=>{if(active)return;try{setError('');const response=await fetch('/api/public-demos/small-part/photo');if(!response.ok)throw new Error(t('network'));choosePhoto(new File([await response.blob()],'public-development-small-part.png',{type:'image/png'}),true);}catch(error){setError(error.message);}});
  $('download-result').addEventListener('click',()=>{if(!job)return;const link=document.createElement('a');link.href=`/api/detector-lab/jobs/${encodeURIComponent(job.id)}/download`;link.download=`kitguard-detection-${job.id}.json`;document.body.append(link);link.click();link.remove();});
  ['dragenter','dragover'].forEach(kind=>$('drop-zone').addEventListener(kind,event=>{event.preventDefault();if(!active)$('drop-zone').classList.add('dragging');}));
  ['dragleave','drop'].forEach(kind=>$('drop-zone').addEventListener(kind,event=>{event.preventDefault();$('drop-zone').classList.remove('dragging');if(kind==='drop')choosePhoto(event.dataTransfer.files[0]);}));
  window.addEventListener('pagehide',()=>{clearTimeout(timer);if(previewURL)URL.revokeObjectURL(previewURL);});
  async function start(){
    language();
    try{service=await request('/api/detector-lab/status');$('service-status').textContent=t(service.available?'available':'disabled');$('service-status').classList.toggle('available',!!service.available);if(!service.available)statusKey='disabledHelp';}
    catch {service={available:false};$('service-status').textContent=t('serviceError');statusKey='disabledHelp';}
    renderStatus();
    const existing=new URLSearchParams(location.search).get('job');
    if(existing&&/^[A-Za-z0-9_-]{1,80}$/.test(existing)){job={id:existing};started=Date.now();await poll();}
  }
  start();
})();
