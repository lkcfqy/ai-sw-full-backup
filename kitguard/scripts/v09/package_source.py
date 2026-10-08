"""Package v0.9 with the reviewed v0.8 collector and isolated runtime smoke test."""
from __future__ import annotations

import argparse
import ast
import json
import re
import tomllib
from pathlib import Path

from scripts.v08 import package_source as base

ORIGINAL_NOTE = base.package_note
ORIGINAL_COLLECT = base.collect


def collect(root):
    selected, samples, index = ORIGINAL_COLLECT(root)
    # The live grading ledger changes after package verification. Ship its final
    # snapshot beside the source ZIP, so the ZIP cannot grade its own hash.
    for relative in ("docs/scoring/ledger.json", "docs/scoring/reviewed-snapshot.json"):
        selected.pop(relative, None)
        index["not_scanned_or_bundled"].append(relative + " (final snapshot accompanies delivery)")
    return selected, samples, index


def package_note(version, preview, samples):
    note = ORIGINAL_NOTE(version, preview, samples).decode()
    note = note.replace("DEVELOPMENT PREVIEW / 개발 미리보기 / 开发预览",
                        "FINAL CONTEST SOURCE / 최종 제출 소스 / 最终提交源码")
    note = note.replace("bash scripts/run.sh", "bash scripts/run_competition.sh")
    note = note.replace("-m scripts.v08.package_source --preview", "-m scripts.v09.package_source")
    reproduction = """## Submission reproduction / 제출 재현 / 提交复现

Unzip the source and run all commands from the `KitGuard/` directory. Code version
is `0.9.0.dev4`; this documentation was revised on 2026-10-05 KST. This source is
one component of the accompanying five-material submission. Use this page for
installation and its submission manifest for the report, video and slides.
The source's development version and previously disclosed evidence limits remain.

The verified machine is Apple Silicon macOS, M5 Pro, 64 GB unified memory,
Python 3.12. `scripts/setup.sh` checks macOS/arm64, requires `uv`, creates a local
`.venv` with Python 3.12 and installs the exact `requirements-lock.txt` versions,
then installs this source without resolving dependencies again. First setup needs
network access for Python/packages that are not already cached. The ZIP contains
neither `.venv` nor model weights. No API key or paid cloud model is required.

The model downloader needs network access and anonymously fetches the fixed
`mlx-community/Qwen3.6-27B-4bit` revision
`c000ac2c2057d94be3fa931000c31723aac53282`. Its 16-file snapshot totals
16,081,490,064 bytes; allow additional disk space for dependencies and temporary
download chunks. It verifies every file's size and SHA-256, compares LFS payloads
with upstream SHA-256 and other files with upstream Git blob SHA-1, and checks the
weight index against the three actual shards. It also verifies the upstream
Apache-2.0 declaration and preserves the original license and model card under
`models/licenses/Qwen3.6-27B/`. Included attribution and license text are under
`third_party/models/`. File integrity verification does not establish accuracy.

On this project's existing verified installation, skip setup and download:

```sh
bash scripts/run_competition.sh
```

For a newly unzipped source directory, run setup first. If the fixed verified model
already exists elsewhere, skip its download and launch with its absolute path:

```sh
KITGUARD_MODEL_PATH=/absolute/path/to/Qwen3.6-27B-4bit \\
  bash scripts/run_competition.sh
```

The default model path is this source directory's `models/Qwen3.6-27B-4bit/`.
Old absolute paths in preserved provenance records describe their original
acquisition location; the launcher uses the current project path above. Keep one
server and one model worker. The launcher uses `spatial_guarded`, 1536-pixel main
inputs, offline model loading and `data-competition-v09/` for new local state.
Keep that directory when restarting. The first actual check loads the model;
file availability and model-loaded status are different. Stop with Ctrl+C.

For the shortest reproducible demonstration, open
http://127.0.0.1:8765/static/autonomy.html and run the three public-photo scenarios.
The ZIP already includes their exact three development photographs at the paths
listed below; no dataset download or manual image copying is needed. Each model
check executes locally. Results can be differences, insufficient evidence or
matching quantities. The declared R1-to-R2 scenario explicitly reuses its photo
and runs a fresh check; it does not show a physical repair. Download the evidence
ZIP, unzip it and open `index.html` to inspect the saved photos, order versions,
model results and tool steps without the server.

For a current photo-document goal, open
http://127.0.0.1:8765/?new=photo-document, register a local image with its source
statement and BOM, then use the order's autonomous-review action. The goal binds
the current order/revision/evidence/photo; an outdated goal is rejected. See
`docs/scoring/DEV4_HANDOFF.md` for the two paths and failure recovery.

The accompanying CPU acceptance uses an isolated directory, existing dependencies
and synthetic observers; it proves import, HTTP and state contracts. The separate
actual MLX/browser records prove local execution on the verified machine. These
scopes do not prove a clean-machine install, another operating system, new-photo
accuracy or human productivity. Current limitations remain 0 human participants,
0 physical completions and the disclosed three errors on the 51-photo assessment.

After setup, reproduce the packaged autonomous/photo-document CPU contracts:

```sh
cpu_review_dir=$(mktemp -d)
KITGUARD_DATA_DIR="$cpu_review_dir" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \\
  .venv/bin/python -m pytest -q -p no:cacheprovider \\
  tests/test_autonomy.py tests/test_photo_documents.py
```

These tests use injected synthetic observers and temporary state, without loading
the model or adding photographic accuracy evidence. Some other historical tests
require the external research artifacts described below.

Current source/AI disclosure and presentation wording are in
`docs/scoring/SOURCE_AI_DISCLOSURE_KO.md` and
`docs/scoring/PRESENTATION_SCRIPT_KO.md`.

"""
    note = note.replace("## Included demo photographs\n", reproduction + "## Included demo photographs\n")
    note += "\n## v0.9 review workflow\n\nSee docs/v0.9/DEMO_AND_HANDOFF_ZH.md and docs/v0.9/RELEASE_NOTES.md. "
    note += "The independent point review preserves original AI, expires on changed evidence/opinions, "
    note += "and exports both count tables and original-photo point positions.\n"
    note += "Public-photo digital tasks: open /static/digital-trials.html. Six fixed tasks per participant, "
    note += "manual/KitGuard order alternation, server timing including inference, current-version checks, "
    note += "and full planned denominators. Engineering rehearsals are never human results.\n"
    note += "Autonomous mission: open /static/autonomy.html. One operator can run all three public-photo scenarios; "
    note += "real local inference, conditional routing, declared R2 replay, persistent execution and evidence ZIP. No participants needed.\n"
    note += "Current photo-document goal: use the order detail's autonomous-review link. The accepted goal binds "
    note += "order ID, revision, evidence epoch and photo ID; the worker also verifies the accepted content. "
    note += "It runs one fresh inspection without rewriting the BOM. Failed execution preserves input and error, "
    note += "without inventing a model result. See docs/scoring/DEV4_HANDOFF.md.\n"
    note += "Five machine tasks and CPU version-binding ablation are engineering evidence, not human efficiency "
    note += "or new-photo accuracy. Final grading ledger and raw execution artifacts accompany this ZIP. "
    note += "Source smoke uses existing dependencies; it does not certify clean-machine installation.\n"
    return note.encode()


def source_version(payload, preview):
    version = tomllib.loads(payload["pyproject.toml"].decode())["project"]["version"]
    tree = ast.parse(payload["kitguard/__init__.py"])
    declared = [n.value.value for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets)
                and isinstance(n.value, ast.Constant)]
    if declared != [version] or not re.fullmatch(r"0\.9\.\d+(?:\.dev\d+)?", version):
        raise ValueError("Matching v0.9 package/project versions required")
    if ".dev" in version and not preview:
        raise ValueError("Development source requires explicit --preview")
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-runtime", action="store_true")
    args = parser.parse_args()
    base.source_version = source_version
    base.package_note = package_note
    base.collect = collect
    base.TOP_FILES = (*base.TOP_FILES, "启动参赛演示.command")
    base.SMOKE_PROGRAM = base.SMOKE_PROGRAM.replace(
        "routes_list = [", "routes_list = ['/static/digital-resolution.js', '/static/digital-resolution.css', "
        "'/static/digital-trials.html', '/static/digital-trials.js', '/static/digital-trials.css', "
        "'/static/autonomy.html', '/static/autonomy.js', '/static/autonomy.css', ")
    base.SMOKE_PROGRAM = base.SMOKE_PROGRAM.replace(
        "assert 'photo-documents.js' in page", "assert 'photo-documents.js' in page and 'digital-resolution.js' in page")
    base.REQUIRED = base.REQUIRED | {"kitguard/digital_resolution.py", "kitguard/static/digital-resolution.js",
                                     "kitguard/static/digital-resolution.css", "tests/test_digital_resolution.py",
                                     "kitguard/digital_task_trials.py", "kitguard/static/digital-trials.html",
                                     "kitguard/static/digital-trials.js", "kitguard/static/digital-trials.css",
                                     "tests/test_digital_task_trials.py", "kitguard/autonomy.py", "tests/test_autonomy.py",
                                     "kitguard/static/autonomy.html", "kitguard/static/autonomy.js", "kitguard/static/autonomy.css",
                                     "docs/scoring/DEV4_HANDOFF.md", "scripts/scoring/run_machine_tasks.py"}
    print(json.dumps(base.build(base.ROOT, args.output, preview=True, smoke=args.verify_runtime), ensure_ascii=False))


if __name__ == "__main__":
    main()
