# v0.5 inspection region backend

Implemented the operator-declared region workflow without modifying the four observer-method files. The default whole-image upload and its saved JPEG bytes remain unchanged. A root is the system's complete normalized JPEG, not the original camera file or RAW/EXIF record.

## API contract

`POST /api/orders/{order_id}/inspection-region` accepts:

```json
{
  "expected_revision": 1,
  "expected_photo_id": "img_current",
  "expected_evidence_epoch": 1,
  "root_photo_id": "img_root",
  "mode": "region",
  "region_xyxy": [20, 30, 320, 330],
  "confirmed_all_items_inside": true
}
```

The coordinate rectangle uses integer pixels in the complete normalized root, with excluded right/bottom bounds. Both sides must be at least 32 px. Whole-image mode requires `region_xyxy: null`; both modes require literal boolean `true` confirmation. Unknown fields, boolean/float/string coordinates and non-finite JSON geometry are rejected with 422. Validation errors omit invalid raw values so NaN/Infinity cannot break JSON error serialization.

Returns `{order, photo, changed}`. A current, identical scope returns `changed: false` without another event or evidence epoch. Stale revision/photo/epoch, an active inspection, completed order, unrelated/recursive root or any non-closed study binding returns 409. Stale replay never silently applies a second scope.

`Store.select_region` performs the state checks, study lock, root integrity check, derivation, final recheck, file registration, epoch increment and scope event within one `BEGIN IMMEDIATE` transaction. Failed commits clean the uncommitted derived file. A registered draft study already locks the order's scope; callers must close it before ordinary workbench reselection.

## Provenance and byte integrity

New full uploads have root identity/family fields. Historical photos without lineage fields are interpreted as roots without rewriting stored records. Every derived view directly references its root, never another crop. Region views use root RGB pixels, an exact integer crop and JPEG quality 95 with no enlargement. Restoring whole-image scope copies the root's exact stored bytes. Each view records a versioned derivation, source coordinate space, root identity/SHA/dimensions, source family, rectangle, declaration and server confirmation time. It does not fabricate a new upload SHA or new physical capture event. Public provenance remains attached to the order and derived view.

`inspection_scope` on every new check and field case contains `mode`, `view_photo_id`, `view_sha256`, `root_photo_id`, `root_photo_sha256`, `source_family_sha256`, `root_width`, `root_height`, `root_source_sha256`, `root_created_at`, `region_xyxy`, `coordinate_space`, `derivation`, `scope_declaration` and `scope_confirmed_at`. A normal whole root has null declaration/confirmation; a restored whole view has its explicit declaration. `source_family_sha256` is also recorded directly on checks/cases.

Inspect, commit, completion and export check the relevant saved bytes and root lineage. Derived views are independently regenerated from the declared root/rectangle using the recorded derivation and compared byte-for-byte, with coordinate space and dimensions checked. A valid file hash cannot excuse a wrong declared rectangle. Checks cannot commit or complete against a changed scope snapshot. Exports preserve historical scopes even after a closed study's workbench order is reselected.

## Evidence semantics and field recording

Feedback and uncertainty budgets use the known root family. Reframing does not count as another physical capture or reset the recapture budget, including a clear derived view followed by a return to the full image. Scope-change feedback says only that the scope changed; it reports no inferred physical action or resolved-count transition. Different-coordinate region cues are not reused as attention boxes.

Field exposure, duplicate registration and known public-source checks join exact recorded byte relationships: root/view family links, saved JPEG SHA and direct re-upload SHA. This also detects a stored root/crop JPEG uploaded into another order even if normalization encodes it again. It does not use a perceptual hash or claim to recognize arbitrary external crops/transcodes. Different files do not authenticate independent physical scenes.

New study protocols include `inspection_scope_policy: operator_region_v1`, and new cases seal their complete scope before freeze/manual/AI. Missing scope in a new-policy case is rejected. Legacy exports without the policy keep their historical meaning. Case/check scopes must match when an AI result is attached.

## Offline archives

Both order and field evidence ZIPs preserve the complete normalized root and actual input view, their hashes, metadata, events and frozen scope. A whole root that already is the target need not have a duplicate photo binding; a derived/restored target has a distinct root role, with identical whole-image bytes deduplicated in field ZIPs. Offline HTML includes the full root with an SVG scope rectangle and the actual view, labelled as the same photograph's selected region, with outside-scope content uninspected. Existing model points stay on their input view; they are not silently moved onto the root.

## Validation

- Full CPU suite: **681 passed** in 9.28 s; `test-results/v05-backend-final.xml`.
- Independent API/adversarial review: 54 tests passed at review time; subsequent cases are included in the final suite.
- Six additional backend regression tests cover budget preservation, exact re-upload family links, closed-study historical scope, scope-policy downgrade, legacy whole-image bytes and completion scope mismatch.
- Ruff passed for all `kitguard` code and the new backend tests; compileall passed.
- `test-results/v05-method-preservation.json` confirms unchanged SHA256 for `vision.py`, `spatial.py`, `consensus.py` and `identity.py`.
- `test-results/v05-api-scope-fixture/` contains an actual API-generated closed engineering study with default whole, region and restored-whole cases, its study ZIP and three order ZIPs. All observations are explicitly `backend: test`; synthetic inputs and fake manual timing are not real-world or model-accuracy results.

No GPU inference, production database edits, v0.4 history changes or production-service restart were performed for this implementation. The remaining evaluation need is fresh real material and operator task validation; the already observed public images cannot establish an unbiased accuracy improvement from this feature.
