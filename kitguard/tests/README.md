# Engineering verification only

The Pillow images and injected `FakeAnalyzer` in this folder are **synthetic,
deterministic software-test fixtures**. They are never evidence of real vision
accuracy, real kit inspection, real users, or competition performance.

Run from the `kitguard` project directory after installing its `dev` dependencies:

```text
python -m pytest -q
```

Tests use temporary SQLite/image directories. They do not download weights or
invoke the real model. The intended coverage is invalid inputs, real image decode
and metadata stripping, stale evidence after revision/photo/reference changes,
concurrent inference invalidation, human confirmation, idempotent completion,
preserved completion history, canceled requests, interrupted-process recovery,
and failure without false success. Adapter-parser tests exercise the real output
validator without loading MLX or model weights.

The tests intentionally use a blocking observer to change state while inference
is in progress. A passing visual demo alone cannot check these race conditions.

## Real browser smoke test

`browser_ui_smoke.cjs` runs installed Google Chrome through the bundled Playwright
runtime against a **fresh, isolated** real KitGuard HTTP server. It does not mock
HTTP responses. Default server: `http://127.0.0.1:8767`; set
`KITGUARD_UI_BASE_URL` to override. Never use it against personal/production data.
The test creates orders, revisions, uploaded evidence and reference photos.

Start the test server with a new `KITGUARD_DATA_DIR` and intentionally missing
`KITGUARD_MODEL_PATH`; do not point it at the real model while another process is
using MLX. `test-results/ui/SYNTHETIC_UI_FIXTURE_1.png` and `_2.png` are clearly
labelled synthetic UI upload fixtures. The smoke test covers real forms, image
upload, reference upload, history selection, unavailable-model proposal handling,
JSON download, escaped user text, desktop and mobile layout, and JavaScript/network
errors. It does **not** validate camera hardware, physical parts, model accuracy,
or a real-model completion. Its intentional proposal request returns HTTP 503,
so that one expected browser resource error is recorded separately.

Run with the bundled Node runtime, without installing packages into the project:

```text
python tests/generate_ui_fixtures.py
"$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node" tests/browser_ui_smoke.cjs
```

Override `KITGUARD_PLAYWRIGHT_MODULE` and `KITGUARD_CHROME_PATH` on another machine.
The server must start with zero orders. Results and desktop/mobile screenshots
are saved under `test-results/ui/`; those outputs are ignored by Git.
