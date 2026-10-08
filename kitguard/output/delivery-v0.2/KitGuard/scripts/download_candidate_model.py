"""Fetch a pinned public MLX candidate and verify every upstream file; never load it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

REPO = "mlx-community/Qwen3.6-27B-4bit"
REVISION = "c000ac2c2057d94be3fa931000c31723aac53282"
UPSTREAM = "Qwen/Qwen3.6-27B"
UPSTREAM_REVISION = "6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"
NAME = "Qwen3.6-27B-4bit"
EXPECTED_BYTES = 16_081_490_064


def emit(event: str, **values) -> None:
    print(json.dumps({"event": event, **values}, ensure_ascii=False), flush=True)


def file_metadata(item) -> dict:
    return {
        "path": item.rfilename,
        "bytes": item.size,
        "upstream_git_blob_sha1": item.blob_id,
        "upstream_lfs_sha256": item.lfs.sha256 if item.lfs else None,
    }


def verify(path: Path, expected: dict) -> dict:
    size = path.stat().st_size
    if size != expected["bytes"]:
        raise RuntimeError(f"Size mismatch: {path.name}: {size} != {expected['bytes']}")
    sha256 = hashlib.sha256()
    git_sha1 = hashlib.sha1(f"blob {size}\0".encode())
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            sha256.update(block)
            git_sha1.update(block)
    digest = sha256.hexdigest()
    if expected["upstream_lfs_sha256"]:
        if digest != expected["upstream_lfs_sha256"]:
            raise RuntimeError(f"LFS SHA-256 mismatch: {path.name}")
        comparison = "upstream_lfs_sha256"
    else:
        if git_sha1.hexdigest() != expected["upstream_git_blob_sha1"]:
            raise RuntimeError(f"Upstream Git blob SHA-1 mismatch: {path.name}")
        comparison = "upstream_git_blob_sha1"
    return {**expected, "sha256": digest, "verified_against": comparison}


def ranged_large_file(url: str, partial: Path, expected_bytes: int) -> None:
    """Use two bounded streams per large file, preserving a prior sequential prefix."""
    import httpx

    prefix_size = partial.stat().st_size if partial.exists() else 0
    if prefix_size == expected_bytes:
        return
    chunk_dir = partial.parent / ".download-chunks" / partial.name
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_size = 128 * 1024 * 1024
    spans = [
        (start, min(start + chunk_size, expected_bytes) - 1)
        for start in range(prefix_size, expected_bytes, chunk_size)
    ]

    def fetch_span(span: tuple[int, int]) -> Path:
        start, end = span
        path = chunk_dir / f"{start}-{end}"
        length = end - start + 1
        for attempt in range(1, 7):
            available = path.stat().st_size if path.exists() else 0
            if available == length:
                return path
            if available > length:
                raise RuntimeError("Oversized ranged chunk")
            offset = start + available
            try:
                with httpx.stream(
                    "GET",
                    url,
                    follow_redirects=True,
                    headers={"Range": f"bytes={offset}-{end}", "Accept-Encoding": "identity"},
                    timeout=httpx.Timeout(60, connect=30),
                ) as response:
                    response.raise_for_status()
                    if response.status_code != 206 or response.headers.get("content-range") != (
                        f"bytes {offset}-{end}/{expected_bytes}"
                    ):
                        raise RuntimeError("Server did not honor exact ranged request")
                    with path.open("ab") as handle:
                        for block in response.iter_bytes(1024 * 1024):
                            handle.write(block)
                if path.stat().st_size != length:
                    raise RuntimeError("Incomplete ranged response")
                return path
            except (httpx.HTTPError, OSError) as error:
                emit(
                    "range_retry",
                    path=partial.name,
                    offset=offset,
                    attempt=attempt,
                    error_type=type(error).__name__,
                )
                if attempt == 6:
                    raise
                time.sleep(min(2**attempt, 30))
        raise RuntimeError("Unreachable ranged state")

    with ThreadPoolExecutor(max_workers=2) as pool:
        chunks = list(pool.map(fetch_span, spans))
    # Build separately: an interrupted assembly cannot be mistaken for a new prefix.
    assembly = partial.with_name(partial.name + ".assembly")
    with assembly.open("wb") as output:
        if prefix_size:
            with partial.open("rb") as source:
                shutil.copyfileobj(source, output, 8 * 1024 * 1024)
        for chunk in chunks:
            with chunk.open("rb") as source:
                shutil.copyfileobj(source, output, 8 * 1024 * 1024)
    if assembly.stat().st_size != expected_bytes:
        raise RuntimeError("Assembled file size mismatch")
    assembly.replace(partial)
    shutil.rmtree(chunk_dir)


def download_file(repo: str, revision: str, directory: Path, expected: dict) -> dict:
    import httpx

    relative = Path(expected["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError("Unsafe upstream filename")
    destination = directory / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return verify(destination, expected)
    partial = destination.with_name(destination.name + ".incomplete")
    url = f"https://huggingface.co/{repo}/resolve/{revision}/{quote(expected['path'])}"
    if expected["bytes"] >= 1_000_000_000:
        ranged_large_file(url, partial, expected["bytes"])
        verified = verify(partial, expected)
        partial.replace(destination)
        emit("file_verified", path=expected["path"], bytes=expected["bytes"])
        return verified
    for attempt in range(1, 7):
        try:
            start = partial.stat().st_size if partial.exists() else 0
            if start > expected["bytes"]:
                raise RuntimeError(f"Oversized partial file: {partial.name}")
            if start < expected["bytes"]:
                headers = {"Accept-Encoding": "identity"}
                if start:
                    headers["Range"] = f"bytes={start}-"
                with httpx.stream(
                    "GET",
                    url,
                    headers=headers,
                    follow_redirects=True,
                    timeout=httpx.Timeout(60, connect=30),
                ) as response:
                    response.raise_for_status()
                    if response.status_code == 206:
                        content_range = response.headers.get("content-range", "")
                        if not content_range.startswith(f"bytes {start}-") or not content_range.endswith(
                            f"/{expected['bytes']}"
                        ):
                            raise RuntimeError(f"Unexpected Content-Range: {partial.name}")
                        mode = "ab" if start else "wb"
                    elif response.status_code == 200:
                        mode = "wb"  # A server ignoring Range must never be appended.
                    else:
                        raise RuntimeError(f"Unexpected download status {response.status_code}")
                    with partial.open(mode) as handle:
                        for block in response.iter_bytes(1024 * 1024):
                            handle.write(block)
            verified = verify(partial, expected)
            partial.replace(destination)
            emit("file_verified", path=expected["path"], bytes=expected["bytes"])
            return verified
        except (httpx.HTTPError, OSError) as error:
            emit("download_retry", path=expected["path"], attempt=attempt, error_type=type(error).__name__)
            if attempt == 6:
                raise
            time.sleep(min(2**attempt, 30))
    raise RuntimeError("Unreachable download state")


def write_json(path: Path, value: dict) -> None:
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def main() -> None:
    from huggingface_hub import HfApi

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / "Downloads" / "AI-Models")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=3)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    target = root / NAME
    provenance = root / "provenance" / NAME
    target.mkdir(parents=True, exist_ok=True)
    provenance.mkdir(parents=True, exist_ok=True)
    api = HfApi(token=False)
    info = api.model_info(REPO, revision=REVISION, files_metadata=True, token=False)
    upstream = api.model_info(UPSTREAM, revision=UPSTREAM_REVISION, files_metadata=True, token=False)
    if info.sha != REVISION or upstream.sha != UPSTREAM_REVISION:
        raise RuntimeError("Resolved revision mismatch")
    for model in (info, upstream):
        if model.card_data.license != "apache-2.0":
            raise RuntimeError("License declaration changed; candidate requires review")
    expected = [file_metadata(item) for item in info.siblings]
    if len(expected) != 16 or sum(item["bytes"] for item in expected) != EXPECTED_BYTES:
        raise RuntimeError("Pinned snapshot inventory differs from reviewed candidate")
    if shutil.disk_usage(root).free < EXPECTED_BYTES + 2_000_000_000:
        raise RuntimeError("Insufficient free space")
    write_json(
        provenance / "snapshot_metadata.json",
        {
            "repo_id": REPO,
            "revision": info.sha,
            "card_data": info.card_data.to_dict(),
            "files": expected,
            "retrieved_at": datetime.now(UTC).isoformat(),
        },
    )
    write_json(
        provenance / "upstream_metadata.json",
        {
            "repo_id": UPSTREAM,
            "revision": upstream.sha,
            "card_data": upstream.card_data.to_dict(),
            "files": [file_metadata(item) for item in upstream.siblings],
            "note": "Metadata only: original upstream weights are not downloaded.",
        },
    )
    started = time.monotonic()
    emit(
        "download_started",
        repo=REPO,
        revision=REVISION,
        target=str(target),
        expected_bytes=EXPECTED_BYTES,
        workers=args.workers,
    )
    verified = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        remaining = {pool.submit(download_file, REPO, REVISION, target, item) for item in expected}
        while remaining:
            done, remaining = wait(remaining, timeout=15, return_when=FIRST_COMPLETED)
            for future in done:
                verified.append(future.result())
            on_disk = sum(path.stat().st_size for path in target.rglob("*") if path.is_file())
            emit(
                "progress",
                downloaded_bytes=on_disk,
                expected_bytes=EXPECTED_BYTES,
                verified_files=len(verified),
                elapsed_seconds=round(time.monotonic() - started, 1),
            )
    license_dir = root / "licenses" / "Qwen3.6-27B"
    license_files = []
    for item in upstream.siblings:
        if item.rfilename in {"README.md", "LICENSE"}:
            record = download_file(UPSTREAM, UPSTREAM_REVISION, license_dir, file_metadata(item))
            license_files.append({**record, "local_path": str(license_dir / item.rfilename)})
    if {record["path"] for record in license_files} != {"README.md", "LICENSE"}:
        raise RuntimeError("Missing original upstream model card or license")
    config = json.loads((target / "config.json").read_text())
    index = json.loads((target / "model.safetensors.index.json").read_text())
    actual_shards = {item["path"] for item in verified if item["path"].endswith(".safetensors")}
    indexed_shards = set(index["weight_map"].values())
    if indexed_shards != actual_shards:
        raise RuntimeError("Safetensors index references a different shard inventory")
    manifest = {
        "repo_id": REPO,
        "revision": REVISION,
        "source_url": f"https://huggingface.co/{REPO}/tree/{REVISION}",
        "local_directory": str(target),
        "upstream_repo": UPSTREAM,
        "upstream_card_revision": UPSTREAM_REVISION,
        "license": "Apache-2.0",
        "license_and_original_card": license_files,
        "completed_at": datetime.now(UTC).isoformat(),
        "invocation_elapsed_seconds": round(time.monotonic() - started, 3),
        "total_bytes": sum(item["bytes"] for item in verified),
        "weight_bytes": sum(item["bytes"] for item in verified if item["path"] in actual_shards),
        "files": sorted(verified, key=lambda item: item["path"]),
        "model_type": config.get("model_type"),
        "quantization": config.get("quantization"),
        "verification": "Every file SHA-256 hashed and size checked; LFS payloads compared to "
        "upstream SHA-256, non-LFS files compared to upstream Git blob SHA-1. "
        "Safetensors index shard inventory matches downloaded weights.",
        "status": "files_verified_runtime_not_tested",
        "performance_note": "No model was loaded by this downloader. File integrity does not "
        "establish runtime compatibility, memory use, latency, or KitGuard accuracy.",
        "credentials": "Public anonymous download; HF token=False, no credential use by this script.",
    }
    write_json(root / f"{NAME}.manifest.json", manifest)
    emit(
        "verified",
        manifest=str(root / f"{NAME}.manifest.json"),
        total_bytes=manifest["total_bytes"],
        weight_bytes=manifest["weight_bytes"],
        files=len(verified),
        status=manifest["status"],
    )


if __name__ == "__main__":
    main()
