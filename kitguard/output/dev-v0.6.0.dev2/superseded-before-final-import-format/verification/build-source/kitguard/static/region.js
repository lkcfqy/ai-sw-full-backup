/* Operator-declared scope. Coordinates always address the stored normalized root JPEG. */
'use strict';
window.KitGuardRegion = (() => {
  const copy = {
    ko: {title:'검사 범위', whole:'전체 사진', selected:'선택 영역 검사 · 영역 밖은 미검사', root:'저장된 전체 사진', preview:'같은 사진의 검사 입력', choose:'전체 사진에서 드래그하거나 아래 좌표를 입력하세요.', note:'이 사진은 방향·크기를 정규화한 저장본입니다. 범위 변경은 새 촬영이나 실물 변경이 아니며, AI 검사를 자동 실행하지 않습니다.', source:'같은 출처의 파생 뷰 · 새 실물 사진 아님', bounds:'원본 픽셀 경계', help:'왼쪽·위쪽 포함, 오른쪽·아래쪽 제외. 가로·세로 최소 32픽셀.', left:'왼쪽 X', top:'위쪽 Y', right:'오른쪽 X', bottom:'아래쪽 Y', confirm:'이 주문의 모든 검사 대상은 범위 안에 있고 경계가 부품을 자르지 않습니다. 영역 밖의 고정구·배경은 검사 대상이 아닙니다.', declaration:'운영자 선언입니다. 소프트웨어가 범위의 완전성을 인증하지 않습니다.', apply:'범위 적용', cancel:'취소', saved:'범위를 저장했습니다. 현재 범위로 검사를 실행하세요.', wholeButton:'전체 사진 선택', invalid:'네 좌표에 정수를 입력하세요. 사진 경계 안에 있어야 하며 가로·세로는 최소 32픽셀입니다.', confirmError:'모든 검사 대상이 범위 안에 있음을 확인하세요.', loadError:'전체 사진을 불러오지 못했습니다. 닫고 새로 읽은 뒤 다시 시도하세요.', retry:'최신 상태를 불러왔습니다. 이 창을 닫고 현재 사진과 범위를 확인한 뒤 다시 여세요. 자동 재시도하지 않습니다.', pending:'저장 중…', rootTime:'전체 사진 저장', viewTime:'파생 뷰 생성', id:'전체 사진 ID', inspectionOnly:'사람의 수기 계수와 AI 모두 표시된 검사 입력 영역만 대상으로 합니다.', ready:'선택 영역 안의 수량이 요구사항과 일치합니다. 영역 밖은 검사하지 않았습니다. 실제 부품과 범위의 완전성을 직접 확인하세요.', dimensions:'전체 사진', regionSize:'현재 범위', unknownRoot:'전체 사진 정보가 없어 범위를 변경할 수 없습니다.'},
    zh: {title:'检查范围', whole:'整张照片', selected:'选区核验 · 框外未核验', root:'已保存的完整照片', preview:'同一照片的核验输入', choose:'在完整照片上拖动矩形，或输入下方整数坐标。', note:'这里的完整照片是方向和尺寸归一化后的保存版本。修改范围不是新拍照或实物改变，也不会自动运行 AI。', source:'同源派生视图 · 不是新的实物照片', bounds:'根图像素边界', help:'左、上边界包含；右、下边界不包含。宽和高均至少 32 像素。', left:'左 X', top:'上 Y', right:'右 X', bottom:'下 Y', confirm:'本工单全部待检件都在范围内，边界未切断零件；框外固定装置与背景不属于待检对象。', declaration:'这是操作者声明，软件不认证范围的完整性。', apply:'应用范围', cancel:'取消', saved:'范围已保存，请对当前范围运行核验。', wholeButton:'选择整张照片', invalid:'四个边界必须是整数，位于照片范围内，且选区宽和高均至少 32 像素。', confirmError:'请确认全部待检件均在范围内。', loadError:'无法读取完整照片。请关闭并刷新后重试。', retry:'已读取最新状态。请关闭此窗口，确认当前照片和范围后重新打开；不会自动重试。', pending:'正在保存…', rootTime:'完整照片保存时间', viewTime:'派生视图生成时间', id:'完整照片 ID', inspectionOnly:'人工计数和 AI 都只检查这里显示的同一核验输入范围。', ready:'选区内数量与要求一致，框外未核验。请人工核对实物及范围是否完整。', dimensions:'完整照片', regionSize:'当前范围', unknownRoot:'缺少完整照片信息，无法修改范围。'}
  };
  const text = (lang,key) => (copy[lang] || copy.ko)[key];
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const url = id => `/api/photos/${encodeURIComponent(id)}`;
  const scope = photo => ({root_photo_id:photo.root_photo_id || photo.id, root_width:photo.root_width || photo.width, root_height:photo.root_height || photo.height, region_xyxy:photo.scope_mode === 'region' ? photo.region_xyxy : null, root_photo_sha256:photo.root_photo_sha256 || photo.sha256, root_created_at:photo.root_created_at || photo.created_at, scope_mode:photo.scope_mode || 'whole_image'});
  const isRegion = photo => photo?.scope_mode === 'region' && Array.isArray(photo.region_xyxy);
  function rootMarkup(value, lang, label='') {
    const w=Number(value.root_width),h=Number(value.root_height),box=value.region_xyxy;
    if (!Number.isInteger(w) || !Number.isInteger(h) || w<=0 || h<=0) return '';
    const hasBox=Array.isArray(box)&&box.length===4&&box.every(Number.isInteger)&&box[0]>=0&&box[1]>=0&&box[2]<=w&&box[3]<=h&&box[2]>box[0]&&box[3]>box[1];
    return `<figure class="kg-root-figure"><figcaption>${escape(label || text(lang,'root'))}</figcaption><svg class="kg-root-image" viewBox="0 0 ${w} ${h}" role="img" aria-label="${escape(text(lang,'root'))}"><image href="${escape(url(value.root_photo_id))}" width="${w}" height="${h}"/>${hasBox?`<rect class="kg-root-box" x="${box[0]}" y="${box[1]}" width="${box[2]-box[0]}" height="${box[3]-box[1]}" vector-effect="non-scaling-stroke"/>`:''}</svg>${hasBox?`<p class="kg-scope-coordinates">${escape(text(lang,'bounds'))}: [${box.join(', ')}] · ${w} × ${h}</p>`:''}</figure>`;
  }
  function summary(photo,lang) {
    if (!photo) return '';
    const s=scope(photo), derived=photo.kind==='inspection_region_view';
    return `<section class="kg-scope-summary" aria-label="${escape(text(lang,'title'))}"><strong>${escape(text(lang,isRegion(photo)?'selected':'whole'))}</strong>${derived?`<p>${escape(text(lang,'source'))}</p><p class="kg-scope-coordinates">${escape(text(lang,'rootTime'))}: ${escape(s.root_created_at)}<br>${escape(text(lang,'viewTime'))}: ${escape(photo.created_at)}</p>`:''}${isRegion(photo)?rootMarkup(s,lang):''}</section>`;
  }
  let context=null;
  function open({order,photo,lang='ko',save}) {
    const modal=document.getElementById('region-dialog');
    const s=scope(photo),root=order.photos.find(p=>p.id===s.root_photo_id);
    if (!root || !Number.isInteger(s.root_width) || !Number.isInteger(s.root_height)) throw new Error(text(lang,'unknownRoot'));
    const tr=key=>text(lang,key),w=s.root_width,h=s.root_height;
    const c={modal,lang,save,loaded:false,busy:false,stale:false,mode:isRegion(photo)?'region':'whole_image',box:s.region_xyxy?[...s.region_xyxy]:[0,0,w,h],w,h,snapshot:{expected_revision:order.revision,expected_photo_id:photo.id,expected_evidence_epoch:order.evidence_epoch,root_photo_id:root.id}};
    context=c;
    modal.innerHTML=`<div class="modal-header"><div><h2 id="region-title">${escape(tr('title'))}</h2><p>${escape(tr('choose'))}</p></div><button type="button" class="icon-btn" data-region="cancel" aria-label="${escape(tr('cancel'))}">×</button></div><form id="region-form" novalidate><div class="modal-content"><p class="kg-region-note">${escape(tr('note'))}</p><div class="kg-region-layout"><div><p class="kg-region-label">${escape(tr('root'))} · ${w} × ${h}</p><div class="kg-region-stage" id="region-stage"><img id="region-root" src="${escape(url(root.id))}" alt="${escape(tr('root'))}" draggable="false"><div id="region-box" aria-hidden="true"></div></div><p class="kg-scope-coordinates">${escape(tr('id'))}: ${escape(root.id)}</p></div><figure class="kg-region-preview"><figcaption>${escape(tr('preview'))}</figcaption><canvas id="region-preview"></canvas><p id="region-size" role="status"></p></figure></div><button class="btn btn-secondary btn-sm" type="button" data-region="whole">${escape(tr('wholeButton'))}</button><fieldset class="kg-region-fields"><legend>${escape(tr('bounds'))}</legend>${['left','top','right','bottom'].map((key,i)=>`<label>${escape(tr(key))}<input type="text" inputmode="numeric" autocomplete="off" name="coord${i}" value="${c.box[i]}" aria-describedby="region-coord-help"></label>`).join('')}</fieldset><p class="kg-region-note" id="region-coord-help">${escape(tr('help'))}</p><label class="kg-region-confirm"><input type="checkbox" name="confirmed"><span>${escape(tr('confirm'))}</span></label><p class="kg-region-note">${escape(tr('declaration'))}</p><div class="modal-error" role="alert"></div></div><div class="modal-footer"><button class="btn btn-quiet" type="button" data-region="cancel">${escape(tr('cancel'))}</button><button class="btn btn-primary" id="region-apply" type="submit" disabled>${escape(tr('apply'))}</button></div></form>`;
    const image=modal.querySelector('#region-root'),stage=modal.querySelector('#region-stage'),form=modal.querySelector('form');
    const read=()=>[0,1,2,3].map(i=>{const raw=form.elements[`coord${i}`].value.trim().normalize('NFKC');return /^\d+$/.test(raw)?Number(raw):NaN;});
    const valid=box=>box.every(Number.isSafeInteger)&&box[0]>=0&&box[1]>=0&&box[2]<=w&&box[3]<=h&&box[2]-box[0]>=32&&box[3]-box[1]>=32;
    const error=message=>{const el=modal.querySelector('.modal-error');el.textContent=message;el.classList.toggle('visible',!!message);};
    const update=(write=false)=>{
      if(write)c.box.forEach((n,i)=>{form.elements[`coord${i}`].value=n;});
      const ok=valid(c.box),overlay=modal.querySelector('#region-box');overlay.hidden=!ok;
      if(ok){overlay.style.left=`${c.box[0]/w*100}%`;overlay.style.top=`${c.box[1]/h*100}%`;overlay.style.width=`${(c.box[2]-c.box[0])/w*100}%`;overlay.style.height=`${(c.box[3]-c.box[1])/h*100}%`;}
      const canvas=modal.querySelector('canvas');canvas.hidden=!ok||!c.loaded;
      if(ok&&c.loaded){const sw=c.box[2]-c.box[0],sh=c.box[3]-c.box[1],scale=Math.min(1,420/sw,300/sh);canvas.width=Math.max(1,Math.round(sw*scale));canvas.height=Math.max(1,Math.round(sh*scale));canvas.getContext('2d').drawImage(image,c.box[0],c.box[1],sw,sh,0,0,canvas.width,canvas.height);}
      modal.querySelector('#region-size').textContent=ok?`${tr(c.mode==='whole_image'?'whole':'regionSize')} · ${c.box[2]-c.box[0]} × ${c.box[3]-c.box[1]}`:tr('invalid');
      modal.querySelector('#region-apply').disabled=!c.loaded||!ok||!form.elements.confirmed.checked||c.busy||c.stale;
    };
    image.onload=()=>{if(context!==c)return;if(image.naturalWidth!==w||image.naturalHeight!==h){error(tr('loadError'));return;}c.loaded=true;update();};
    image.onerror=()=>{if(context===c)error(tr('loadError'));};
    if(image.complete&&image.naturalWidth)image.onload();
    const point=event=>{const r=image.getBoundingClientRect();return [Math.min(w,Math.max(0,(event.clientX-r.left)/r.width*w)),Math.min(h,Math.max(0,(event.clientY-r.top)/r.height*h))];};
    let start=null,pointer=null;
    stage.addEventListener('pointerdown',event=>{if(c.busy||c.stale||!c.loaded||event.button!==0)return;event.preventDefault();start=point(event);pointer=event.pointerId;stage.setPointerCapture(pointer);});
    const drag=event=>{if(!start||event.pointerId!==pointer)return;const end=point(event);c.mode='region';c.box=[Math.floor(Math.min(start[0],end[0])),Math.floor(Math.min(start[1],end[1])),Math.ceil(Math.max(start[0],end[0])),Math.ceil(Math.max(start[1],end[1]))];form.elements.confirmed.checked=false;error('');update(true);};
    stage.addEventListener('pointermove',drag);
    stage.addEventListener('pointerup',event=>{drag(event);if(event.pointerId===pointer){start=null;pointer=null;}});
    stage.addEventListener('pointercancel',()=>{start=null;pointer=null;});
    form.addEventListener('input',event=>{if(c.busy||c.stale)return;if(event.target.name.startsWith('coord')){c.mode='region';c.box=read();form.elements.confirmed.checked=false;}error('');update();});
    form.addEventListener('keydown',event=>{if(c.busy||c.stale||!event.target.name?.startsWith('coord')||!['ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();const value=Number(event.target.value.normalize('NFKC'));if(!Number.isSafeInteger(value))return;event.target.value=value+(event.key==='ArrowUp'?1:-1);event.target.dispatchEvent(new Event('input',{bubbles:true}));});
    modal.querySelectorAll('[data-region]').forEach(button=>button.addEventListener('click',()=>{if(c.busy)return;if(button.dataset.region==='cancel'){modal.close();return;}if(c.stale)return;c.mode='whole_image';c.box=[0,0,w,h];form.elements.confirmed.checked=false;error('');update(true);}));
    form.addEventListener('submit',async event=>{event.preventDefault();if(c.busy||c.stale)return;c.box=read();if(!valid(c.box)){error(tr('invalid'));return;}if(!form.elements.confirmed.checked){error(tr('confirmError'));return;}if(!c.loaded){error(tr('loadError'));return;}c.busy=true;form.querySelectorAll('input,button').forEach(el=>{el.disabled=true;});modal.querySelectorAll('[data-region="cancel"]').forEach(el=>{el.disabled=true;});modal.querySelector('#region-apply').textContent=tr('pending');try{const result=await save({...c.snapshot,mode:c.mode,region_xyxy:c.mode==='region'?c.box:null,confirmed_all_items_inside:true});if(result){modal.close();}else{c.stale=true;const el=modal.querySelector('.modal-error');error(`${el.textContent}\n${tr('retry')}`);}}catch(err){c.stale=true;error(`${err.message}\n${tr('retry')}`);}finally{c.busy=false;modal.querySelectorAll('[data-region="cancel"]').forEach(el=>{el.disabled=false;});if(!c.stale)form.querySelectorAll('input,button').forEach(el=>{el.disabled=false;});modal.querySelector('#region-apply').textContent=tr('apply');update();}});
    if(!modal.dataset.regionBound){modal.addEventListener('cancel',event=>{if(context?.busy)event.preventDefault();});modal.dataset.regionBound='true';}
    modal.showModal();update();
  }
  return {open,scope,isRegion,summary,rootMarkup,text,canClose:()=>!context?.busy};
})();
