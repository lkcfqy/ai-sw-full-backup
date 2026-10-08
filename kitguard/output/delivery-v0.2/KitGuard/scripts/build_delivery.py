"""Collect reviewed final artifacts with an offline index and SHA-256 manifest."""

import hashlib
import html
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/delivery-v0.2"


def main():
    run = json.loads((ROOT / "evaluation-runs/loco_holdout_release_v1/run.json").read_text())
    recording = json.loads((ROOT / "output/demo/recording.json").read_text())
    video = json.loads((ROOT / "output/demo/video-verification.json").read_text())
    assert run["status"] == "completed" and run["completed_cases"] == 48
    assert recording["success"] and not recording["errors"]
    assert video["mp4_duration_seconds"] <= 180
    artifacts = [
        ("韩文完成报告 · 5页", "output/pdf/KitGuard_결과보고서_v0.2.pdf"),
        ("韩文Agent技术说明 · 1页", "output/pdf/KitGuard_Agent_기술설명_v0.2.pdf"),
        ("答辩幻灯片 · 9页", "output/presentations/KitGuard_발표_v0.2.pptx"),
        ("真实本地模型演示 · MP4", "output/demo/KitGuard_real_local_demo.mp4"),
        ("源码与可复算记录", "output/KitGuard_source_v0.2.zip"),
        ("中文交互评估报告", "output/report/KitGuard_中文交互评估.html"),
        ("中文评估正文", "docs/FINAL_EVALUATION.md"),
        ("韩文答辩问答", "docs/JUDGES_QA_KO.md"),
        ("演示来源与边界", "output/demo/README.md"),
        ("实际订单离线证据包", "output/demo/PUBLIC_PHOTO_DEMO_evidence.zip"),
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    records, cards = [], []
    for title, relative in artifacts:
        source = ROOT / relative
        assert source.is_file(), source
        name = f"KitGuard/{relative}" if relative.startswith("docs/") else source.name
        if relative == "output/demo/README.md":
            name = "演示来源说明.md"
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        raw = target.read_bytes()
        records.append(
            {
                "title": title,
                "path": name,
                "source": relative,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        cards.append(f'<a class="card" href="{html.escape(name, quote=True)}">{html.escape(title)}<span>打开文件 ↗</span></a>')
    for relative in ("output/demo/recording.json", "output/demo/video-verification.json", "output/source-package-verification.json"):
        source = ROOT / relative
        assert source.is_file(), source
        target = OUT / source.name
        shutil.copy2(source, target)
        raw = target.read_bytes()
        records.append({"path": source.name, "source": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    exact = run["summary"]["count_exact"]
    page = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>KitGuard v0.2 交付入口</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#f4f7f5;color:#173630;font:16px/1.7 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:64px 24px}}small{{letter-spacing:.12em;color:#356e60}}h1{{font-size:44px;line-height:1.2}}p{{max-width:850px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:32px 0}}.card{{background:white;border:1px solid #cdded5;padding:20px;border-radius:14px;color:#124e40;text-decoration:none;font-weight:650}}.card:hover,.card:focus{{outline:2px solid #1e806b}}.card span{{display:block;color:#678075;font-size:13px;font-weight:400}}.note{{border-left:4px solid #b98a36;padding:16px 20px;background:#fff5df}}footer{{font-size:13px;color:#566d64}}@media(max-width:600px){{.grid{{grid-template-columns:1fr}}h1{{font-size:32px}}main{{padding-top:32px}}}}</style>
<main><small>해피 · KITGUARD · LOCAL DELIVERY v0.2</small><h1>开发成果与自检材料</h1><p>可运行的本地备料核验工作台：照片观察、程序计数、订单改版、证据审计和离线导出。当前完整留出结果为 <strong>{exact['numerator']}/{exact['denominator']}（{exact['rate']:.1%}）</strong>，范围为预先选定的公开静态照片。</p><p><a href="http://127.0.0.1:8765">打开本机工作台</a> · <a href="http://127.0.0.1:4173">打开本机交互报告</a>（需要相应服务正在运行；下方文档和视频可离线查看。）</p><div class="grid">{''.join(cards)}</div><p class="note">这是2026-09-26完成的内部技术交付，没有代为报名或提交。公开图片不证明现场补件或生产收益；名次不能保证。正式开发期、赛前资产使用与9月29日公布的最终材料要求仍须核实。9月29日的报名文件位于项目上层“报名材料_해피_2026-09-29”，与这里的最终成果材料不同。</p><footer>文件完整性见 <a href="SHA256.json">SHA256.json</a>，源码验收见 <a href="source-package-verification.json">验证记录</a>。权重和数据原始归档保存在原项目与共享目录，没有塞入源码ZIP。演示使用MVTec公开照片，来源与许可随附。</footer></main></html>"""
    (OUT / "index.html").write_text(page)
    records.append(
        {
            "path": "index.html",
            "bytes": len(page.encode()),
            "sha256": hashlib.sha256(page.encode()).hexdigest(),
        }
    )
    (OUT / "SHA256.json").write_text(
        json.dumps({"created_at": datetime.now(UTC).isoformat(), "files": records}, ensure_ascii=False, indent=2)
        + "\n"
    )
    print(json.dumps({"output": str(OUT), "files": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
