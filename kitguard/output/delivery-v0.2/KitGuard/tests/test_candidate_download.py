"""Synthetic bytes test download integrity plumbing, never model quality or inference."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "download_candidate_model.py"
SPEC = importlib.util.spec_from_file_location("candidate_downloader", MODULE_PATH)
downloader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(downloader)


def metadata(payload: bytes, *, lfs: bool) -> dict:
    return {
        "path": "synthetic.bin",
        "bytes": len(payload),
        "upstream_git_blob_sha1": hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest(),
        "upstream_lfs_sha256": hashlib.sha256(payload).hexdigest() if lfs else None,
    }


@pytest.mark.parametrize("lfs", [False, True])
def test_verifies_against_upstream_not_only_local_hash(tmp_path, lfs):
    payload = b"SYNTHETIC DOWNLOAD INTEGRITY FIXTURE"
    file = tmp_path / "synthetic.bin"
    file.write_bytes(payload)
    result = downloader.verify(file, metadata(payload, lfs=lfs))
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["verified_against"] == ("upstream_lfs_sha256" if lfs else "upstream_git_blob_sha1")
    file.write_bytes(payload[:-1] + b"X")
    with pytest.raises(RuntimeError, match="mismatch"):
        downloader.verify(file, metadata(payload, lfs=lfs))


def test_size_mismatch_is_rejected_before_hash(tmp_path):
    file = tmp_path / "synthetic.bin"
    file.write_bytes(b"short")
    with pytest.raises(RuntimeError, match="Size mismatch"):
        downloader.verify(file, metadata(b"longer fixture", lfs=True))


class FakeRangeResponse:
    def __init__(self, payload: bytes, start: int, end: int, status=206, bad_range=False):
        self.status_code = status
        self.headers = {"content-range": "unexpected" if bad_range else f"bytes {start}-{end}/{len(payload)}"}
        self.payload = payload[start : end + 1]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        return None

    def iter_bytes(self, _):
        yield self.payload


@pytest.mark.parametrize("prefix_size", [0, 11, 128])
def test_ranges_preserve_sequential_prefix(tmp_path, monkeypatch, prefix_size):
    payload = bytes(range(256))
    partial = tmp_path / "fixture.incomplete"
    if prefix_size:
        partial.write_bytes(payload[:prefix_size])
    requests = []

    def stream(method, url, *, headers, **kwargs):
        start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
        requests.append((start, end))
        return FakeRangeResponse(payload, start, end)

    monkeypatch.setattr("httpx.stream", stream)
    downloader.ranged_large_file("https://invalid.test/fixture", partial, len(payload))
    assert partial.read_bytes() == payload
    assert requests == [(prefix_size, len(payload) - 1)]
    assert not partial.with_name(partial.name + ".assembly").exists()


@pytest.mark.parametrize("status,bad_range", [(200, False), (206, True)])
def test_ranges_reject_ignored_or_mismatched_response(tmp_path, monkeypatch, status, bad_range):
    payload = b"SYNTHETIC DATA"
    partial = tmp_path / "fixture.incomplete"
    partial.write_bytes(payload[:3])
    monkeypatch.setattr(
        "httpx.stream",
        lambda *args, **kwargs: FakeRangeResponse(
            payload, 3, len(payload) - 1, status=status, bad_range=bad_range
        ),
    )
    with pytest.raises(RuntimeError, match="exact ranged request"):
        downloader.ranged_large_file("https://invalid.test/fixture", partial, len(payload))
    assert partial.read_bytes() == payload[:3]
    assert not partial.with_name(partial.name + ".assembly").exists()
