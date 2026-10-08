"""Real model inference on clearly labeled synthetic engineering inputs.

This is a wiring/JSON/schema smoke test, NOT a parts-recognition evaluation.
Run from the KitGuard environment, after the pinned model finishes verification.
"""
import json
import resource
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from kitguard.app import create_app
from kitguard.vision import LocalVision

root = Path(__file__).parent
vision = LocalVision()
report = {
    "scope": "Synthetic engineering smoke; not physical-part accuracy or field validation",
    "hardware": "Apple M5 Pro, 64 GiB unified memory, macOS 26.6.2",
    "started_at": datetime.now(UTC).isoformat(),
    "before": vision.status(),
}
assert report["before"]["available"], "Model snapshot is incomplete"
started = time.perf_counter()
proposal = vision.propose_revision("볼트는 1개 줄이고 와셔는 1개 늘려 주세요.",
                                  {"bolt": 1, "nut": 1, "washer": 1, "bracket": 1})
report["text"] = {"instruction": "볼트는 1개 줄이고 와셔는 1개 늘려 주세요.",
                  "proposal": proposal, "wall_seconds": round(time.perf_counter() - started, 3),
                  "model_status": vision.status()}
print(json.dumps({"text": report["text"]}, ensure_ascii=False), flush=True)
assert proposal["requirements"] == {"bolt": 0, "nut": 1, "washer": 2, "bracket": 1}
report["additional_text_cases"] = []
for instruction, expected in [
    ("螺栓改成2个，其他不变", {"bolt": 2, "nut": 1, "washer": 1, "bracket": 1}),
    ("螺栓100个", None),
]:
    started = time.perf_counter()
    try:
        result = vision.propose_revision(instruction, {"bolt": 1, "nut": 1, "washer": 1, "bracket": 1})
    except ValueError as exc:
        if expected is not None:
            raise
        case = {"instruction": instruction, "rejected": True, "clarification": str(exc)}
    else:
        case = {"instruction": instruction, "rejected": False, "proposal": result}
        assert expected is not None, "Out-of-range instruction was silently clamped or accepted"
        assert result["requirements"] == expected
    case["wall_seconds"] = round(time.perf_counter() - started, 3)
    case["model_status"] = vision.status()
    report["additional_text_cases"].append(case)
    print(json.dumps(case, ensure_ascii=False), flush=True)
started = time.perf_counter()
with TemporaryDirectory(prefix="kitguard-real-api-smoke-") as temporary:
    with TestClient(create_app(Path(temporary), analyzer=vision)) as client:
        response = client.post('/api/orders', json={
            'title': 'Synthetic engineering API smoke - not parts evaluation',
            'requirements': {'bolt': 1, 'nut': 1, 'washer': 1, 'bracket': 1},
        })
        response.raise_for_status()
        order = response.json()['order']
        with (root / 'synthetic_engineering_smoke.png').open('rb') as photo:
            response = client.post(f"/api/orders/{order['id']}/photos",
                                   data={'expected_revision': str(order['revision'])},
                                   files={'photo': ('synthetic_engineering_smoke.png', photo, 'image/png')})
        response.raise_for_status()
        photo_id = response.json()['photo']['id']
        response = client.post(f"/api/orders/{order['id']}/inspect", json={
            'photo_id': photo_id, 'expected_revision': order['revision'],
        })
        response.raise_for_status()
        result = response.json()
        assert result['check']['backend'] == 'mlx'
        assert result['check']['photo_id'] == photo_id
        assert result['order']['status'] != 'completed'
report["image"] = {"api_response": result, "wall_seconds": round(time.perf_counter() - started, 3),
                   "model_status": vision.status(), "input": "synthetic_engineering_smoke.png"}
report["process_max_rss_bytes_macos"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
report["finished_at"] = datetime.now(UTC).isoformat()
(root / "kitguard_smoke_result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"image": report["image"], "process_max_rss_bytes_macos":
                  report["process_max_rss_bytes_macos"]}, ensure_ascii=False), flush=True)
