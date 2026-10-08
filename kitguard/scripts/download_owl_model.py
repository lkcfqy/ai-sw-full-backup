"""Anonymous, pinned OWLv2 download; no model loading or accelerator work."""

from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import requests

REPO = "google/owlv2-base-patch16-ensemble"
REVISION = "cfd3195ba4ea9592eec887ded089f4c08eff231d"
TARGET = Path(__file__).resolve().parents[1] / "models/owlv2-base-patch16-ensemble"


def digest_file(path: Path) -> tuple[str, str]:
    sha256 = hashlib.sha256()
    blob = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            sha256.update(block)
            blob.update(block)
    return sha256.hexdigest(), blob.hexdigest()


def fetch(item: dict) -> dict:
    name = item["rfilename"]
    path = TARGET / name
    url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}"
    if not path.exists():
        partial = path.with_name(path.name + ".partial")
        # A failed incomplete download may be replaced; verified final files never are.
        for attempt in range(4):
            try:
                with requests.get(url, stream=True, timeout=(30, 60)) as response:
                    response.raise_for_status()
                    with partial.open("wb") as handle:
                        for chunk in response.iter_content(2 * 1024 * 1024):
                            handle.write(chunk)
                if partial.stat().st_size != item["size"]:
                    raise RuntimeError(f"Incomplete file: {name}")
                partial.rename(path)
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(attempt + 1)
    sha256, git_blob = digest_file(path)
    expected = item.get("lfs", {}).get("sha256")
    if path.stat().st_size != item["size"]:
        raise RuntimeError(f"Size mismatch; existing file left untouched: {name}")
    if expected and sha256 != expected:
        raise RuntimeError(f"LFS SHA-256 mismatch: {name}")
    if not expected and git_blob != item["blobId"]:
        raise RuntimeError(f"Git blob SHA-1 mismatch: {name}")
    print(f"Verified {name}: {path.stat().st_size} bytes", flush=True)
    return {
        "path": name,
        "bytes": path.stat().st_size,
        "sha256": sha256,
        "upstream_lfs_sha256": expected,
        "upstream_git_blob_sha1": item["blobId"],
        "git_blob_sha1_checked": not bool(expected),
        "url": url,
    }


def main() -> None:
    metadata_url = f"https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true"
    response = requests.get(metadata_url, timeout=30)
    response.raise_for_status()
    info = response.json()
    if info["sha"] != REVISION or info["cardData"]["license"] != "apache-2.0":
        raise RuntimeError("Pinned model identity/license mismatch")
    TARGET.mkdir(parents=True, exist_ok=True)
    files = [item for item in info["siblings"] if item["rfilename"] != "pytorch_model.bin"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        verified = list(pool.map(fetch, files))
    license_url = "https://www.apache.org/licenses/LICENSE-2.0.txt"
    response = requests.get(license_url, timeout=30)
    response.raise_for_status()
    if "Apache License" not in response.text or "Version 2.0" not in response.text:
        raise RuntimeError("Unexpected canonical license response")
    license_path = TARGET / "LICENSE"
    if license_path.exists() and license_path.read_bytes() != response.content:
        raise RuntimeError("Existing license differs; not overwriting")
    if not license_path.exists():
        license_path.write_bytes(response.content)
    manifest = {
        "repo_id": REPO,
        "revision": REVISION,
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "license": "Apache-2.0",
        "license_declaration": "Pinned original README.md model card",
        "license_text_source": license_url,
        "license_note": "Canonical Apache text; pinned HF repository has no standalone LICENSE",
        "license_sha256": hashlib.sha256(response.content).hexdigest(),
        "license_bytes": len(response.content),
        "metadata_source": metadata_url,
        "files": verified,
        "upstream_files_bytes": sum(item["bytes"] for item in verified),
        "excluded": {"pytorch_model.bin": "Duplicate unsafe pickle serialization; safetensors retained"},
        "verification": "Every upstream file: size + LFS SHA-256 or Git blob SHA-1; all local SHA-256 saved",
        "credentials": "Anonymous HTTPS requests; no Hugging Face tokens read",
        "runtime": "No inference/model loading by downloader",
    }
    for name, data in (("UPSTREAM_API_METADATA.json", info), ("DOWNLOAD_MANIFEST.json", manifest)):
        destination = TARGET / name
        if destination.exists():
            raise RuntimeError(f"Refusing to overwrite existing manifest: {name}")
        destination.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps({"event": "verified", "bytes": manifest["upstream_files_bytes"], "path": str(TARGET)}),
        flush=True,
    )


if __name__ == "__main__":
    main()
