'use strict';
const status = document.getElementById('status');
function element(tag, text, className) { const node = document.createElement(tag); if (text) node.textContent = text; if (className) node.className = className; return node; }
async function request(url, options) { const response = await fetch(url, options); const data = await response.json(); if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`); return data; }
async function initializeDemos() {
  try {
    const data = await request('/api/public-demos');
    for (const sample of data.samples) {
      const card = element('article');
      if (sample.available) { const image = element('img'); image.src = `/api/public-demos/${encodeURIComponent(sample.sample_id)}/photo`; image.alt = sample.title; card.append(image); }
      else card.append(element('div', '공개 원본 미준비 / 本机尚未准备此公开源图', 'unavailable'));
      const body = element('div', '', 'body'); body.append(element('h2', sample.title), element('p', sample.source_note));
      body.append(element('small', `BOM · bolt ${sample.requirements.bolt} / nut ${sample.requirements.nut} / washer ${sample.requirements.washer} / bracket ${sample.requirements.bracket}`));
      const button = element('button', '이 사진으로 시작 / 使用此照片'); button.type = 'button'; button.disabled = !sample.available;
      button.addEventListener('click', async () => {
        document.querySelectorAll('button').forEach(b => { b.disabled = true; }); status.textContent = '데모 주문 준비 / 正在创建演示工单…';
        try { const result = await request(`/api/public-demos/${encodeURIComponent(sample.sample_id)}/orders`, { method: 'POST' }); window.location.assign(`/?order=${encodeURIComponent(result.order.id)}`); }
        catch (error) { status.className = 'error'; status.textContent = error.message; for (const b of document.querySelectorAll('button[data-available="true"]')) b.disabled = false; }
      });
      button.dataset.available = String(sample.available); body.append(button);
      const source = element('a', '원본 출처 / 作者来源 ↗'); source.href = sample.source_url; source.target = '_blank'; source.rel = 'noopener noreferrer'; body.append(source, element('small', sample.license)); card.append(body); document.getElementById('samples').append(card);
    }
    status.textContent = `${data.samples.filter(s => s.available).length}개 사용 가능 / 个样例已就绪`;
  } catch (error) { status.className = 'error'; status.textContent = error.message; }
}
initializeDemos();
