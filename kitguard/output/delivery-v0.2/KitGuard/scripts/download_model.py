"""Download the one public KitGuard model at a pinned revision, without credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

REPO = "mlx-community/Qwen3-VL-8B-Instruct-8bit"
REVISION = "a0093b9b5fda6f76ddd4a462c6830ae7c4fe47ec"
UPSTREAM = "Qwen/Qwen3-VL-8B-Instruct"
DEFAULT_ROOT = Path.home() / "Downloads" / "AI-Models"


def main() -> None:
    import httpx
    from huggingface_hub import HfApi, hf_hub_download, snapshot_download

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    target = root / "Qwen3-VL-8B-Instruct-8bit"
    root.mkdir(parents=True, exist_ok=True)
    api = HfApi(token=False)
    info = api.model_info(REPO, revision=REVISION, files_metadata=True, token=False)
    expected_bytes = sum(item.size or 0 for item in info.siblings)
    if shutil.disk_usage(root).free < expected_bytes + 2_000_000_000 and not target.exists():
        raise RuntimeError("Not enough disk space for the model and verification files")
    started = time.monotonic()
    print(
        json.dumps(
            {
                "event": "download_started",
                "repo": REPO,
                "revision": REVISION,
                "path": str(target),
                "expected_bytes": expected_bytes,
            }
        ),
        flush=True,
    )
    snapshot_download(REPO, revision=REVISION, local_dir=target, token=False, max_workers=4)
    print("Download complete; verifying files and writing the provenance manifest.", flush=True)
    files = []
    for item in info.siblings:
        path = target / item.rfilename
        if not path.is_file():
            raise RuntimeError(f"Missing snapshot file: {item.rfilename}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(block)
        actual = digest.hexdigest()
        expected = getattr(item.lfs, "sha256", None) if item.lfs else None
        if expected and actual != expected:
            raise RuntimeError(f"Checksum mismatch: {item.rfilename}")
        if item.size is not None and path.stat().st_size != item.size:
            raise RuntimeError(f"Size mismatch: {item.rfilename}")
        files.append(
            {
                "path": item.rfilename,
                "bytes": path.stat().st_size,
                "sha256": actual,
                "upstream_lfs_sha256": expected,
            }
        )
    # The upstream HF repository declares a license in its card but has no
    # standalone LICENSE file. Preserve that declaration and the canonical text.
    # Never download upstream (unquantized) model weights.
    upstream = api.model_info(UPSTREAM, token=False)
    if getattr(upstream.card_data, "license", None) != "apache-2.0":
        raise RuntimeError("Upstream license declaration changed; review before use")
    license_dir = root / "licenses" / "Qwen3-VL-8B-Instruct"
    upstream_card = hf_hub_download(
        UPSTREAM, "README.md", revision=upstream.sha, local_dir=license_dir, token=False
    )
    license_url = "https://www.apache.org/licenses/LICENSE-2.0.txt"
    response = httpx.get(license_url, timeout=30, follow_redirects=True)
    response.raise_for_status()
    if "Apache License" not in response.text or "Version 2.0" not in response.text:
        raise RuntimeError("Unexpected Apache license response")
    license_path = license_dir / "LICENSE-2.0.txt"
    license_path.write_bytes(response.content)
    manifest = {
        "repo_id": REPO,
        "revision": REVISION,
        "source_url": f"https://huggingface.co/{REPO}",
        "upstream_repo": UPSTREAM,
        "upstream_card_revision": upstream.sha,
        "upstream_card_path": str(Path(upstream_card).relative_to(root)),
        "license": "Apache-2.0",
        "license_path": str(Path(license_path).relative_to(root)),
        "license_text_source": license_url,
        "license_text_sha256": hashlib.sha256(response.content).hexdigest(),
        "completed_at": datetime.now(UTC).isoformat(),
        "invocation_elapsed_seconds": round(time.monotonic() - started, 3),
        "total_bytes": sum(f["bytes"] for f in files),
        "files": files,
        "verification": "All snapshot files SHA-256 hashed; LFS checksums and file sizes checked",
        "upstream_index_note": (
            "This pinned snapshot retains an upstream 4-shard index but ships two 8-bit shards. "
            "Source files are unmodified. MLX-VLM 0.7.3 falls back to actual safetensors files; "
            "KitGuard checks the two verified file sizes explicitly."
        ),
        "credentials": "Public anonymous download (token=False); no credentials read by this script",
    }
    (root / "Qwen3-VL-8B-Instruct-8bit.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / "README_Qwen3-VL-8B-Instruct-8bit.md").write_text(
        "# KitGuard shared 8B baseline model\n\n"
        f"Model: [{REPO}](https://huggingface.co/{REPO})\n\n"
        f"Pinned revision: `{REVISION}`. Local directory: `{target.name}`.\n\n"
        "Format: MLX 8-bit for Apple Silicon Macs. Other compatible projects can reuse this "
        "same local model directory without another download. These are not RTX 3080/CUDA "
        "weights or Ollama GGUF files; those runtimes would need separately selected formats. "
        "No such additional model format was downloaded.\n\n"
        "This downloader manages only the MLX 8-bit baseline and preserves other shared models. "
        "Original model weights were not downloaded by this script; "
        "only its model card (license declaration) and the canonical Apache 2.0 license text were fetched.\n\n"
        "The repository's original README is inside the model directory. See the adjacent "
        "manifest for source revision, SHA-256 hashes, verified bytes, and license location. "
        "Downloaded weights do not establish accuracy on KitGuard parts; real photographs "
        "and task-specific evaluation are still required.\n",
        encoding="utf-8",
    )
    with (root / "README_Qwen3-VL-8B-Instruct-8bit.md").open("a", encoding="utf-8") as readme:
        readme.write(
            "\n## Upstream index compatibility\n\n"
            "The pinned community snapshot has a stale `model.safetensors.index.json` naming "
            "four upstream shards, while the quantized snapshot actually contains two shards. "
            "No original model file was edited: all original SHA-256 hashes remain valid. "
            "MLX-VLM 0.7.3 falls back to the actual local safetensors files. KitGuard's "
            "availability check uses the verified sizes of the two real shards.\n\n"
            "## Verification scope\n\n"
            "See `verification/kitguard_smoke_result.json` and `verification/README.md` "
            "for local engineering checks. Synthetic pictures are deliberately labeled and "
            "are not evidence of accuracy on real hardware.\n"
        )
    print(
        json.dumps(
            {
                "event": "verified",
                "total_bytes": manifest["total_bytes"],
                "invocation_elapsed_seconds": manifest["invocation_elapsed_seconds"],
                "files": len(files),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
