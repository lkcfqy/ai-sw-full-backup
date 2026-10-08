# Partial author L-bracket validation runner

The independent runner is `scripts/run_partial_bracket_benchmark.py`. It never calls the existing four-class `score_case`/`order_tasks` helpers. Author truth contains only `bracket`; `bolt`, `nut`, and `washer` remain explicitly unlabeled. This is a descriptive positive-view validation, including author-box oracle ROIs, rather than a four-class completeness or business-readiness test.

## Frozen execution contract

Required CLI arguments are `--manifest`, `--dataset-root`, `--output`, and `--freeze`. Exactly one of `--validate-only` or `--execute-real-model` is required. The output must not already exist. Validation imports only the standard library and was tested successfully under `python -S` with site packages disabled.

The freeze must contain `schema_version: 1`, `protocol: ino_bracket_partial_v1`, a UTC `frozen_at`, exact `manifest_sha256`, exact `runner_sha256`, and the complete immediate `kitguard/*.py` source mapping returned by `source_hashes(project)`. It also requires the exact manifest-order `case_ids`, matching `expected_cases`, `label_scope: author_L_bracket_count_only`, `input_pipeline: app-upload`, `observation_mode: spatial_guarded`, `image_max_side: 1536`, model profile `Qwen3.6-27B-4bit` at revision `c000ac2c2057d94be3fa931000c31723aac53282`, and fixed observer requirements `{bolt: 1, nut: 1, washer: 1, bracket: 1}`. Extra descriptive freeze fields are allowed.

The runner supports any explicitly frozen number of cases. Current supported author bracket truth is integer 1–3. It rejects additional ground-truth keys, duplicate source IDs or case IDs, incorrect SHA256, and image paths outside the dataset root, including symlinks. It does not select cases, tune prompts, modify truth, retry failures, or create matching orders for scoring.

## What is preserved

- Exact input manifest/freeze, Observation JSON schema, complete Python method source snapshot and the runner source.
- Isolated real app-upload normalization through its HTTP route, saved as JPEG. No production store is used.
- Original and rotated prepared PNGs, identity model crops and raw pixel crops, copied before the observer removes its temporary directory.
- Every generation's supplied image hashes, system/user prompts, output schema, parsed output or failure, and image-file hashes.
- Per-case raw observation, full attempt diagnostics, normalized/source hashes before and after execution, actual first-pass bracket output, total pipeline time, and runtime diagnostics.
- Every planned case as C_b, W_b, U_b, or E; initialization/parse/inference failures remain in the denominator. On interruption, remaining cases are explicitly saved as `not_executed_or_not_recorded` errors with null latency.

Source snapshots are checked against the freeze, followed by a second preflight. Beginning and ending source/runner/manifest hashes are compared with the frozen values. Input changes invalidate the frozen-run flag. An invalid raw output is preserved with explicit non-JSON markers rather than making the JSONL writer lose a failed case. Persisted rows are counted only after the JSONL write succeeds.

## Interpretation

`C_b` means final bracket count equals author truth, `W_b` means a known unequal count, `U_b` means bracket is unknown, and `E` means execution/validation failed. `app_clear` is independently defined as all four predicted counts known, no issues, and action `none`. Its cross-tab never means four-class correctness or readiness. Real original-pass bracket counts remain paired components of this same run; there is no invented independent first-pass latency. When later inference fails, a schema-valid saved original-pass inventory can still supply the first-pass result while the final outcome stays E.

The summary includes full-image/oracle-ROI strata and a constant-one baseline. The present 20-source set has author bracket truth 1 in every case, so a constant prediction of 1 scores 20/20. Results cannot establish general counting reasoning, multi-bracket performance, absent-bracket false positives, independent scenes, or a new factory deployment. Latency excludes unexecuted rows and reports its sample count explicitly.

## CPU validation

33 tests passed; Ruff passed for both added files. Tests exercise the actual normalization route with generated CPU fixtures and stubbed model generation, including exact temporary-input retention. No real model/GPU was executed and no accuracy claim follows from these engineering fixtures.

JUnit evidence: `test-results/audit/v04-data-research/partial-bracket-runner.xml`.

The actual 20-case manifest at `datasets/manifests/v0.4/ino_l_bracket_external_v1/manifest.json` also passed metadata/path/image-SHA validation. Root owns final freeze creation and real-model execution.
