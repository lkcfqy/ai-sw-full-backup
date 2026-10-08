from pathlib import Path
from copy import deepcopy
import json, hashlib, re
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'01_待补地址与签字'
SOURCE=ROOT.parents[0]/'tmp/hwp_template_check/pyhwp/template.docx'
data=json.loads((ROOT/'工作文件/报名字段正文.json').read_text())
team=json.loads((ROOT/'工作文件/队伍信息_仅本地核对.json').read_text())
leader=team['leader'];member=team['member']
src=Document(SOURCE)
FONT='Apple SD Gothic Neo'

def textformat(p,size=10,bold=False,align=None):
    p.paragraph_format.space_before=Pt(0)
    p.paragraph_format.space_after=Pt(3)
    p.paragraph_format.line_spacing=1.12
    p.paragraph_format.keep_together=False
    p.paragraph_format.keep_with_next=False
    p.paragraph_format.page_break_before=False
    p.paragraph_format.left_indent=Pt(0)
    p.paragraph_format.right_indent=Pt(0)
    p.paragraph_format.first_line_indent=Pt(0)
    if align is not None:p.alignment=align
    for r in p.runs:
        r.font.name=FONT;r.font.size=Pt(size);r.font.bold=bold;r.font.italic=False
        r.font.color.rgb=RGBColor(0,0,0)
        f=r._element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ('ascii','hAnsi','eastAsia','cs'):f.set(qn('w:'+attr),FONT)

def base():
    d=Document(SOURCE)
    body=d._element.body
    for ch in list(body):
        if ch.tag!=qn('w:sectPr'):body.remove(ch)
    for s in d.sections:
        s.top_margin=Cm(1.5);s.bottom_margin=Cm(1.5)
        s.left_margin=Cm(2);s.right_margin=Cm(2)
    for style in d.styles:
        if style.type==1:
            style.font.name=FONT;style.font.size=Pt(10)
    d.core_properties.author=''
    d.core_properties.last_modified_by=''
    return d

def para(d,txt,size=10,bold=False,center=False):
    p=d.add_paragraph(txt)
    textformat(p,size,bold,WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT)
    return p

def heading(d,txt,first=False):
    if not first:d.add_page_break()
    p=para(d,txt,15,True,True)
    p.paragraph_format.space_after=Pt(10)
    return p

def put(t,row,col,text,size=10):
    c=t.cell(row,col)
    c.text=text
    for p in c.paragraphs:textformat(p,size)

def table(d,idx,rows=None,size=9.5):
    el=deepcopy(src.tables[idx]._tbl)
    if rows is not None:
        for i,tr in reversed(list(enumerate(el.tr_lst))):
            if i not in rows:el.remove(tr)
    d._element.body.insert(len(d._element.body)-1,el)
    t=d.tables[-1]
    t.alignment=WD_TABLE_ALIGNMENT.CENTER
    t.autofit=False
    pr=t._tbl.tblPr
    for tag in ('tblpPr','tblOverlap'):
        for item in list(pr.findall(qn('w:'+tag))):pr.remove(item)
    borders=pr.find(qn('w:tblBorders'))
    if borders is None:borders=OxmlElement('w:tblBorders');pr.append(borders)
    for edge in ('top','left','bottom','right','insideH','insideV'):
        elb=borders.find(qn('w:'+edge))
        if elb is None:elb=OxmlElement('w:'+edge);borders.append(elb)
        for k,v in [('val','single'),('sz','5'),('color','888888')]:elb.set(qn('w:'+k),v)
    seen=set()
    for row in t.rows:
        row.height=None
        prr=row._tr.get_or_add_trPr()
        for e in list(prr):
            if e.tag in (qn('w:trHeight'),qn('w:cantSplit')):prr.remove(e)
        for c in row.cells:
            if c._tc in seen:continue
            seen.add(c._tc)
            c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr=c._tc.get_or_add_tcPr()
            mar=tcpr.find(qn('w:tcMar'))
            if mar is None:mar=OxmlElement('w:tcMar');tcpr.append(mar)
            for side,value in [('top','55'),('bottom','55'),('left','80'),('right','80')]:
                e=mar.find(qn('w:'+side))
                if e is None:e=OxmlElement('w:'+side);mar.append(e)
                e.set(qn('w:w'),value);e.set(qn('w:type'),'dxa')
            for p in c.paragraphs:
                textformat(p,size)
                for r in p.runs:
                    for br in r._r.findall(qn('w:br')):
                        if br.get(qn('w:type'))=='page':r._r.remove(br)
    return t

def blocks(c,items,size=10):
    c.text=''
    for i,(label,txt) in enumerate(items):
        p=c.paragraphs[0] if i==0 else c.add_paragraph()
        p.add_run(label+'\n').bold=True
        p.add_run(txt)
        textformat(p,size)
        p.runs[0].bold=True
        p.paragraph_format.space_after=Pt(5)

def gridwidths(t,widths):
    for gc,w in zip(t._tbl.tblGrid.gridCol_lst,widths):gc.set(qn('w:w'),str(int(Cm(w).twips)))
    for row in t.rows:
        start=0
        for tc in row._tr.tc_lst:
            span=tc.grid_span
            tc.get_or_add_tcPr().get_or_add_tcW().set(qn('w:w'),str(int(Cm(sum(widths[start:start+span])).twips)))
            start+=span

app=base()
para(app,'(서식 제1호)',9)
heading(app,'제4회 경남 AI·SW 경진대회 참가 신청서',True)
t=table(app,0,size=9)
gridwidths(t,[2,1,2,5.2,2,4.6])
put(t,0,3,'□ 고등부    □ 대학부    ■ 일반부',9)
put(t,1,3,team['team_name'],10)
put(t,2,3,leader['name'],10);put(t,2,5,leader['phone'],10)
put(t,3,3,'국립창원대학교 대학원\n인공지능융합공학과\n석·박사통합과정 1년차',9)
put(t,3,5,leader['email'],9);put(t,4,3,leader['address'] or '[팀장 상세 주소 입력]',9)
for r in range(5,15):
    for c in (3,5):put(t,r,c,'—',8.5)
put(t,5,3,member['name'],10);put(t,5,5,member['phone'],10)
put(t,6,3,'국립창원대학교 대학원\n인공지능융합공학과\n박사과정 1년차',9)
put(t,6,5,member['city_county'] or '[거주 시·군 입력]',9)
# Keep the one actual team member block; the leader is already in the representative block.
for r in reversed(range(7,15)):
    t._tbl.remove(t.rows[r]._tr)
para(app,'※ 참가 인원: 총 2명 (대표 남청청, 팀원 이개심). 팀명: 해피 / 과제명: KitGuard.',9)
para(app,src.paragraphs[3].text,8.5)
t=table(app,1,size=9)
put(t,2,1,'■ 2. 업무혁신, 생산성향상 AI Agent',9)
# Preserve the category table's content, but give its label column appropriate width.
t.columns[0].width=Cm(3);t.columns[1].width=Cm(13.9)
for row in t.rows:
    row.cells[0].width=Cm(3);row.cells[1].width=Cm(13.9)
para(app,src.paragraphs[6].text,8.5)

heading(app,'개발 계획서')
t=table(app,2,rows=list(range(6)),size=9.5)
put(t,0,1,data['project_title'],11)
blocks(t.cell(1,1),[('목적',data['intro_purpose']),('개발 내용 설명',data['intro_content']),('기대효과',data['intro_effect'])],10)
put(t,2,3,'□ GPT-4  □ Claude  □ Gemini\n□ 국내 LLM  ■ 기타: Qwen3-VL-8B/4B-Instruct\n로컬 후보 비교 후 고정, 신규 학습 없음.',9.5)
put(t,3,3,'□ LangChain  □ AutoGen  □ CrewAI  □ Dify  □ n8n\n■ 기타: FastAPI, MLX-VLM, SQLite, 경량 웹',9.5)
put(t,4,3,'■ Python  ■ JavaScript  □ Java\n■ 기타: HTML, CSS, SQL',9.5)
put(t,5,3,'□ 예  ■ 아니오\nMacBook Pro M5 Pro 64 GB 단독 실행 목표.\nRTX 3080 10 GB 데스크톱은 비교 평가·예비 추론.',9.5)
para(app,'AI 모델과 환경은 개발용 자료로 평가한 뒤 고정하며, 실제 성능과 오프라인 실행 여부는 개발 기간에 검증한다.',9)

heading(app,'개발 계획')
t=table(app,2,rows=[6],size=10)
items=[('개발방법',data['method']),('일정',data['schedule']),('개발방법론',data['methodology']),('목표 성능(정량, 정성)',data['targets']),('As-Is',data['as_is']),('To-Be',data['to_be']),('기타',data['other'])]
blocks(t.cell(0,1),items,10)

heading(app,'역할분담 및 신청 확인')
t=table(app,2,rows=list(range(7,14)),size=9)
put(t,1,1,leader['name'],9)
put(t,1,2,leader['phone'],9);put(t,1,4,'국립창원대학교\n인공지능융합공학과',8.5);put(t,1,5,'팀장: 총괄·요구사항·사용자 실험·제출 관리',8.5)
put(t,2,1,member['name'],9)
put(t,2,2,member['phone'],9);put(t,2,4,'국립창원대학교\n인공지능융합공학과',8.5);put(t,2,5,'실물 데이터·평가·재현성 검증·시연 준비',8.5)
for r in range(3,6):
    for c in (1,2,4,5):put(t,r,c,'—',9)
for r in reversed(range(3,6)):t._tbl.remove(t.rows[r]._tr)
para(app,data['roles'],9.5)
para(app,'제출 예정 자격 증빙: 남청청·이개심 각 재학증명서',10,True)
para(app,'상기와 같이 신청합니다.',11,False,True)
para(app,'2026년 9월 _____일',11,False,True)
para(app,'상기신청인 (대표) 남청청                      (인)',11,False,True)
para(app,'※ 신청시 유의사항',10,True)
for p in src.paragraphs[23:38]:
    if p.text:para(app,p.text,8.5)
apath=OUT/'01_해피_참가신청서_개발계획서_주소서명전.docx'
app.save(apath)

consent_paras=[p.text for p in src.tables[3].cell(1,0).paragraphs if p.text.strip()]
normalize=lambda s:re.sub(r'\s+','',s)
outputs=[str(apath)]
for no,person in enumerate((leader,member),2):
    con=base()
    para(con,'(서식 제2호)',9)
    title=src.tables[3].cell(0,0).text.split('\n')
    heading(con,title[0],True)
    para(con,title[1],10,False,True)
    for txt in consent_paras:
        if txt.startswith('2. 저작권'):con.add_page_break()
        bold=txt.startswith(('1. 개인정보','[1]','[2]','2. 저작권','3. 대회 규정'))
        shown=txt
        if txt.startswith('2026년'):shown='2026년   9월                  일'
        if txt.startswith('성 명'):shown='성    명 : '+person['name']+'                     (인 또는 서명)'
        p=para(con,shown,10.5,bold)
        if bold:p.paragraph_format.space_before=Pt(8)
        if txt.startswith('[ ]'):
            p.paragraph_format.space_before=Pt(4)
            p.paragraph_format.space_after=Pt(10)
        if txt.startswith(('2026년','성 명','(사)')):
            p.alignment=WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before=Pt(12)
    cpath=OUT/f'{no:02d}_참가자_동의서_{person["name"]}_선택서명전.docx'
    con.save(cpath);outputs.append(str(cpath))
    allcons=''.join(p.text for p in con.paragraphs)
    for txt in consent_paras:
        if not txt.startswith('성 명'):assert normalize(txt) in normalize(allcons),txt
    assert sum('[ ] 동의함 [ ] 동의하지 않음' in p.text for p in con.paragraphs)==4
report={'template_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'outputs':outputs,'consent_terms_preserved':True,'consent_choices_unchecked_per_person':4,'intro_characters':sum(len(data[k])for k in ('intro_purpose','intro_content','intro_effect')),'plan_characters':sum(len(data[k])for k in ('method','schedule','methodology','targets','as_is','to_be','other'))}
(ROOT/'工作文件/结构检查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
