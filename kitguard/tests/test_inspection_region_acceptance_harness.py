"""CPU-only harness checks: HTTP persistence and failure denominators, no MLX."""

import importlib.util
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_inspection_region_acceptance.py"
SPEC = importlib.util.spec_from_file_location("region_acceptance_review", SCRIPT)
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


def test_http_recorder_preserves_failed_request_and_response_bytes(tmp_path, monkeypatch):
    body = b'{"detail":"intentional isolated fixture failure"}'

    def reject(request, timeout):
        assert timeout == 360
        assert request.get_method() == "POST"
        raise HTTPError(request.full_url, 503, "Synthetic failure", {}, io.BytesIO(body))

    monkeypatch.setattr(harness, "urlopen", reject)
    recorder = harness.HTTP(tmp_path)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        recorder.request("fixture-inspect", "/api/orders/fixture/inspect", {"expected_revision": 1})
    assert (tmp_path / "http/001-fixture-inspect.response.body").read_bytes() == body
    receipt = harness.read_json(tmp_path / "http/001-fixture-inspect.receipt.json")
    assert receipt["status"] == 503
    assert receipt["response_sha256"] == harness.sha(body)
    assert receipt["request_body_sha256"] == harness.file_sha(tmp_path / "http/001-fixture-inspect.request.body")
    assert len(harness.read_json(tmp_path / "http-index.json")) == 1


def test_real_runner_retains_both_failed_calls_without_retry_using_a_synthetic_http_adapter(
    tmp_path, monkeypatch, client, analyzer, image_bytes
):
    base = tmp_path / "fake-run"
    base.mkdir()
    image = tmp_path / "synthetic.png"
    image.write_bytes(image_bytes())
    root, size = harness.normalize(image.read_bytes())
    rect = [0, 0, *size]
    cases = []
    for identifier, field in (("ino-A41-author-region", False), ("mixed-screws-full-region", True)):
        counts = {"bolt": 3 if field else 0, "nut": 0, "washer": 0, "bracket": 0 if field else 1}
        cases.append({"id": identifier, "image": str(image), "image_sha256": harness.file_sha(image),
                      "field_registration": field, "requirements": counts,
                      "ground_truth": counts if field else {"bracket": 1}, "region_xyxy": rect,
                      "expected_root_sha256": harness.sha(root), "expected_view_sha256": harness.sha(harness.crop_bytes(root, rect))})
    harness.write_json(base / "SOURCE_PLAN.json", {"scope": "SYNTHETIC ENGINEERING FIXTURE ONLY", "cases": cases})
    harness.write_json(base / "PLAN_FREEZE.json", {"fixture": True})
    harness.write_json(base / "server.json", {"freeze_sha256": harness.file_sha(base / "PLAN_FREEZE.json")})
    frozen = {"source_sha256": {harness.SCRIPT: harness.file_sha(SCRIPT)}}
    monkeypatch.setattr(harness, "verify_freeze", lambda _: frozen)
    status = analyzer.status
    monkeypatch.setattr(analyzer, "status", lambda: {**status(), "loaded": False,
        "repo_id": harness.REPO, "revision": harness.REVISION, "observation_mode": "spatial_guarded",
        "image_max_side": 1536, "observer_protocol_sha256": "f"*64})
    attempted = []

    class Response:
        def __init__(self, response):
            self.status, self.headers, self.body = response.status_code, response.headers, response.content

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self):
            return self.body

    def isolated_http(request, timeout):
        del timeout
        endpoint = request.full_url.removeprefix(harness.URL)
        if endpoint == "/api/public-demos/mixed-screws/orders":
            # This is a synthetic fixture; no public dataset or saved model result is used.
            created = client.post("/api/orders", json={"title": "SYNTHETIC REGION HARNESS", "requirements": cases[1]["requirements"]})
            order = created.json()["order"]
            response = client.post(f"/api/orders/{order['id']}/photos", data={"expected_revision": 1},
                                   files={"photo": ("synthetic.png", image.read_bytes(), "image/png")})
        else:
            if endpoint.endswith("/inspect"):
                attempted.append(endpoint)
            response = client.request(request.get_method(), endpoint, content=request.data,
                                      headers=dict(request.header_items()))
        if response.status_code >= 400:
            raise HTTPError(request.full_url, response.status_code, "Fixture response", response.headers, io.BytesIO(response.content))
        return Response(response)

    monkeypatch.setattr(harness, "urlopen", isolated_http)
    assert harness.run(base) == 1  # Synthetic observer lacks guarded passes; real API rejects both calls.
    result = harness.read_json(base / "result.json")
    assert result["planned_inspections"] == result["attempted_inspections"] == len(attempted) == 2
    assert result["source_changed"] is False
    assert all(c["status"] == "failed" and "HTTP 503" in c["error"] for c in result["cases"])
    responses = [r for r in harness.read_json(base / "http-index.json") if r["endpoint"].endswith("/inspect")]
    assert len(responses) == 2 and all(r["status"] == 503 for r in responses)
    assert result["study"]["status"] == "closed"
    assert (base / "public-replay-evidence.zip").is_file()
    assert all((base / c["id"] / "order-evidence.zip").is_file() for c in cases)
    assert result["study"]["report"]["methods"]["kitguard"]["failed"] == 1
    with pytest.raises(RuntimeError, match="never retry"):
        harness.run(base)
    assert len(attempted) == 2


def test_prepare_geometry_and_partial_truth_have_no_model_side_effects():
    if not (harness.ROOT / "datasets/raw/ino-10-190/data/origin/A/41_color.png").exists():
        pytest.skip("Optional author dataset is outside portable source archive")
    plan = harness.source_plan()
    first, second = plan["cases"]
    assert plan["status"] == "prepared_not_frozen_not_executed"
    assert first["ground_truth"] == {"bracket": 1}
    assert first["region_xyxy"] == [436, 511, 606, 627]
    assert second["ground_truth"] == {"bolt": 3, "nut": 0, "washer": 0, "bracket": 0}
    assert second["region_xyxy"] == [0, 0, 768, 576]
    assert json.dumps(plan, allow_nan=False)
