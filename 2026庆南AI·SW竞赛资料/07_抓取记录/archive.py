#!/usr/bin/env python3
"""Download public contest resources with provenance; never submit forms.
Run with a JSON array of {url, path, source, kind} entries as the first argument.
Requires beautifulsoup4 for later inspection scripts; downloader is stdlib only.
"""
import concurrent.futures
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG = ROOT / '07_抓取记录/下载记录.jsonl'

def fetch(item):
    item = dict(item)
    target = ROOT / item['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    item['retrieved_at'] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
    item['url'] = urllib.parse.quote(item['url'], safe=':/?=&%#@+;,$!()*\'~-._')
    if target.exists() and not item.get('refresh'):
        item['result'] = 'existing'
        data = target.read_bytes()
    else:
        with tempfile.TemporaryDirectory(prefix='gnict-fetch-') as td:
            body, headers = pathlib.Path(td)/'body', pathlib.Path(td)/'headers'
            cmd = ['curl', '--silent', '--show-error', '--location', '--compressed',
                   '--connect-timeout', '12', '--max-time', '50', '--retry', '1',
                   '--retry-delay', '1', '-A', 'Mozilla/5.0', '-D', str(headers),
                   '-o', str(body), '-w', '%{json}', item['url']]
            if item.get('source'):
                cmd.extend(['--referer', item['source']])
            if item.get('cookie_jar'):
                cmd.extend(['--cookie', item['cookie_jar'], '--cookie-jar', item['cookie_jar']])
            run = subprocess.run(cmd, capture_output=True, text=True)
            try:
                meta = json.loads(run.stdout)
            except ValueError:
                meta = {}
            item.update(http_status=meta.get('http_code'), final_url=meta.get('url_effective'),
                        content_type=meta.get('content_type'), curl_exit=run.returncode)
            if run.returncode or not 200 <= meta.get('http_code', 0) < 300:
                item['result'] = 'failed'
                item['error'] = run.stderr.strip() or f"HTTP {meta.get('http_code')}"
                if body.exists():
                    errfile = ROOT/'07_抓取记录'/(hashlib.sha256(item['url'].encode()).hexdigest()[:12]+'_response.html')
                    errfile.write_bytes(body.read_bytes())
                    item['error_response_path'] = str(errfile.relative_to(ROOT))
                return item
            data = body.read_bytes()
            suffix = target.suffix.lower()
            bad = (suffix == '.hwp' and not data.startswith(bytes.fromhex('d0cf11e0a1b11ae1'))) or (suffix == '.pdf' and not data.startswith(b'%PDF'))
            if bad:
                errfile = ROOT/'07_抓取记录'/(hashlib.sha256(item['url'].encode()).hexdigest()[:12]+'_invalid_response.html')
                errfile.write_bytes(data)
                item.update(result='failed', error='Response has the wrong file signature; not a valid '+suffix+' file', error_response_path=str(errfile.relative_to(ROOT)))
                return item
            target.write_bytes(data)
            item['result'] = 'downloaded'
            htext = headers.read_text(errors='replace')
            item['content_disposition'] = next((x.split(':',1)[1].strip() for x in htext.splitlines() if x.lower().startswith('content-disposition:')), None)
    item['bytes'] = len(data)
    item['sha256'] = hashlib.sha256(data).hexdigest()
    item['magic_hex'] = data[:16].hex()
    target.with_name(target.name+'.metadata.json').write_text(json.dumps(item,ensure_ascii=False,indent=2))
    return item

if __name__ == '__main__':
    items = json.loads(pathlib.Path(sys.argv[1]).read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch,item) for item in items]
        for future in concurrent.futures.as_completed(futures):
            record = future.result()
            with LOG.open('a') as out:
                out.write(json.dumps(record,ensure_ascii=False)+'\n')
            print(json.dumps({k:record[k] for k in ('path','result','http_status','bytes','error') if k in record},ensure_ascii=False),flush=True)
