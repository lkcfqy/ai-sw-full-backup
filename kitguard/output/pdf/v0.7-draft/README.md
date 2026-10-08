# KitGuard v0.7 Korean submission PDF drafts

Generated and visually checked on 2026-10-02 (Korea). These are **DRAFT** files;
new51 results and final package/video/index references remain explicitly
incomplete. No missing result was inferred or filled from a partial run.

- `KitGuard_결과보고서_v0.7_draft.pdf`: 5 A4 pages, no extra cover. Body 10.6 pt;
  table text 10.1 pt.
- `KitGuard_Agent_기술설명_v0.7_draft.pdf`: 1 A4 page. Body 10.3 pt; table text
  9.8 pt.
- Both embed Arial Unicode MS. Sources and output hashes are in
  `BUILD_MANIFEST.json`; final visual and extraction checks are in `QA.json`.
- `qa/` contains every page rendered by Poppler (report 130 dpi, technical note
  150 dpi). All six final pages were visually inspected, with no clipping,
  overlap, missing Korean glyphs, broken table borders, or obscured footers.
- Extracted text preserves the complete source body after removing Markdown
  formatting/links and normalizing whitespace; every page retains DRAFT.

## Rebuild from updated Markdown

From the project root, with the bundled Python (ReportLab and pypdf):

```sh
/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  scripts/v07/build_submission_pdfs.py \
  --report-source docs/v0.7/RESULT_REPORT_KO_DRAFT.md \
  --tech-source docs/v0.7/AGENT_TECH_KO_DRAFT.md \
  --output-dir output/pdf/v0.7-draft \
  --tech-size 10.3
```

The script reads only the specified Markdown content, never partial model runs.
The report's `PAGE_BREAK` comments define its five explicit pages. It rejects
overflow instead of silently dropping text, shrinking below the configured
minimum, or adding a sixth page. Source-linked local files must exist. Relative
PDF links assume the project directory structure is retained; a PDF copied alone
does not carry those source files inside it.

`--status final` is available only after DRAFT/작업본/미완료 markers have been
removed from the source with verified replacements. It does not certify final
submission readiness, metrics, or licensing. The current files retain all draft
markers.

After any content or layout change, rerender every page and repeat visual and
text checks. `BUILD_MANIFEST.json` intentionally records visual QA as pending at
generation time; the separate `QA.json` certifies the inspected PDF hashes only.
Old QA becomes stale when those hashes change.

```sh
pdftoppm -r 130 -png output/pdf/v0.7-draft/KitGuard_결과보고서_v0.7_draft.pdf output/pdf/v0.7-draft/qa/report
pdftoppm -r 150 -png output/pdf/v0.7-draft/KitGuard_Agent_기술설명_v0.7_draft.pdf output/pdf/v0.7-draft/qa/agent
```

The PDF skill's authoring-operation marker was successfully invoked exactly once
for this creation operation, with expected output count 2. No inference, browser
automation, or modification of earlier official/historical PDFs occurred.
