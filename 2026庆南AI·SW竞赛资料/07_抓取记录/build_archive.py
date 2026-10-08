#!/usr/bin/env python3
"""Build offline reading copies and auditable source inventories.
Run after archive.py has finished. Requires beautifulsoup4.
"""
import datetime
import difflib
import hashlib
import html
import json
import os
import pathlib
import re
import urllib.parse
from collections import Counter, defaultdict
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOW = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec='seconds')
STYLE = 'body{max-width:1050px;margin:40px auto;padding:0 24px;font:17px/1.7 system-ui,sans-serif;color:#182230;background:#f8fafc}main{background:white;padding:30px;border:1px solid #ddd;border-radius:10px}img{max-width:100%;height:auto!important}table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #cbd5e1;padding:8px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#1649a3;overflow-wrap:anywhere}.meta{color:#536277;font-size:14px}h1{line-height:1.3}li{margin:5px 0}'

def rel_link(p, origin):
    return urllib.parse.quote(os.path.relpath(p, origin),safe='/')

def norm(u):
    u=urllib.parse.unquote(u).strip()
    return u.replace('https://www.gnict.org/','https://gnict.org/').split('#',1)[0]

def wrap(title, body, source=None):
    meta = f'<p class="meta">归档生成：{html.escape(NOW)}。离线整理版；原始文件另外保留。</p>'
    if source:
        meta += f'<p>来源：<a href="{html.escape(source,quote=True)}">{html.escape(source)}</a></p>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+'</style><main><h1>'+html.escape(title)+'</h1>'+meta+body+'</main></html>'

sources=[]
for p in sorted(ROOT.rglob('*.metadata.json')):
    original=p.with_name(p.name[:-len('.metadata.json')])
    if not original.exists():
        continue
    m=json.loads(p.read_text())
    data=original.read_bytes()
    record={
        'path':str(original.relative_to(ROOT)), 'url':m.get('url') or m.get('source_url'),
        'final_url':m.get('final_url'), 'referrer':m.get('source'),
        'retrieved_at':m.get('retrieved_at') or datetime.datetime.fromtimestamp(original.stat().st_mtime,datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec='seconds'),
        'retrieved_at_basis':'request_log' if m.get('retrieved_at') else 'saved_file_mtime', 'kind':m.get('kind','webpage'),
        'http_status':m.get('http_status',m.get('status')), 'content_type':m.get('content_type'),
        'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest(),
        'content_disposition':m.get('content_disposition'),
    }
    sources.append(record)

urlmap={}
for rec in sources:
    for u in (rec['url'],rec['final_url']):
        if u:urlmap[norm(u)]=ROOT/rec['path']

offline={}
links=[]
for rec in sources:
    p=ROOT/rec['path']
    if p.suffix!='.html':continue
    soup=BeautifulSoup(p.read_bytes(),'html.parser')
    title=soup.title.get_text(' ',strip=True) if soup.title else p.stem
    selected=None
    for selector in ('#nttViewForm','#bo_v','.page-body','#articleBody','.article-body','#gnict-main','main','form','body'):
        selected=soup.select_one(selector)
        if selected:break
    if selected is None:selected=soup
    copy=BeautifulSoup(str(selected),'html.parser')
    for tag in copy.select('script,style,link,meta,input,button,select,textarea,iframe,header,nav,footer,.gn-header,.gn-footer'):
        tag.decompose()
    for tag in copy.find_all(True):
        for attr in list(tag.attrs):
            if attr.lower().startswith('on') or attr in ('style','srcset','action','method'):del tag[attr]
    out=p.with_name(p.stem+'_离线阅读.html')
    for tag in copy.select('a[href],img[src]'):
        attr='src' if tag.name=='img' else 'href'
        raw=tag.get(attr,'')
        if not raw:continue
        full=urllib.parse.urljoin(rec['final_url'] or rec['url'],raw)
        links.append({'page':rec['path'],'tag':tag.name,'label':tag.get_text(' ',strip=True)[:200] or tag.get('alt',''),'url':full,'local_path':str(urlmap[norm(full)].relative_to(ROOT)) if norm(full) in urlmap else None})
        if norm(full) in urlmap:
            tag[attr]=rel_link(urlmap[norm(full)],out.parent)
        elif tag.name=='img':
            # A remote site logo or unrelated recommendation is not contest content.
            tag.replace_with(copy.new_string('[外部图片：'+(tag.get('alt') or full)+']'))
        elif full.startswith(('http://','https://','mailto:')):
            tag[attr]=full
        elif raw.startswith('#'):
            tag[attr]=raw
        else:
            tag.attrs.pop(attr,None)
    out.write_text(wrap(title,str(copy),rec['url']))
    offline[rec['path']]=str(out.relative_to(ROOT))
    txt=ROOT/'06_可检索文本'/(p.parent.name+'__'+p.stem+'.txt')
    txt.write_text('来源：'+str(rec['url'])+'\n原始HTML：'+rec['path']+'\n\n'+copy.get_text('\n',strip=True))

for p in sorted((ROOT/'02_主办方公告').glob('*网页检索快照.txt')):
    out=p.with_suffix('.html')
    out.write_text(wrap(p.stem,'<pre>'+html.escape(p.read_text())+'</pre>'))

for line in (ROOT/'07_抓取记录/海报OCR.jsonl').read_text().splitlines():
    obj=json.loads(line)
    if 'path' not in obj:continue
    p=pathlib.Path(obj['path'])
    out=ROOT/'06_可检索文本'/(p.parent.parent.name+'__'+p.stem+'_OCR.txt')
    out.write_text('OCR辅助文字，可能存在误识别，以原始图片为准。\n原图：'+str(p.relative_to(ROOT))+'\n二维码：'+json.dumps(obj.get('barcodes',[]),ensure_ascii=False)+'\n\n'+obj['text'])

groups=defaultdict(list)
for rec in sources:groups[rec['sha256']].append(rec['path'])
duplicates=[{'sha256':h,'paths':paths} for h,paths in groups.items() if len(paths)>1]
(ROOT/'00_索引与说明/下载清单.json').write_text(json.dumps({'created_at':NOW,'sources':sources,'duplicate_groups':duplicates},ensure_ascii=False,indent=2))
(ROOT/'07_抓取记录/页面链接核查.json').write_text(json.dumps(links,ensure_ascii=False,indent=2))
lines=['# 资料来源与下载清单','',f'生成时间：{NOW}。以下为成功保存的原始网络文件；正文转录、中文说明、OCR与索引不混入原始文件统计。','', '| 本地文件 | 类型 | 字节 | SHA-256前16位 | 来源 |','|---|---|---:|---|---|']
for rec in sources:
    path=ROOT/rec['path']
    link=rel_link(path,ROOT/'00_索引与说明')
    lines.append(f"| [{rec['path']}]({link}) | {rec['kind']} | {rec['bytes']:,} | `{rec['sha256'][:16]}` | [原网址]({rec['url']}) |")
lines += ['','## 相同内容与多来源保留','']
for group in duplicates:
    lines.append('- SHA-256 `'+group['sha256']+'`：'+'；'.join(group['paths']))
(ROOT/'00_索引与说明/资料来源与下载清单.md').write_text('\n'.join(lines)+'\n')

intro='<p>2026年第4届庆南AI·SW竞赛资料。原件、不同版本、官方答疑、报名字段、补充公告和图片按来源保存。</p><p><strong>博士生应报一般部。普通报名截止：2026年9月29日中午12:00（韩国时间）。</strong></p><p>详细评分表等尚未公开材料及表单后续步骤存在获取边界，请先读下列说明。</p><ul>'
for p in [ROOT/'README_先读我.md',ROOT/'00_索引与说明/参赛关键信息_中文.md',ROOT/'00_索引与说明/版本差异与未获取项.md',ROOT/'00_索引与说明/资料来源与下载清单.md',ROOT/'04_报名入口/报名表_已读取页面与字段.md']:
    intro+='<li><a href="'+rel_link(p,ROOT)+'">'+html.escape(p.name)+'</a></li>'
intro+='</ul>'
for folder in ['01_昌原大学公告','02_主办方公告','03_赛事官网','04_报名入口','05_补充官方资料','08_媒体及公开转载']:
    intro+='<h2>'+folder+'</h2><ul>'
    for p in sorted((ROOT/folder).rglob('*')):
        if not p.is_file() or p.name.endswith('.metadata.json'):continue
        if p.suffix=='.html' and '离线阅读' not in p.name and '网页检索快照' not in p.name:continue
        intro+='<li><a href="'+rel_link(p,ROOT)+'">'+html.escape(str(p.relative_to(ROOT/folder)))+'</a></li>'
    intro+='</ul>'
(ROOT/'index.html').write_text(wrap('2026 庆南 AI·SW 竞赛｜本地资料索引',intro))
counts=Counter(pathlib.Path(r['path']).suffix.lower() for r in sources)
stats={'created_at':NOW,'source_files':len(sources),'source_bytes':sum(r['bytes'] for r in sources),'extensions':dict(counts),'distinct_payloads':len(groups),'duplicate_groups':len(duplicates),'offline_html':len(offline)}
(ROOT/'00_索引与说明/归档统计.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2))
print(json.dumps(stats,ensure_ascii=False))
