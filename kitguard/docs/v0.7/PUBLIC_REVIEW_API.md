# Public-photo digital review and version replay

Implemented 2026-10-02 (Korea). Scope: public-data demonstration of the existing
agent workflow. This is separate from physical completion, full-task trials, model
accuracy measurement, and proof of genuine user feedback.

## Intended workflow

1. Create an order through `/api/public-demos/{sample_id}/orders`.
2. Run the normal inference endpoint. No public-review endpoint runs inference or
   supplies cached predictions.
3. Inspect the actual observed counts, tool trace, next action, model identity, and
   photo/region provenance. The real model may request more evidence or be wrong.
4. Optionally approve a revised BOM using the existing revision endpoint.
5. Explicitly replay the same registered public photograph against the new BOM.
   This copies verified pixels and the exact selected region, invalidates the old
   check, and requires a fresh call through the normal inference endpoint. It
   does not simulate new physical evidence, repair, or capture.
6. A human records a digital review, including disagreement or inability to judge.
   Review does not set order status to completed, change model output, or create a
   physical completion/manual-review receipt.

Factory: `create_public_review_router(store, engine.status, catalog=PUBLIC_DEMOS)`.
All routes inherit the app's same-origin local-browser boundary. Operator codes
are self-declared labels; the app does not authenticate reviewer identities.

## Read current state

`GET /api/orders/{order_id}/public-review-summary`

Returns `scope: "public_photo_digital_review"`, registered `source`,
`physical_completion_allowed: false`, `inspection_scope`, `check`, `limitations`,
`can_replay`, `replay_blockers`, `can_review`, `review_blockers`, `replay_request`,
`review_request`, `current_review`, and historical `reviews` with a computed
`current` flag. Request templates contain version/photo/check/hash bindings only;
the UI must supply explicit confirmations, an idempotency key, and human inputs.

The current check includes its full SHA-256 digest and runtime identity digest.
It must use `backend: "mlx"` and exactly match the current runtime's label, model
repository/revision, observer protocol hash, mode, and image size. Test-backend
checks cannot be promoted into public-model evidence.

An active registered fixed-state study prevents writes. A current historical
review may remain current while a study is active because its evidence has not
changed; the write affordance is disabled.

## Reuse existing public pixels after a BOM revision

`POST /api/orders/{order_id}/public-replay`

```json
{
  "expected_revision": 2,
  "expected_photo_id": "img_from_revision_1",
  "expected_evidence_epoch": 2,
  "confirmed_no_physical_capture": true,
  "idempotency_key": "unique-replay-key"
}
```

Response: `{order, photo, replay}`. The receipt includes prior/new photo IDs,
revision, epoch, source, exact inspection scope, `physical_capture: false`, and
`requires_new_inference: true`. Whole-image replay creates one photo; region replay
creates a copied root plus its exact view. Photo bytes, source-family hash, region,
and scope declaration remain bound. Copied photos include `replay_of_photo_id` and
`capture_kind: "public_photo_replay"`. Fresh inference is required even for the
same bytes. Same-revision replay is rejected rather than accumulating duplicates.

## Record a human digital review

`POST /api/orders/{order_id}/public-review`

```json
{
  "expected_revision": 2,
  "expected_evidence_epoch": 3,
  "photo_id": "img_current",
  "check_id": "chk_current",
  "check_sha256": "64-lowercase-hex-characters-from-summary",
  "runtime_identity_sha256": "64-lowercase-hex-characters-from-summary",
  "operator_code": "reviewer-1",
  "conclusion": "needs_more_evidence",
  "note": "The count cannot be confirmed from this recorded view.",
  "confirmed_digital_only": true,
  "idempotency_key": "unique-review-key"
}
```

`conclusion` is one of `acknowledged`, `needs_more_evidence`, `disputed`, or
`inconclusive`. Any of the four AI decisions (`ready`, `correct`, `recapture`,
`manual`) can be reviewed with any human conclusion. The receipt retains the
actual `ai_decision`, full `check_snapshot`, requirements, source, scope, runtime,
reviewer code, and note. It explicitly has `physical_completion: false` and
`user_validation: false`. Human acknowledgement is not a correctness label.

Response: `{order, review, summary}`. Receipt histories live in
`order.public_reviews` and `order.public_replays` and are included in existing JSON
exports and `evidence.json` in the normal evidence ZIP. A historical receipt is
immutable; do not label all historical records as currently valid. Currentness is
computed from the latest valid check, full check digest, revision, epoch, source,
scope, and runtime. Revision, new photos/references/inference, or changed runtime
can make a review historical without deleting it.

## State and error contract

- Writes hold the existing SQLite immediate transaction lock and check the
  current revision, epoch, photo, active inference, registered source/bytes, and
  active-study restriction. Reviews additionally bind check contents and runtime.
- Request confirmation must be JSON boolean `true`; integer/string equivalents
  and extra fields are rejected. Version/epoch fields are strict integers.
- Shared human-operation idempotency keys cannot be reused across different
  bodies, orders, or operation kinds. A retry returns its historical receipt with
  `replayed: true`, without reverting a newer order revision.
- File-copy failure or database rollback removes newly written replay files.
- Invalid inputs return 422; conflicting state/source/identity returns 409.
- Existing `/complete` and `/manual-review` protections for public data remain in
  force. `/complete` now also rejects registered public raw hashes and known exact
  source-family links when the photo was re-uploaded through an ordinary order,
  including normalized copies and recorded region descendants. This closes an
  existing path that only checked the order's demo marker. It does not detect
  every internet image or unregistered visual alteration. The pre-existing
  synthetic completion-test contract is unchanged. No new public endpoint creates
  physical-completion authority.

## Engineering verification record

The first isolated run on 2026-10-02 passed 55 synthetic contract cases in 2.44s
with Ruff passing. The expanded 61-case suite also covers active studies,
busy/terminal/full orders, rollback cleanup, and simultaneous replay retries.
Combined with existing public-demo and manual-review regression cases, 120 tests
passed in 4.73s. The JUnit record is
`test-results/public-review-contract-20261002.xml`. Subsequent integration cases
check offline replay-only display, escaped review text, and historical validity.
After adding the ordinary-upload public-source guard and those integration cases,
the final focused run passed 135 tests in 6.47s with Ruff passing; the same JUnit
file now records that expanded run. A further 7 existing completion/region
regressions passed in 0.41s; see
`test-results/public-source-completion-regression-20261002.xml`.
These tests inject clearly named synthetic observations and persisted metadata to
exercise the API. They do not run MLX and are not public-data inference results,
model accuracy measurements, genuine human reviews, or contest bonus evidence.

Reproduce with:

```sh
.venv/bin/python -m pytest tests/test_public_review.py tests/test_public_demo.py -q
.venv/bin/python -m ruff check kitguard/public_review.py tests/test_public_review.py
```
