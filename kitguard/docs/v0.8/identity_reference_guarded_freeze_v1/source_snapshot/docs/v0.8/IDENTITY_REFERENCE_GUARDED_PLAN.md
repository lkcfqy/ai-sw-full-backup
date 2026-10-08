# Identity-only fixed references: exposed 51-image development protocol

Status: implemented for CPU contract review; no inference authorized by this file. Root approved preparing this one bounded candidate on 2026-10-02. Preflight, freeze and actual execution remain separate root actions. No production promotion or new holdout claim.

## Fixed intervention and model boundary

Mode: `spatial_guarded_identity_references_v1`. Reuse the original v0.7 frozen `LocalVision` guarded implementation, including both spatial calls, identity selection/skip conditions, target IDs, crops, JSON schemas, category definitions, exact-ID checks and unknown-only veto. The original source freeze is `docs/v0.7/public_paired_freeze_v1/freeze.json`, SHA-256 `cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7`. Copy its manifest-listed bytes to a new isolated source bundle; never modify or copy incidental runtime databases from that old snapshot.

Calls 1 and 2 receive exactly one image each: original normalized inspection input, then its 90° counterclockwise PNG rotation. Their system/user prompts, `SpatialInventory` JSON schema, 900-token limit and temperature 0 are unchanged from original G. The two spatial stages are attempted again in the original G order; an earlier failure remains E and later stages are not run to compensate. Historical outputs are not reused as model answers.

When the original identity condition allows call 3, image 1 is the full target, images 2..K are the original target crops with their original point IDs, image K+1 is the previously approved nut297 reference and K+2 is washer057. Only the old sentence asserting that every later image is a crop is replaced with the correct roles, and reference-index instructions are appended to the point prompt. References create no new target IDs and are not inventoried or counted. All category definitions and uncertainty instructions remain byte-for-byte unchanged. The original `IdentityResponse` schema and `apply_decision` remain unchanged: a classification conflict may only remove known counts by setting affected categories to unknown; it never supplies a corrected count.

Fixed prepared PNG hashes, already selected before this candidate:

- nut: `097a0da4cdd05c725cab6f2e871cfb4f55e153d0125d25d548c4534969ce5137`
- washer: `845922352509f55cfe294ec2f2ec2a4218d251a140f302323dfc08c146a76d88`

Approval/source/original-pixel crops remain `datasets/derived/v0.8/class_reference_dev_v1/approved_references.json`. No new reference screening, selection or image editing is permitted. This approval is AI development QA, not human feedback or independent certification of physical threading. Type007→nut retains the disclosed project semantic projection.

The model receives no truth, BOM quantities, source IDs, author types or historical answer. The API supplies a fixed neutral four-class requirement map only to satisfy the existing validation interface; the original observer does not pass it into the prompts.

## Frozen population, budgets and decisions

All original 51 case/source/input hashes from `evaluation-runs/v0.7/public_paired_v1` are retained: 35 Screws crops and 16 LOCO normal bags. The sole behavioral baseline is its historical `spatial_guarded` arm, C41/W3/U7. These are exposed development cases, including the four cases inspected during failure diagnosis; no filtering, max-cases shortcut or new holdout claim. New LOCO24 preparation/results are outside this experiment.

One attempt per case, concurrency 1, zero retries, no warmup, no context adaptation, the same pinned Qwen3.6-27B MLX 4-bit revision. Identity keeps **1800** output tokens despite the longer visual/text context; extra prompt tokens, generation tokens, finish reason, load time and per-case total time are recorded. The first cold attempt remains in the all-attempt timing denominator. Any warm subset is additionally labeled. Historical timings are not concurrent and this is not a clean causal estimate of reference placement: both spatial calls and identity are rerun, and their outputs can vary.

All C/W/U/E/N must sum to 51. Failed attempts remain E; unattempted cases after interruption remain N. Development continuation requires **W=E=N=0, C≥41, all 14 historically correct LOCO cases still C, and all-four-class false-ready=0**. Source-supported false-ready is separately reported and cannot replace the all-four metric. Gates do not authorize automatic production use. No threshold/prompt/reference adjustment is made after inspecting this run.

## Recording and isolation

The candidate source bundle consists of the original v0.7 manifest-listed files, this plan, the new runner and a base-source provenance manifest. Preflight itself dispatches into this bundle with isolated Python before importing `kitguard`. Freeze hashes all bundle files, model payloads/revision, approved references and all 51 source/normalized inputs. The experimental observer protocol hash binds the original base protocol, new runner SHA and policy; status names the experimental mode and separately discloses the base mode/hash. It does not pretend to be the original G protocol.

The new runner distinguishes generation-attempt records from actual model-call started/completed counters (loading or grammar failures need not invoke the model). It retains each call's raw text, parsed or failed state, full JSON-schema SHA, exact prompts, max tokens, actual PNG bytes/SHA and explicit one-based image roles. Diagnostics hold the experimental protocol and actual identity reference indices, including failures. The returned observation remains legal under the old frozen observation schema. Current v0.8 host `ReferenceEvidence` is neither used nor changed, so its production identity-without-reference claim is not falsely applied to this experiment.

At runtime, `KITGUARD_DATA_DIR` is set to the new result directory's `runtime-app-data` before any app/evaluation import. Preflight uses an adjacent dedicated runtime-data directory. No runtime database belongs in a source snapshot. Sources and model files are verified before/after; baseline and old reference51 evidence remain untouched. Results/analysis/decision use new directories, and an independent raw-replay audit is required after completion.

## Root execution commands after review

Use the project virtual environment; these commands are instructions only and were not executed while writing this protocol.

```sh
.venv/bin/python scripts/v08/run_identity_reference_guarded.py preflight --output test-results/v0.8-identity-reference-preflight-v1.json
.venv/bin/python scripts/v08/run_identity_reference_guarded.py freeze --preflight test-results/v0.8-identity-reference-preflight-v1.json --output docs/v0.8/identity_reference_guarded_freeze_v1
.venv/bin/python scripts/v08/run_identity_reference_guarded.py run --freeze docs/v0.8/identity_reference_guarded_freeze_v1/freeze.json --output evaluation-runs/v0.8/identity_reference_guarded_v1
```

The preflight JSON's adjacent `.source_snapshot` is retained as preparation evidence. Existing destinations are never overwritten. Synthetic CPU contracts validate inputs, roles, unchanged base behavior, skip/failure paths and full denominators; they are not model accuracy evidence.
