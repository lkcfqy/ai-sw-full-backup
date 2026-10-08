# v0.7 delivery builder evidence contract

`scripts/v07/build_delivery.py` keeps the five existing primary components and
local HTML/JSON/checksum layout. It neither publishes files nor submits them to
the contest. Use a Python environment containing `pypdf`, from the project root:

```sh
python -m scripts.v07.build_delivery \
  --config path/to/reviewed-delivery-config.json \
  --output output/delivery-v0.7-new
```

The output directory must be new. Config paths are project-local regular files.
The primary roles remain `report`, `technical`, `source`, `video`, and `slides`.
The required `checks` object is:

```json
{
  "source": "path/to/source.zip.verification.json",
  "video": "output/demo/v0.7/public-photo-edit-01/video_receipt.json",
  "tests": "test-results/final-software-tests.xml",
  "evaluation_run": "evaluation-runs/THE_COMPLETED_RUN/run.json",
  "evaluation_analysis": "evaluation-runs/THE_COMPLETED_RUN/analysis.json",
  "evaluation_freeze": "docs/v0.7/public_paired_freeze_v1/freeze.json",
  "evaluation_audit": "path/to/independent-completed-audit.json"
}
```

Replace the illustrative paths with actual reviewed artifacts. `evaluation_freeze`
and `evaluation_audit` are mandatory additions. Before assembling the delivery,
create the audit outside the completed run directory:

```sh
.venv/bin/python -m scripts.v07.audit_public_paired \
  --run evaluation-runs/THE_COMPLETED_RUN \
  --freeze docs/v0.7/public_paired_freeze_v1/freeze.json \
  --output path/to/new-independent-completed-audit.json
```

The auditor performs CPU replay of preserved observations; the delivery builder
does not repeat that replay or invoke a model. Do not run the audit or media build
concurrently with the timed inference experiment.

## Required experiment bindings

- `run.json` must record completed, unchanged, isolated execution of all 153
  planned attempts. Incomplete runs are rejected before other results are read.
- The actual freeze SHA must be
  `cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7`.
  A different protocol requires an explicit reviewed builder change.
- Freeze, analysis and audit schema versions must be v0.7's registered formats.
  The exact modes are `spatial_inventory`, `spatial_guarded`, and
  `selective_identity_experimental_v1`. Missing/extra modes are rejected.
- Every analysis arm retains 51 nonnegative integer `C/W/U/E/N` outcomes with
  `N=0`. Wrong/uncertain/failed observations remain in the denominator.
- The independent audit must be passed, complete, unchanged, and explicitly record
  that no model was loaded or called. Its three model/protocol identities must
  match the freeze. Its independent aggregates and acceptance gates must agree
  with the selected analysis. Passing an engineering gate is **not** required to
  deliver an honest report of a failed experiment.
- Audit `artifacts_sha256` must match the actual same-directory `run.json`,
  `analysis.json`, `freeze.json`, `manifest.json` and `predictions.jsonl` bytes.
  Audit `evidence_sha256` must also match the official freeze, manifest, predictions
  and current `scripts/v07/audit_public_paired.py` source bytes.
- These compact evidence bindings are checked again after copying deliverables,
  before the HTML and build manifest are sealed. The builder does not rehash every
  raw input/call file; the completed independent auditor is responsible for that
  deeper check. SHA-256 binds local artifacts but is not an authenticity signature.

`BUILD_MANIFEST.json.validation` retains earlier fields and adds
`evaluation_modes`, `evaluation_independent_audit_status`, `evaluation_evidence`
(project-relative paths and actual hashes), and `evaluation_verification_scope`.
The official freeze hash and 153 attempts remain visible in their existing fields.

Small synthetic tests are in `tests/test_delivery_v07_builder.py`. They do not
read the live experiment, run a model, encode media or import PDF tooling.
