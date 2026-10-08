#!/usr/bin/env python3
"""Reproduce HWP XML and complete text extraction (including table cells).
Requires pyhwp and six. Pass the path to hwp5proc, or put it on PATH.
"""
import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

root=pathlib.Path(__file__).resolve().parents[1]
tool=sys.argv[1] if len(sys.argv)>1 else shutil.which('hwp5proc')
if not tool:raise SystemExit('Install pyhwp and six, then provide the hwp5proc path.')
for p in sorted(root.rglob('*.hwp')):
    relative=p.relative_to(root)
    prefix=relative.parts[0]+('__仁济大学' if '仁济大学' in str(relative) else '')
    name=prefix+'__'+p.stem
    xml=subprocess.run([tool,'xml',str(p)],check=True,capture_output=True).stdout
    xmlpath=root/'06_可检索文本/XML'/(name+'.xml')
    xmlpath.parent.mkdir(parents=True,exist_ok=True)
    xmlpath.write_bytes(xml)
    parts=[]
    def walk(el):
        if el.tag=='Text':
            parts.append(el.text or '')
            return
        for c in el:walk(c)
        if el.tag=='Paragraph':parts.append('\n')
    walk(ET.fromstring(xml))
    (root/'06_可检索文本'/(name+'.txt')).write_text('提取说明：由原始HWP解析所得，包含表格单元格文字；排列仅供检索，不代替原始版式。\n来源文件：'+str(relative)+'\n\n'+''.join(parts))
    print(relative)
