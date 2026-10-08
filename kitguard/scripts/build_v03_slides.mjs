#!/usr/bin/env node
/**
 * Korean v0.3 supplemental deck. CPU only; no model or benchmark invocation.
 * A completed gate + independent audit + actual API receipt are mandatory.
 * Uses ArtifactTool native editable objects and the Presentations finalizer.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SKILL = '/Users/lkc/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations';
const RUNTIME = '/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const PYTHON = path.join(RUNTIME, 'python/bin/python3');
const FONT = 'Apple SD Gothic Neo';
const DEFAULT_DEV = 'evaluation-runs/v03_guarded_integrated_development_v1/gate_report_v1.json';
const DEFAULT_DEV_AUDIT = 'test-results/audit/v03-guarded-integrated-development-analysis.json';
const LABELS = ['C', 'W', 'U', 'E'];
const args = process.argv.slice(2);
const has = flag => args.includes(flag);
const value = (flag, fallback) => { const i = args.indexOf(flag); return i < 0 ? fallback : args[i + 1]; };
const absolute = filename => path.resolve(ROOT, filename);
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const digest = async filename => sha(await fs.readFile(filename));
const read = async filename => JSON.parse(await fs.readFile(filename, 'utf8'));
const rel = filename => path.relative(ROOT, filename);
const frac = metric => metric.denominator ? `${metric.numerator}/${metric.denominator}` : '해당 없음';
const percent = rate => `${(rate * 100).toFixed(1)}%`;
const seconds = ms => `${(ms / 1000).toFixed(2)}초`;
const vector = m => LABELS.map(k => m[k]).join(' / ');
const decisionKO = v => ({ready: '수량 일치·본인 확인 대기', correct: '수량 조정 필요', recapture: '다시 촬영 필요'}[v] ?? v ?? '결과 없음');

if (has('--help')) {
  console.log(`Usage: node scripts/build_v03_slides.mjs
  --gate <completed 64-image gate.json> --audit <independent 64-image audit.json>
  --demo-receipt <completed real-API browser/result.json>
  --engineering-junit <completed regression.xml>
  --deployment-mode spatial_inventory|spatial_guarded
  [--development-gate ${DEFAULT_DEV}]
  [--development-audit ${DEFAULT_DEV_AUDIT}]
  [--workbench-screen bag-revision-r1-workspace.png]
  [--audit-screen bag-revision-r2-audit.png]
  [--output output/presentations/KitGuard_검증보충_v0.3.pptx]
  [--build-dir .presentation-v03-build/final-v1]
  [--validate-only]
  --development-only checks only completed development evidence and produces no PPT.
Missing, incomplete, mismatched, or changed evidence prevents PPT creation.
The shared read-only evidence validator is scripts/build_v03_korean_addendum.py.
Marker for this artifact operation was invoked once before authoring; the builder does not invoke it again.`);
  process.exit(0);
}

function pythonBundle() {
  const config = {
    development_gate: absolute(value('--development-gate', DEFAULT_DEV)),
    gate: value('--gate') ? absolute(value('--gate')) : null,
    audit: value('--audit') ? absolute(value('--audit')) : null,
    engineering_junit: value('--engineering-junit') ? absolute(value('--engineering-junit')) : null,
    demo_receipt: value('--demo-receipt') ? absolute(value('--demo-receipt')) : null,
  };
  if (!has('--development-only')) {
    for (const [key, val] of Object.entries(config)) assert.ok(val, `Missing required evidence: ${key}`);
  }
  // Reuse the exact document validator rather than creating divergent scoring logic.
  const code = `import json,sys,types\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nimport build_v03_korean_addendum as v\ncfg=json.loads(sys.argv[2]); args=types.SimpleNamespace(**{k:Path(x) if x else None for k,x in cfg.items()})\nif sys.argv[3]=='development':\n d={'development':v.validate_gate(args.development_gate,'development',v.read_json(v.PROTOCOL))}\nelse:\n d=v.load_bundle(args)\nfor k in ('development','gate'):\n if k in d: d[k].pop('cases',None)\nprint(json.dumps(d,ensure_ascii=False,allow_nan=False))\n`;
  const result = spawnSync(PYTHON, ['-c', code, path.join(ROOT, 'scripts'), JSON.stringify(config), has('--development-only') ? 'development' : 'all'], {encoding: 'utf8', maxBuffer: 8 * 1024 * 1024});
  assert.equal(result.status, 0, `Evidence validation rejected the build:\n${result.stderr}`);
  return {data: JSON.parse(result.stdout), config};
}

async function validateDevelopmentAudit(gate) {
  const filename = absolute(value('--development-audit', DEFAULT_DEV_AUDIT));
  const audit = await read(filename);
  assert.equal(audit.schema_revalidated, 28);
  assert.equal(audit.input_audit?.verified, true);
  assert.equal(audit.run_sha256, gate.run_json_sha256);
  assert.equal(audit.predictions_sha256, gate.predictions_sha256);
  assert.equal(audit.manifest_sha256, gate.manifest_sha256);
  assert.equal(audit.correct_actionable?.denominator, 28);
  for (const [a, g] of [['first_pass', 'baseline'], ['final', 'candidate']]) {
    assert.equal(audit[a].images, 28);
    assert.equal(audit.correct_actionable[a === 'final' ? 'final' : 'first_pass'], gate[g].C);
    assert.equal(audit[a].wrong_actionable_count.numerator, gate[g].W);
    assert.equal(audit[a].errors.numerator, gate[g].E);
    assert.equal(audit[a].actionable_coverage.numerator, gate[g].C + gate[g].W);
  }
  return {path: filename, sha256: await digest(filename), audit};
}

function validatePairedAudit(audit, gate) {
  for (const [a, g] of [['first_pass', 'baseline'], ['final', 'candidate']]) {
    assert.equal(audit[a].actionable_coverage.numerator, gate[g].C + gate[g].W);
  }
  assert.equal(audit.transitions.correct_abstained, gate.comparison.correct_to_abstention);
  assert.equal(audit.transitions.wrong_blocked, gate.comparison.blocked_baseline_wrong);
  assert.equal(audit.final.latency_ms.median, gate.candidate.latency_ms.median);
}

async function validateActualDemo(data, filename) {
  const d = data.demo;
  assert.ok(d.finished_at && d.started_at);
  assert.equal(d.planned_instruction_calls, 1, 'Natural-language receipt contract is required');
  assert.equal(d.attempted_instruction_calls, 1);
  assert.equal(d.planned_model_requests, 5);
  assert.equal(d.attempted_model_requests, 5);
  assert.equal(d.planned_inspections, 4);
  assert.equal(d.attempted_inspections, 4);
  const language = d.instruction_outcome;
  assert.ok(language && ['proposal_returned', 'clarification', 'proposal_mismatch', 'execution_error'].includes(language.status));
  assert.equal(typeof language.fallback_used, 'boolean');
  assert.ok(language.approval && ['natural_proposal', 'structured_fallback'].includes(language.approval.via));
  assert.equal(language.approval.http_status, 200);
  assert.equal(language.approval.to_revision, 2);
  if (language.approval.via === 'natural_proposal') {
    assert.equal(language.status, 'proposal_returned');
    assert.equal(language.proposal_matches_intended, true);
    assert.equal(language.fallback_used, false);
  } else assert.equal(language.fallback_used, true);
  const directory = path.dirname(filename);
  for (const receipt of d.http_receipts) {
    assert.ok(!path.isAbsolute(receipt.file) && !receipt.file.split(/[\\/]/).includes('..'));
    const r = await read(path.join(directory, receipt.file));
    if (r.response_file && r.response_sha256) {
      assert.ok(!path.isAbsolute(r.response_file) && !r.response_file.split(/[\\/]/).includes('..'));
      assert.equal(await digest(path.join(directory, r.response_file)), r.response_sha256);
    }
  }
  for (const row of d.outcomes) {
    if (row.status === 'recorded') {
      assert.equal(row.runtime_mode, 'spatial_guarded');
      assert.equal(row.backend, 'mlx');
      assert.ok(row.response?.check);
    }
  }
  const samples = [...new Set(d.outcomes.map(row => row.sample))];
  assert.equal(samples.length, 3);
  for (const sample of samples) {
    assert.equal(path.basename(sample), sample);
    const order = await read(path.join(directory, 'orders', `${sample}-final.json`));
    assert.equal(order.demo_source?.physical_completion_allowed, false);
    assert.deepEqual(order.completions, [], 'Public demo must not claim physical completion');
    if (sample === 'bag-revision') {
      assert.equal(order.revision, 2);
      assert.equal(order.photos[0].source_sha256, order.photos.at(-1).source_sha256);
      assert.ok(order.checks.filter(check => check.revision === 1).every(check => check.valid === false));
    }
  }
  const assets = {};
  for (const [key, flag, fallback] of [
    ['workbench', '--workbench-screen', 'bag-revision-r1-workspace.png'],
    ['audit', '--audit-screen', 'bag-revision-r2-audit.png'],
  ]) {
    const basename = value(flag, fallback);
    assert.equal(path.basename(basename), basename, 'Screenshot must be from this actual run screenshots/');
    assert.ok(basename.endsWith('.png'));
    const image = path.join(directory, 'screenshots', basename);
    const bytes = await fs.readFile(image);
    assert.equal(bytes.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
    assets[key] = {path: image, sha256: sha(bytes)};
  }
  assert.notEqual(assets.workbench.sha256, assets.audit.sha256, 'Use distinct actual software views');
  return assets;
}

async function loadFailedExperiment() {
  const directory = path.join(ROOT, 'evaluation-runs/v03_screws_identity_probe_v1');
  const run = await read(path.join(directory, 'run.json'));
  assert.equal(run.status, 'completed');
  assert.equal(run.expected_cases, 12);
  assert.equal(run.completed_cases, 12);
  assert.equal(run.source_changed_during_run, false);
  assert.equal(run.source_inputs_changed_during_run, false);
  assert.deepEqual(run.source_hashes_after, run.source_hashes);
  const m = run.summary.filtered;
  assert.equal(m.images, 12);
  assert.equal(m.splits.development, 12);
  const rows = (await fs.readFile(path.join(directory, 'predictions.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse);
  assert.deepEqual(rows.map(r => r.case_id), run.case_ids);
  return {summary: m, source: {path: path.join(directory, 'run.json'), sha256: await digest(path.join(directory, 'run.json'))}};
}

function groupRows(gate, stageKO) {
  const label = key => key.includes('normal') ? 'LOCO 정상' : key.includes('anomal') ? 'LOCO 수량 이상' : key.startsWith('loco') ? 'LOCO' : key.startsWith('screws') ? 'Screws' : key;
  return Object.entries(gate.groups).map(([key, row]) => [
    `${stageKO} ${label(key)} ${row.candidate.images}장`,
    vector(row.baseline), vector(row.candidate),
    percent(row.candidate.actionable_coverage.rate), seconds(row.candidate.latency_ms.median),
  ]);
}

async function build(data, config, developmentAudit, assets, failed) {
  const output = absolute(value('--output', 'output/presentations/KitGuard_검증보충_v0.3.pptx'));
  const buildDir = absolute(value('--build-dir', '.presentation-v03-build/final-v1'));
  assert.notEqual(output, path.join(ROOT, 'output/presentations/KitGuard_발표_v0.2.pptx'));
  try { await fs.access(output); throw new Error(`Refusing to overwrite an existing final deck: ${output}`); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  await fs.mkdir(buildDir, {recursive: true});
  await fs.mkdir(path.dirname(output), {recursive: true});
  const runtimeRequire = createRequire(path.join(RUNTIME, 'node/package.json'));
  process.env.RUNTIME_NODE_MODULES = path.join(RUNTIME, 'node/node_modules');
  const {Presentation, PresentationFile, FileBlob} = await import(pathToFileURL(runtimeRequire.resolve('@oai/artifact-tool')).href);
  const {finalizePresentation} = await import(pathToFileURL(path.join(SKILL, 'container_tools/artifact_tool_utils.mjs')).href);
  const presentation = Presentation.create({slideSize: {width: 1280, height: 720}});
  const p = presentation, dark = '#153B39', teal = '#00695E', muted = '#526963', paper = '#F8FAF6';
  const txt = (s, text, x, y, w, h, size = 28, color = dark, bold = false) => {
    const box = s.shapes.add({geometry: 'textbox', name: text.slice(0, 64), position: {left:x, top:y, width:w, height:h}, fill:'none', line:{fill:'none', width:0}});
    box.text = text; box.text.style = {typeface: FONT, fontSize:size, color, bold, autoFit:'none', wrap:true}; return box;
  };
  const slide = (n, title) => {const s=p.slides.add();s.background.fill=paper;txt(s,title,64,44,1148,75,43,dark,true);txt(s,`KitGuard v0.3  ·  ${n}/6`,64,681,1148,25,18,muted);return s;};
  const note = (s, text) => s.speakerNotes.textFrame.setText(text);
  const image = async (s, file, x, y, w, h, alt) => s.images.add({blob:new Uint8Array(await fs.readFile(file)), contentType:'image/png', fit:'contain', position:{left:x,top:y,width:w,height:h},alt});
  const table = (s, values, x, y, width, height, widths, size=24) => {
    const t=s.tables.add({rows:values.length, columns:values[0].length, left:x,top:y,width,height,columnWidths:widths,values});
    t.borders.assign({style:'solid',fill:'#CCDBD4',width:1});
    for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
      const cell=t.getCell(r,c); cell.fill=r===0?dark:(r%2===0?'#EDF3EC':'#FFFFFF');
      cell.text.style={typeface:FONT,fontSize:size,bold:r===0,color:r===0?'#FFFFFF':dark,autoFit:'none'};
    } return t;
  };
  const src = Object.entries(data.sources).map(([k,v])=>`${k}: ${rel(v.path)} SHA256 ${v.sha256}`).join('\n');
  const publicScope = 'MVTec LOCO AD and MVTec Screws, CC BY-NC-SA 4.0. https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad ; https://www.mvtec.com/research-teaching/datasets/mvtec-screws ; https://creativecommons.org/licenses/by-nc-sa/4.0/ . Public development photographs shown inside actual API screenshots, not new field photographs. Same-source grouping is not independent factories; pretrained overlap unknown. Original author labels and conservative exact count projection, never AI ground truth.';
  const dev=data.development, held=data.gate, demo=data.demo;
  const mode=value('--deployment-mode');
  assert.ok(['spatial_inventory','spatial_guarded'].includes(mode),'Explicit deployment decision is required');
  if(mode==='spatial_guarded')assert.equal(held.default_adoption_eligible,true,'Cannot call a failed candidate the default');
  const adopted = mode === 'spatial_guarded';
  const language=demo.instruction_outcome;
  const nlText=language.approval.via==='natural_proposal'?'한국어 제안 후 명시적 승인':'자연어 응답 후 구조화 입력으로 승인';
  // 1: the software's business purpose, with actual evidence visible.
  {
    const s=slide(1,'KitGuard, 수량 확인을 검토 가능한 작업으로');
    txt(s,'잘못된 확정을 줄이고\n다음 확인을 남깁니다',64,159,543,119,41,teal,true);
    txt(s,'목표 수량과 사진 관찰을 분리\n애매하면 촬영 또는 수량 수정 안내\n새 버전과 증거를 읽기 전용 기록으로',64,333,538,177,29);
    await image(s,assets.audit.path,652,141,562,373,'Actual API audit screen, public development-photo demo');
    txt(s,'v0.3: 회전 일치 확인 · 국소 정체 확인\n이전 결과 무효화 · 오프라인 증거 보고서',652,545,562,80,26,teal,true);
    txt(s,'공개 개발 사진을 쓴 실제 앱 실행입니다. 실물 보충·출하 완료는 수행하지 않았습니다.',64,634,1148,35,22,muted);
    note(s,`Business intent is an implemented workflow, not measured operator savings. Current deployment mode: ${mode}.\n${src}\nScreenshot ${assets.audit.path} SHA256 ${assets.audit.sha256}\n${publicScope}`);
  }
  // 2: native editable architecture, explicitly correlated model calls.
  {
    const s=slide(2,'목표 수량을 보지 않는 단계적 관찰');
    const stages=[['1','공간 목록','원본의 물체별 분류와 위치\n코드가 목록에서 수량을 계산'],['2','회전 일치 확인','같은 사진을 반시계 90° 회전\n두 관찰이 어긋나면 불확실'],['3','국소 정체 확인','너트·와셔 후보 부분 확대\n정체·구멍 판단 충돌 시 보류']];
    stages.forEach(([n,title,body],i)=>{const x=64+i*390;s.shapes.add({geometry:'rect',position:{left:x,top:185,width:368,height:243},fill:'#FFFFFF',line:{fill:'#A9C7BB',width:1}});txt(s,n,x+20,201,70,52,38,teal,true);txt(s,title,x+20,265,329,43,30,dark,true);txt(s,body,x+20,328,330,88,26);});
    txt(s,'모델 입력에 BOM 목표 없음',64,465,530,43,31,teal,true);
    txt(s,'확정 수량을 다른 정수로 고치지 않음',652,465,562,43,31,teal,true);
    txt(s,'승인된 요구와의 비교는 관찰 뒤에 규칙으로 수행합니다.\n충돌 범주의 수량만 null로 바꾸고 사용자에게 다시 확인을 요청합니다.',64,530,1148,88,28);
    txt(s,'모두 같은 27B 모델의 관련된 호출입니다. 추정 좌표·구멍 판단은 실측 진실이 아니며 확대 보간은 정보를 만들지 않습니다.',64,630,1148,47,22,muted);
    note(s,`Native editable architecture. Model Qwen3.6-27B MLX 4-bit,1536px. Spatial inventory max900 tokens per orientation; identity geometry v2 uses only model-selected ring candidates. Same model and same photograph, not independent evidence. Null-only candidate policy, no integer correction. Source kitguard/identity.py, consensus.py, vision.py and schemas.py; actual frozen hashes in gate reports.\n${src}`);
  }
  // 3: one complete denominator per photograph, paired within the same run.
  {
    const s=slide(3,'맞힌 수와 거절한 수를 함께 공개');
    txt(s,'C 정확한 확정   W 틀린 확정   U 불확실·보류   E 실행 오류',64,133,1148,38,25,teal,true);
    const rows=[['자료·사진 수','같은 실행 첫 관찰\nC / W / U / E','최종 확인\nC / W / U / E','최종 확정 비율','전체 시간 중앙값'],...groupRows(dev,'개발'),...groupRows(held,'새 평가')];
    table(s,rows,64,190,1148,340,[286,225,225,185,227],23);
    txt(s,`새 평가 ${held.completed_images}장: ${held.candidate.C}C · ${held.candidate.W}W · ${held.candidate.U}U · ${held.candidate.E}E\n첫 관찰 오류 ${held.comparison.blocked_baseline_wrong}건 차단 · 정확했던 ${held.comparison.correct_to_abstention}건도 보류`,64,552,1148,71,29,teal,true);
    txt(s,'첫 관찰은 같은 실행의 관찰 결과이며 별도 전체 지연 측정은 없습니다. 표의 시간에는 업로드 처리와 모델 관찰을 포함하고 사람 작업은 제외합니다.',64,634,1148,43,21,muted);
    note(s,`All C/W/U/E rows are mutually exclusive and sum to every planned image. Development28 selected the method; newholdout64 never folded into that denominator. Rates are descriptive, not a population performance estimate. Final latency is actual integrated app-upload/observe duration including cold first row; first-pass baseline has no separately measured total latency. Guarded inspect API timing is shown separately on slide5. No pooling model-only, historical replay combined, or detector CPU timing.\n${src}\nDevelopment audit ${developmentAudit.path} SHA256 ${developmentAudit.sha256}\n${publicScope}`);
  }
  // 4: unsuccessful alternatives remain inspectable, with incomparable metrics named.
  {
    const s=slide(4,'실패한 대안도 남기고 채택 조건을 고정');
    const detectors=data.detectors.map(d=>[d.label,`${d.summary.loco.exact_count_images}/16 · ${d.summary.screws.exact_count_images}/12`,'현 설정은 미채택']);
    const f=failed.summary;
    table(s,[['완료한 개발 실험','LOCO / Screws 수량 전부 정확','판단'],...detectors,['초기 정체 확인 v1',`Screws ${frac(f.count_exact)} · 틀린 확정 ${f.wrong_actionable_count.numerator}건`,'오류가 남아 수정'],['통합 v2',`${dev.groups.loco16.candidate.C}/16 · ${dev.groups.screws12.candidate.C}/12`,'새 평가 전에 고정']],64,152,1148,289,[335,509,304],25);
    txt(s,adopted?'내부 사전 기준 충족 후 강화 확인을 기본값으로 채택':'기본값은 유지하고 강화 확인은 후보로 보존',64,478,1148,55,34,teal,true);
    txt(s,`새 평가 문턱 ${held.stage_passed?'통과':'미통과'} · 오류 차단 이득 ${held.comparison.demonstrated_error_blocking_benefit?'관측':'입증되지 않음'}\n현재 모드: ${mode}`,64,547,1148,74,28);
    txt(s,'탐지기는 수량 정확도만 비교합니다. 업무 확정 지표는 해당 없습니다. CPU 시간·과거 결과 재생 시간은 통합 지연과 별도로 기록합니다.',64,625,1148,48,21,muted);
    note(s,`These detector trials do not establish the best achievable detector performance: specific pretrained settings, no task-specific training. Their business-actionability metrics are null, not0. Identityv1 is replay on development outputs, not integrated end-to-end timing. Frozen research gates are not contest scoring and do not guarantee first place or shipping safety.\n${src}\nFailed identity run ${failed.source.path} SHA256 ${failed.source.sha256}`);
  }
  // 5: screenshot remains whole and reasonably large, evidence levels separated.
  {
    const s=slide(5,'실제 API로 변경·재검사·기록까지');
    await image(s,assets.workbench.path,64,143,760,475,'Actual Korean workbench after local MLX inspection on public development photo');
    txt(s,`${data.engineering.passed}/${data.engineering.total} 공학 테스트`,864,149,350,48,32,teal,true);
    txt(s,'상태·입력·기록 동작 검증\n시각 정확도와 다른 분모',864,206,350,78,25);
    const recorded=demo.outcomes.filter(o=>o.status==='recorded').length;
    txt(s,`시각 검사 요청 ${demo.attempted_inspections}회`,864,310,350,45,30,teal,true);
    const r1=demo.outcomes.find(o=>o.sample==='bag-revision'&&o.revision===1);
    const r2=demo.outcomes.find(o=>o.sample==='bag-revision'&&o.revision===2);
    txt(s,`${nlText}\nR2에 같은 공개 사진 재업로드\nR1 ${seconds(r1.request_wall_ms)} / R2 ${seconds(r2.request_wall_ms)}\n자연어 제안 ${seconds(language.request_wall_ms)}`,864,367,350,151,25);
    txt(s,`검사 기록 ${recorded}회 · 실행 오류 ${demo.attempted_inspections-recorded}회\n자연어 ${demo.attempted_instruction_calls}회 · 실물 완료 0건`,864,549,350,67,25,dark,true);
    txt(s,'이 시연은 이미 사용한 공개 개발 사진입니다. 주문만 변경했으며 새로운 현장 촬영이나 실물 보충을 입증하지 않습니다.',64,634,1148,45,22,muted);
    const observations=demo.outcomes.map(o=>`${o.sample}R${o.revision}: HTTP${o.http_status}, ${decisionKO(o.decision)}, actual request ${(o.request_wall_ms/1000).toFixed(3)}s`).join('\n');
    note(s,`Actual API demonstration separate from benchmark. ${observations}\nNL status ${language.status}, fallback ${language.fallback_used}, approval via ${language.approval.via}; no claim that4visual endpoint requests equals4low-level VLM generations: each guarded request can include multiple correlated calls, plus1NLrequest. Browser-operated explicit approval is not a human-user study. No physical completions. Screenshot ${assets.workbench.path} SHA256 ${assets.workbench.sha256}\n${src}\n${publicScope}`);
  }
  // 6: a bounded, testable next step instead of an unearned claim of readiness.
  {
    const s=slide(6,'다음 증거는 실제 작업에서 확보');
    txt(s,'현재 입증한 것은 공개 실사진의 수량 확인과\n소프트웨어 상태·감사 기록의 연결입니다.',64,148,1148,105,36,teal,true);
    const next=[['현장 촬영','조명·가림·겹침·브래킷 양성 사례를 포함해 새로 촬영'],['실물 수정 전후','실제로 더하고 뺀 뒤 새 사진과 담당자 확인을 연결'],['작업자 비교','완료 시간·재촬영 수·잘못된 수량 확정을 함께 측정']];
    table(s,[['다음 검증','확보할 증거'],...next],64,294,1148,220,[279,869],27);
    txt(s,'이번 표본에서 오류를 관측하지 않아도 현장 위험은 남습니다.',64,548,1148,45,31,dark,true);
    txt(s,'공개 데이터 사전학습 중복은 미확인 · 다른 공장 일반화 미검증\n실제 개발 시작 2026.09.26 · 사전 개발 규정과 참가 자격은 주최 측 확인 필요',64,610,1148,66,25,muted);
    note(s,`Future field plan, not claimed executed work. No measured physical correction, user efficiency, novel acquisition domain, bracket-positive validation or commercial-use permission. Public data CC BY-NC-SA4.0 requires attribution/noncommercial/sharealike compliance. This supplemental deck is a research/development record, not ready-to-submit authorization. Official judging weights are not fabricated. AI-assisted implementation documented; actual predevelopment September26 preserved.\n${src}\n${publicScope}`);
  }
  const sourceReceipt={created_at:new Date().toISOString(),builder:{path:rel(fileURLToPath(import.meta.url)),sha256:await digest(fileURLToPath(import.meta.url))},shared_validator:{path:'scripts/build_v03_korean_addendum.py',sha256:await digest(path.join(ROOT,'scripts/build_v03_korean_addendum.py'))},sources:data.sources,development_audit:{path:developmentAudit.path,sha256:developmentAudit.sha256},failed_identity:failed.source,screenshots:assets,deployment_mode:mode,slides:6,marker:'Successfully invoked once before authoring this artifact operation; not repeated by builder'};
  await fs.writeFile(path.join(buildDir,'sources.json'),JSON.stringify(sourceReceipt,null,2)+'\n');
  await fs.writeFile(path.join(buildDir,'validated-metrics.json'),JSON.stringify({development:dev,holdout:held,engineering:data.engineering,demo_status:demo.status,instruction_outcome:language},null,2)+'\n');
  const candidate=path.join(buildDir,'candidate.pptx');
  await (await PresentationFile.exportPptx(p)).save(candidate);
  await fs.writeFile(path.join(buildDir,'source.json'),JSON.stringify(p.toProto()));
  const owners=[3,4,6];
  await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath:output,pythonExecutable:PYTHON,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...owners.flatMap(n=>['--require-native-table-slide',String(n)])],explicitTotalSlideCount:6,requiredNativeTableOwnerSlides:owners,requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(buildDir,'validation.json')});
  // Import and render the final file, not only the pre-export presentation.
  const rendered=await PresentationFile.importPptx(await FileBlob.load(output));
  const renderDir=path.join(buildDir,'render-final');
  await fs.mkdir(renderDir,{recursive:true});
  for(let i=0;i<6;i++) {
    const item=rendered.slides.getItem(i);
    const preview=await rendered.export({slide:item,format:'png',scale:1.5});
    await fs.writeFile(path.join(renderDir,`slide-${i+1}.png`),new Uint8Array(await preview.arrayBuffer()));
  }
  console.log(JSON.stringify({status:'finalized_rendered_requires_visual_QA',output,build_dir:buildDir,render_dir:renderDir,slides:6,sha256:await digest(output)},null,2));
}

try {
  const {data,config}=pythonBundle();
  const developmentAudit=await validateDevelopmentAudit(data.development);
  validatePairedAudit(developmentAudit.audit,data.development);
  if(has('--development-only')) {
    console.log(JSON.stringify({status:'completed_development_sources_validated',images:28,counts:vector(data.development.candidate),artifact_created:false,holdout_read:false}));
  } else {
    validatePairedAudit(data.audit,data.gate);
    assert.equal(data.engineering.failed,0);assert.equal(data.engineering.errors,0);assert.equal(data.engineering.skipped,0);
    const assets=await validateActualDemo(data,config.demo_receipt);
    const failed=await loadFailedExperiment();
    if(has('--validate-only'))console.log(JSON.stringify({status:'all_completed_sources_validated',development_images:28,holdout_images:64,engineering:data.engineering,demo_status:data.demo.status,artifact_created:false}));
    else await build(data,config,developmentAudit,assets,failed);
  }
} catch(error) {
  console.error(`No presentation produced: ${error.message}`);
  process.exitCode=2;
}
