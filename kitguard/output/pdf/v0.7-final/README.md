# KitGuard v0.7.0 — verified Korean submission PDFs

Generated and reviewed on 2026-10-02 KST from the final Markdown sources. The result report is exactly 5 A4 pages (no extra cover); the Agent technical note is exactly 1 A4 page. Every page was rendered and visually inspected. `QA.json` records the inspected PDF/source hashes, all six PNG hashes, complete source-text checks and layout bounds. `BUILD_MANIFEST.json` is the generation record; its initial `visual_qa: pending` state is resolved by the matching hashes in `QA.json`.

- Report body 10.6 pt / table 10.1 pt; technical body 10.3 pt / table 9.8 pt.
- Embedded Arial Unicode MS; no clipped text, overlap, missing Korean glyphs or broken table/footers.
- All 153 observations and the passing independent audit are reflected. I/G/S results are C46/W5/U0, C41/W3/U7, C46/W4/U1; all E/N=0. Full four-category false-ready panels are 5/3/4 photos; narrower source-supported zeros do not replace these results. Neither guarded acceptance nor candidate follow-up criteria passed.
- The bag-revision demonstration is separate from the 51-photo evaluation and uses saved observation times 51.488/46.614 seconds. Automated opinions are not real-user feedback; changing a genuine requirement requires an explicit operator decision and does not resolve a fixed-BOM shortage.
- Local evidence references are readable labels, with original paths preserved in the manifest. They do not become broken relative PDF links when copied into the delivery directory. HTTP(S) links remain clickable. Consult the delivery index and corresponding source-package paths for detailed evidence.
- The planned source archive is named `KitGuard_source_v0.7.0.zip`; its archive hash belongs in the external delivery manifest, not in documents packaged inside that ZIP.

`FINAL` identifies the completed document artifact. It does not certify organizer approval of pre-contest assets, industrial safety, real-user efficacy or submission receipt. Historical/draft PDFs were not modified.

## Rebuild

Run from the project root after changing a source, then render and inspect all pages again:

```sh
/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/v07/build_submission_pdfs.py --report-source docs/v0.7/RESULT_REPORT_KO_FINAL.md --tech-source docs/v0.7/AGENT_TECH_KO_FINAL.md --output-dir output/pdf/v0.7-final --tech-size 10.3 --status final
pdftoppm -r 130 -png output/pdf/v0.7-final/KitGuard_결과보고서_v0.7.pdf output/pdf/v0.7-final/qa/report
pdftoppm -r 150 -png output/pdf/v0.7-final/KitGuard_Agent_기술설명_v0.7.pdf output/pdf/v0.7-final/qa/agent
```

The PDF authoring-operation marker succeeded exactly once for this final creation operation, expected output count 2. No model inference or browser automation was performed for PDF generation or QA.
