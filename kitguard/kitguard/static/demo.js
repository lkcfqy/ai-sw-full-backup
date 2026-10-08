'use strict';
const status = document.getElementById('status');
const REVIEW_FOCUS = {
  'bag-revision': ['주문 수량을 바꾸면 차이가 어떻게 달라지는지 확인하세요.', '修改需求数量，比较同一照片在新旧订单中的差异。'],
  'small-part': ['작은 부품의 분류와 추가 자료 요청을 검토하세요.', '查看小零件的分类判断，以及是否需要补充资料。'],
  'mixed-screws': ['모양이 다른 나사류의 분류와 수량을 검토하세요.', '查看不同外形的螺纹件如何被分类和计数。'],
};
const PART_NAMES = {
  bolt: ['나사류', '螺纹件'], nut: ['너트', '螺母'], washer: ['와셔', '垫圈'], bracket: ['브래킷', '角码'],
};
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function bilingual(tag, ko, zh, className) {
  const node = element(tag, ko, className);
  const translation = element('span', zh); translation.lang = 'zh'; node.append(translation);
  return node;
}
async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`);
  return data;
}
function requirements(sample) {
  const section = element('div', '', 'requirements');
  section.append(element('h3', '초기 주문 / 初始工单'));
  const counts = element('dl');
  for (const [part, names] of Object.entries(PART_NAMES)) {
    const item = element('div');
    item.append(bilingual('dt', ...names), element('dd', String(sample.requirements[part])));
    counts.append(item);
  }
  section.append(counts);
  return section;
}
function sourceLink(sample) {
  try {
    const url = new URL(sample.source_url);
    if (!['https:', 'http:'].includes(url.protocol)) throw new Error('Unsupported source link');
    const link = element('a', '원본 출처 / 原始来源 ↗');
    link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
    return link;
  } catch { return element('span', '원본 출처 확인 필요 / 需要核实来源链接'); }
}
async function initializeDemos() {
  try {
    const data = await request('/api/public-demos');
    for (const sample of data.samples) {
      const card = element('article', '', 'sample-card');
      if (sample.available) {
        const image = element('img');
        image.src = `/api/public-demos/${encodeURIComponent(sample.sample_id)}/photo`;
        image.alt = sample.title; image.loading = 'lazy'; card.append(image);
      }
      else card.append(element('div', '공개 원본 미준비 / 本机尚未准备此公开源图', 'unavailable'));
      const body = element('div', '', 'body');
      body.append(element('span', sample.derived_view ? '원본에서 자른 보기 / 原图裁剪视图' : '공개 원본 사진 / 公开原图', 'source-kind'));
      const [koTitle, ...zhTitle] = sample.title.split(' / ');
      body.append(zhTitle.length ? bilingual('h3', koTitle, zhTitle.join(' / ')) : element('h3', sample.title));
      const focus = REVIEW_FOCUS[sample.sample_id];
      body.append(focus ? bilingual('p', ...focus, 'review-focus') : element('p', sample.source_note, 'review-focus'));
      body.append(requirements(sample));
      const button = bilingual('button', '이 사진으로 검토 시작', '使用此照片开始审查');
      button.type = 'button'; button.disabled = !sample.available;
      button.addEventListener('click', async () => {
        document.querySelectorAll('button').forEach(b => { b.disabled = true; });
        status.className = ''; status.textContent = '검토할 주문을 여는 중 / 正在创建审查工单…';
        button.setAttribute('aria-busy', 'true');
        try {
          const result = await request(`/api/public-demos/${encodeURIComponent(sample.sample_id)}/orders`, { method: 'POST' });
          window.location.assign(`/?order=${encodeURIComponent(result.order.id)}`);
        } catch (error) {
          status.className = 'error'; status.textContent = error.message;
          button.removeAttribute('aria-busy');
          for (const b of document.querySelectorAll('button[data-available="true"]')) b.disabled = false;
        }
      });
      button.dataset.available = String(sample.available); body.append(button);
      const source = element('div', '', 'source');
      source.append(sourceLink(sample), element('small', sample.license)); body.append(source);
      const sourceDetails = element('details', '', 'source-details');
      sourceDetails.append(element('summary', '사진 설명 / 照片说明'), element('p', sample.source_note));
      body.append(sourceDetails);
      card.append(body); document.getElementById('samples').append(card);
    }
    const available = data.samples.filter(s => s.available).length;
    status.textContent = available ? `${available}개 사진 사용 가능 / ${available} 张照片已就绪`
      : '이 기기에 준비된 사진이 없습니다 / 本机暂无可用照片';
  } catch (error) { status.className = 'error'; status.textContent = error.message; }
}
initializeDemos();
