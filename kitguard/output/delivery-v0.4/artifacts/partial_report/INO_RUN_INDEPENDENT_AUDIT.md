# Independent read-only run audit

Both completed frozen experiments passed the independent audit in `scripts/audit_partial_bracket_run.py`. The auditor imports no runner scorer, preparation helper, application or model module. It uses saved author annotations, original image bytes, standard-library checks and Pillow. It did not run a model, change a frozen file or write into either experiment directory.

| Frozen experiment | Planned sources | C_b | W_b | U_b | E | Median pipeline time | Independent checks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `v04_ino_bracket_partial_v1` | 20 | 16 | 2 | 2 | 0 | 11.529 s | 1,495 |
| `v04_ino_two_bracket_v1` | 1 | 1 | 0 | 0 | 0 | 15.411 s | 159 |

All rows remain in the frozen denominator and source order. In the 20-source experiment, four full images yielded C_b=0/W_b=2/U_b=2/E=0; sixteen author-box oracle ROIs yielded C_b=16. Of the sixteen C_b rows, eleven are application-clear and five are not. Application clarity is not four-class correctness or business readiness. The separate two-bracket oracle ROI was C_b and application-clear.

The constant-one baseline matches all 20 single-bracket labels and fails the separate two-bracket label. These experiments are reported separately. Their outputs establish agreement with selected author labels, not completeness of those labels for every visible background object. A W_b discrepancy must not automatically be described as a visual misclassification. Author-box crops also do not establish detection in unlocalized scenes.

## Evidence verified

- External and saved manifests/freezes, planned IDs and unique origin-source IDs; exact prediction row order and full denominator.
- Beginning and ending method/runner/manifest/freeze hashes; exact method source set and every saved Python source snapshot.
- Partial bracket-only truth and explicit unlabeled bolt/nut/washer categories; fixed observer requirements and selected actual model/mode/image size.
- Independent reconstruction of the author ROI from normalized YOLO coordinates, 10% short-side margin, integer floor/ceil bounds, target size, complete selected boxes and non-intersection of omitted boxes.
- All 21 author views, all 21 normalized app-upload JPEGs and all 42 original/rotated prepared PNGs reproduced byte-for-byte. Both actual runs used two spatial generations per case and did not invoke identity crops.
- Every listed PNG size/hash, every generation image reference, and the correspondence between generation output, saved inventory, pass counts and final counts.
- C_b/W_b/U_b/E, application-clarity cross-tab, real first-pass transitions, constant-one baseline, full-image/oracle-ROI strata and latency recomputed independently from the saved records.

The 9 CPU tests verify valid reconstruction and detection of changed prediction labels, summaries, source snapshots, normalized JPEGs, prepared PNGs and generation input hashes, plus refusal to audit an active run. Ruff passed. Synthetic tests do not measure model accuracy.

Reports:

- `test-results/audit/v04-data-research/ino20-independent-run-audit.json`
- `test-results/audit/v04-data-research/ino2-independent-run-audit.json`
- `test-results/audit/v04-data-research/partial-auditor-tests.xml`
- `test-results/audit/v04-data-research/independent-21-derived-audit.json` — separate agent's source/ROI reconstruction, including independent enumeration of the F/52 selection rule.

The audit script SHA recorded in both run-audit reports is `ae2b85d100e6dae673b0bdd1e80b7aee808d2d3d22a7c5b46382ec987c2d5a5f`.
