"""Export a searchable font-compatible copy with bundled LibreOffice only."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/submission-final-20261005"
BUILD = ROOT / "tmp/submission-slides-20261005"
RUNTIME = Path("/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies")
SOFFICE = RUNTIME / "bin/override/soffice"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    import os

    source = OUT / "KitGuard_presentation_9slides.pptx"
    run = BUILD / f"pdf-final-{time.time_ns()}"
    run.mkdir(parents=True)
    config = run / "fontconfig.xml"
    config.write_text(
        '<?xml version="1.0"?>\n<fontconfig><dir>/System/Library/Fonts/Supplemental</dir>'
        f'<cachedir>{run / "font-cache"}</cachedir></fontconfig>'
    )
    env = dict(os.environ, FONTCONFIG_FILE=str(config))
    profile = run / "lo-profile"
    subprocess.run([
        str(SOFFICE), f"-env:UserInstallation={profile.as_uri()}", "--headless",
        "--convert-to", "pdf", "--outdir", str(run), str(source)
    ], env=env, check=True)
    candidate = run / "KitGuard_presentation_9slides.pdf"
    pdf = PdfReader(candidate)
    assert len(pdf.pages) == 9
    text_checks = []
    with zipfile.ZipFile(source) as archive:
        for i, page in enumerate(pdf.pages, 1):
            text = "".join(page.extract_text().split())
            slide = ET.fromstring(archive.read(f"ppt/slides/slide{i}.xml"))
            expected = [e.text or "" for e in slide.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t")]
            missing = [s for s in expected if "".join(s.split()) not in text]
            assert not missing, (i, missing)
            text_checks.append({"slide": i, "expected_text_segments": len(expected), "missing": []})
    destination = OUT / "KitGuard_presentation_9slides.pdf"
    shutil.copy2(candidate, destination)
    receipt = {
        "version": "0.9.0.dev4", "material_revision": "20261005", "pages": 9,
        "source_pptx_sha256": sha(source), "pdf_sha256": sha(destination),
        "renderer": str(SOFFICE), "font": "Arial Unicode MS",
        "font_source": "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "font_config_scope": "Private build file only; no installed runtime or system settings changed",
        "all_native_text_preserved": text_checks, "visual_qa": "pending",
        "native_powerpoint_verified": False,
    }
    (OUT / "presentation-pdf-build.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"output": str(destination), "pages": 9, "text_segments_preserved": True}))


if __name__ == "__main__":
    main()
