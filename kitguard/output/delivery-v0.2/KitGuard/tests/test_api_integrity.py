"""Meaningful API state/validation checks with an explicitly fake observer.

These tests verify application invariants. They do not measure model vision
accuracy, physical kit verification, or competition performance.
"""

from __future__ import annotations

import asyncio
import json
import struct
import zlib
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import httpx
import pytest
from conftest import REQUIREMENTS, FakeAnalyzer
from fastapi.testclient import TestClient
from PIL import Image


def get_order(client, order_id):
    response = client.get(f"/api/orders/{order_id}")
    assert response.status_code == 200, response.text
    return response.json()["order"]


def inspect(client, order, photo_id):
    return client.post(
        f"/api/orders/{order['id']}/inspect",
        json={"photo_id": photo_id, "expected_revision": order["revision"]},
    )


def complete_body(order, check_id, key="test-completion-1", confirmed=True):
    return {
        "check_id": check_id,
        "expected_revision": order["revision"],
        "confirmed": confirmed,
        "idempotency_key": key,
    }


def assert_not_ready(order):
    assert order["status"] not in ("ready", "completed")
    check = order.get("latest_check")
    assert not check or not check.get("valid") or check["decision"] != "ready"


@pytest.mark.parametrize(
    "requirements",
    [
        {**REQUIREMENTS, "bolt": -1},
        {**REQUIREMENTS, "bolt": 4},
        {**REQUIREMENTS, "bolt": 1.5},
        {**REQUIREMENTS, "bolt": True},
        {**REQUIREMENTS, "bolt": "2"},
        {**REQUIREMENTS, "bolt": None},
        {part: 0 for part in REQUIREMENTS},
        {part: value for part, value in REQUIREMENTS.items() if part != "bracket"},
        {**REQUIREMENTS, "unexpected_part": 1},
    ],
)
def test_invalid_requirements_rejected_without_creating_order(client, requirements):
    response = client.post("/api/orders", json={"title": "Invalid test order", "requirements": requirements})
    assert 400 <= response.status_code < 500, response.text
    assert client.get("/api/orders").json()["orders"] == []


def test_invalid_revision_leaves_previous_state_intact(client, inspected):
    order = inspected["order"]
    response = client.post(
        f"/api/orders/{order['id']}/revise",
        json={"requirements": {**REQUIREMENTS, "washer": -1}, "instruction": "bad", "expected_revision": 1},
    )
    assert 400 <= response.status_code < 500, response.text
    current = get_order(client, order["id"])
    assert current["revision"] == order["revision"]
    assert current["status"] == "ready"
    assert current["requirements"] == order["requirements"]


@pytest.mark.parametrize("payload,mime", [(b"not an image", "image/png"), (b"", "image/jpeg")])
def test_undecodable_photo_does_not_mutate_order(client, order, upload, payload, mime):
    response = upload(order, payload=payload, mime=mime)
    assert 400 <= response.status_code < 500, response.text
    assert get_order(client, order["id"])["photos"] == []


def test_oversize_photo_is_rejected(client, order, upload, image_bytes):
    payload = image_bytes() + b"\x00" * (13 * 1024 * 1024)
    response = upload(order, payload=payload)
    assert 400 <= response.status_code < 500, response.text
    assert get_order(client, order["id"])["photos"] == []


def test_unsupported_decodable_image_is_rejected(client, order, upload, image_bytes):
    response = upload(order, payload=image_bytes(format="GIF"), name="pretends.png", mime="image/png")
    assert 400 <= response.status_code < 500, response.text
    assert get_order(client, order["id"])["photos"] == []


@pytest.mark.parametrize("image_format,mime", [("WEBP", "image/webp"), ("PNG", "image/png")])
def test_animated_input_is_rejected_instead_of_silently_using_first_frame(
    client, order, upload, image_format, mime
):
    first = Image.new("RGB", (640, 480), "white")
    second = Image.new("RGB", (640, 480), "black")
    output = BytesIO()
    first.save(output, format=image_format, save_all=True, append_images=[second], duration=100, loop=0)
    assert getattr(Image.open(BytesIO(output.getvalue())), "n_frames", 1) == 2
    response = upload(order, payload=output.getvalue(), name=f"animation.{image_format.lower()}", mime=mime)
    assert 400 <= response.status_code < 500, response.text
    assert get_order(client, order["id"])["photos"] == []


def test_huge_decoded_dimensions_rejected_without_allocating_image(client, order, upload, image_bytes):
    # Mutate only a PNG header; never allocate a 30,000 x 30,000 pixel image.
    payload = bytearray(image_bytes())
    payload[16:24] = struct.pack(">II", 30_000, 30_000)
    payload[29:33] = struct.pack(">I", zlib.crc32(payload[12:29]) & 0xFFFFFFFF)
    response = upload(order, payload=bytes(payload))
    assert 400 <= response.status_code < 500, response.text
    assert get_order(client, order["id"])["photos"] == []


def test_photo_roundtrip_strips_exif_and_ignores_filename(client, order, upload, image_bytes):
    response = upload(
        order,
        payload=image_bytes(format="JPEG", exif=True),
        name="../../outside-test-image.jpg",
        mime="image/jpeg",
    )
    assert response.status_code == 201, response.text
    photo = response.json()["photo"]
    served = client.get(photo["url"])
    assert served.status_code == 200
    decoded = Image.open(BytesIO(served.content))
    assert not dict(decoded.getexif())
    assert decoded.size == (photo["width"], photo["height"])
    assert ".." not in photo["url"]


def test_new_photo_invalidates_previous_readiness(client, inspected, upload):
    order = inspected["order"]
    check = inspected["check"]
    response = upload(order, seed=1)
    assert response.status_code == 201, response.text
    current = get_order(client, order["id"])
    assert_not_ready(current)
    rejected = client.post(f"/api/orders/{order['id']}/complete", json=complete_body(order, check["id"]))
    assert rejected.status_code == 409, rejected.text


def test_revision_invalidates_previous_check_and_rejects_old_photo(client, inspected):
    order = inspected["order"]
    response = client.post(
        f"/api/orders/{order['id']}/revise",
        json={
            "requirements": {**REQUIREMENTS, "bolt": 3},
            "instruction": "TEST: bolt 3",
            "expected_revision": order["revision"],
        },
    )
    assert response.status_code == 200, response.text
    current = response.json()["order"]
    assert current["revision"] == order["revision"] + 1
    assert_not_ready(current)
    assert inspect(client, current, inspected["check"]["photo_id"]).status_code == 409
    stale = client.post(
        f"/api/orders/{order['id']}/revise",
        json={"requirements": REQUIREMENTS, "instruction": "stale", "expected_revision": order["revision"]},
    )
    assert stale.status_code == 409, stale.text


def test_revision_proposal_does_not_mutate_order(client, order, analyzer):
    analyzer.proposal = {"requirements": {**REQUIREMENTS, "bolt": 3}, "explanation": "TEST proposal"}
    before = get_order(client, order["id"])
    response = client.post(
        f"/api/orders/{order['id']}/propose-revision",
        json={"instruction": "bolt 3", "expected_revision": order["revision"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["proposal"]["base_revision"] == before["revision"]
    assert get_order(client, order["id"]) == before


def test_malformed_proposal_never_changes_order(client, order, analyzer):
    analyzer.proposal = {"requirements": {**REQUIREMENTS, "bolt": 50}, "explanation": "invalid TEST"}
    before = get_order(client, order["id"])
    response = client.post(
        f"/api/orders/{order['id']}/propose-revision",
        json={"instruction": "bad proposal", "expected_revision": order["revision"]},
    )
    assert response.status_code >= 400, response.text
    assert get_order(client, order["id"]) == before


@pytest.mark.parametrize("mutation", ["revision", "photo", "reference"])
def test_mutation_during_inference_cannot_commit_stale_success(client, order, upload, image_bytes, analyzer, mutation):
    posted = upload(order)
    assert posted.status_code == 201, posted.text
    photo_id = posted.json()["photo"]["id"]
    analyzer.release.clear()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(inspect, client, order, photo_id)
        try:
            assert analyzer.started.wait(timeout=5), "Inference never reached the injected observer"
            if mutation == "revision":
                changed = client.post(
                    f"/api/orders/{order['id']}/revise",
                    json={
                        "requirements": {**REQUIREMENTS, "bolt": 3},
                        "instruction": "Concurrent change",
                        "expected_revision": order["revision"],
                    },
                )
            elif mutation == "photo":
                changed = upload(order, seed=2)
            else:
                changed = client.post(
                    f"/api/orders/{order['id']}/references/bolt",
                    files={"photo": ("reference.png", image_bytes(3), "image/png")},
                )
            assert changed.status_code in (200, 201), changed.text
        finally:
            analyzer.release.set()
        response = future.result(timeout=5)
    assert response.status_code == 409, response.text
    assert_not_ready(get_order(client, order["id"]))


def test_reference_change_invalidates_existing_check(client, inspected, image_bytes):
    order = inspected["order"]
    response = client.post(
        f"/api/orders/{order['id']}/references/bolt",
        files={"photo": ("reference.png", image_bytes(4), "image/png")},
    )
    assert response.status_code in (200, 201), response.text
    assert_not_ready(response.json()["order"])
    rejected = client.post(
        f"/api/orders/{order['id']}/complete",
        json=complete_body(order, inspected["check"]["id"]),
    )
    assert rejected.status_code == 409, rejected.text


def test_confirmation_is_required_and_cannot_be_coerced(client, inspected):
    order = inspected["order"]
    route = f"/api/orders/{order['id']}/complete"
    for value in (False, "true", 1, None):
        response = client.post(route, json=complete_body(order, inspected["check"]["id"], confirmed=value))
        assert 400 <= response.status_code < 500, response.text
        assert get_order(client, order["id"])["status"] == "ready"


def test_completion_is_atomic_idempotent_and_conflicts_reject(client, inspected):
    order = inspected["order"]
    route = f"/api/orders/{order['id']}/complete"
    body = complete_body(order, inspected["check"]["id"])
    first = client.post(route, json=body)
    assert first.status_code == 200, first.text
    first_result = first.json()
    assert first_result["order"]["status"] == "completed"
    assert first_result["completion"]["replayed"] is False
    assert get_order(client, order["id"])["status"] == "completed"
    again = client.post(route, json=body)
    assert again.status_code == 200, again.text
    assert again.json()["completion"]["id"] == first_result["completion"]["id"]
    assert again.json()["completion"]["replayed"] is True
    conflict = client.post(route, json={**body, "check_id": "different-check"})
    assert conflict.status_code == 409, conflict.text


def test_revision_after_completion_keeps_historical_evidence(client, inspected):
    order = inspected["order"]
    check = inspected["check"]
    completed = client.post(
        f"/api/orders/{order['id']}/complete", json=complete_body(order, check["id"])
    )
    assert completed.status_code == 200, completed.text
    completion_id = completed.json()["completion"]["id"]
    changed = client.post(
        f"/api/orders/{order['id']}/revise",
        json={
            "requirements": {**REQUIREMENTS, "washer": 1},
            "instruction": "After completion change",
            "expected_revision": order["revision"],
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["order"]["status"] == "pending"
    exported = client.get(f"/api/orders/{order['id']}/export")
    assert exported.status_code == 200
    history = json.dumps(exported.json())
    for identifier in (completion_id, check["id"], check["photo_id"]):
        assert identifier in history


def test_concurrent_identical_completion_creates_one_record(client, inspected):
    order = inspected["order"]
    route = f"/api/orders/{order['id']}/complete"
    body = complete_body(order, inspected["check"]["id"], key="concurrent-completion")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(client.post, route, json=body) for _ in range(2)]
        responses = [future.result(timeout=5) for future in futures]
    assert [response.status_code for response in responses] == [200, 200]
    completions = [response.json()["completion"] for response in responses]
    assert completions[0]["id"] == completions[1]["id"]
    assert sorted(item["replayed"] for item in completions) == [False, True]


def test_idempotency_key_cannot_be_reused_for_another_order(client, inspected, upload):
    first_order = inspected["order"]
    key = "global-order-bound-key"
    first = client.post(
        f"/api/orders/{first_order['id']}/complete",
        json=complete_body(first_order, inspected["check"]["id"], key=key),
    )
    assert first.status_code == 200, first.text
    second_order = client.post(
        "/api/orders", json={"title": "Second kit", "requirements": REQUIREMENTS}
    ).json()["order"]
    photo = upload(second_order, seed=9).json()["photo"]
    second_check = inspect(client, second_order, photo["id"]).json()["check"]
    rejected = client.post(
        f"/api/orders/{second_order['id']}/complete",
        json=complete_body(second_order, second_check["id"], key=key),
    )
    assert rejected.status_code == 409, rejected.text
    assert get_order(client, second_order["id"])["status"] == "ready"


def test_replayed_old_completion_never_restores_new_revision_to_completed(client, inspected):
    order = inspected["order"]
    body = complete_body(order, inspected["check"]["id"])
    route = f"/api/orders/{order['id']}/complete"
    first = client.post(route, json=body)
    assert first.status_code == 200, first.text
    revision = client.post(
        f"/api/orders/{order['id']}/revise",
        json={
            "requirements": {**REQUIREMENTS, "washer": 1},
            "instruction": "New requirements after completion",
            "expected_revision": order["revision"],
        },
    )
    assert revision.status_code == 200, revision.text
    replay = client.post(route, json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["completion"]["id"] == first.json()["completion"]["id"]
    assert replay.json()["completion"]["replayed"] is True
    assert replay.json()["order"]["revision"] == order["revision"] + 1
    assert_not_ready(replay.json()["order"])


def test_cancelled_request_does_not_later_commit_observer_success(client, order, upload, analyzer):
    photo = upload(order).json()["photo"]
    analyzer.release.clear()

    async def cancel_inflight():
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as asynchronous:
            task = asyncio.create_task(asynchronous.post(
                f"/api/orders/{order['id']}/inspect",
                json={"photo_id": photo["id"], "expected_revision": order["revision"]},
            ))
            try:
                assert await asyncio.to_thread(analyzer.started.wait, 5)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                analyzer.release.set()

    asyncio.run(cancel_inflight())
    current = get_order(client, order["id"])
    assert current.get("active_inspection") is None
    assert_not_ready(current)
    # Cancellation releases the reservation; a fresh explicit retry can succeed.
    retried = inspect(client, order, photo["id"])
    assert retried.status_code == 200, retried.text
    assert retried.json()["order"]["status"] == "ready"


def test_restart_recovers_abandoned_inference_without_success(client, order, upload, analyzer):
    from kitguard.app import create_app

    photo = upload(order).json()["photo"]
    store = client.app.state.store
    store.begin_inspection(order["id"], photo["id"], order["revision"])
    assert get_order(client, order["id"])["active_inspection"] is not None
    restarted_app = create_app(data_dir=store.directory, analyzer=analyzer)
    with TestClient(restarted_app) as restarted:
        recovered = get_order(restarted, order["id"])
        assert recovered["active_inspection"] is None
        assert_not_ready(recovered)
        assert any(event["kind"] == "inspection_failed" for event in recovered["events"])


def test_inspection_timeout_releases_reservation_and_late_output_never_commits(
    tmp_path, analyzer, image_bytes
):
    from kitguard.app import create_app

    app = create_app(data_dir=tmp_path / "timeout-data", analyzer=analyzer, inference_timeout=0.05)
    with TestClient(app) as client:
        order = client.post(
            "/api/orders", json={"title": "Timeout test", "requirements": REQUIREMENTS}
        ).json()["order"]
        posted = client.post(
            f"/api/orders/{order['id']}/photos",
            data={"expected_revision": order["revision"]},
            files={"photo": ("fixture.png", image_bytes(), "image/png")},
        )
        assert posted.status_code == 201, posted.text
        analyzer.release.clear()
        try:
            timed_out = inspect(client, order, posted.json()["photo"]["id"])
            assert timed_out.status_code == 504, timed_out.text
            assert analyzer.started.is_set()
            assert not analyzer.finished.is_set(), "Observer should still be running at HTTP timeout"
            current = get_order(client, order["id"])
            assert current["active_inspection"] is None
            assert_not_ready(current)
        finally:
            analyzer.release.set()
            assert analyzer.finished.wait(timeout=2)
        # The worker eventually returns matching counts, but its expired request cannot commit.
        current = get_order(client, order["id"])
        assert current["active_inspection"] is None
        assert current["checks"] == []
        assert_not_ready(current)


def test_revision_proposal_timeout_has_no_state_effect_even_after_late_output(tmp_path, analyzer):
    from kitguard.app import create_app

    app = create_app(data_dir=tmp_path / "proposal-timeout-data", analyzer=analyzer, inference_timeout=0.05)
    with TestClient(app) as client:
        order = client.post(
            "/api/orders", json={"title": "Proposal timeout test", "requirements": REQUIREMENTS}
        ).json()["order"]
        before = get_order(client, order["id"])
        analyzer.proposal = {"requirements": {**REQUIREMENTS, "bolt": 3}, "explanation": "Late proposal"}
        analyzer.proposal_release.clear()
        try:
            response = client.post(
                f"/api/orders/{order['id']}/propose-revision",
                json={"instruction": "bolt 3", "expected_revision": order["revision"]},
            )
            assert response.status_code == 504, response.text
            assert analyzer.proposal_started.is_set()
            assert not analyzer.proposal_finished.is_set()
            assert get_order(client, order["id"]) == before
        finally:
            analyzer.proposal_release.set()
            assert analyzer.proposal_finished.wait(timeout=2)
        assert get_order(client, order["id"]) == before


@pytest.mark.parametrize("failure", ["unavailable", "runtime"])
def test_model_failure_never_creates_success(client, order, upload, analyzer, failure):
    posted = upload(order)
    if failure == "unavailable":
        analyzer.available = False
    else:
        analyzer.error = RuntimeError("TEST model failed to load")
    response = inspect(client, order, posted.json()["photo"]["id"])
    assert response.status_code == 503, response.text
    assert_not_ready(get_order(client, order["id"]))


@pytest.mark.parametrize("bad_observed", [
    {**REQUIREMENTS, "bolt": True},
    {**REQUIREMENTS, "bolt": "2"},
    {**REQUIREMENTS, "bolt": 2.5},
    {**REQUIREMENTS, "bolt": -1},
    {"bolt": 2},
])
def test_malformed_observation_fails_closed(client, order, upload, analyzer, bad_observed):
    posted = upload(order)
    analyzer.result = FakeAnalyzer.observation(bad_observed)
    response = inspect(client, order, posted.json()["photo"]["id"])
    if response.status_code == 200:
        assert response.json()["check"]["decision"] == "manual", response.text
    else:
        assert response.status_code >= 400, response.text
    assert_not_ready(get_order(client, order["id"]))


def test_manual_action_cannot_be_overridden_by_matching_counts(client, order, upload, analyzer):
    posted = upload(order)
    analyzer.result = FakeAnalyzer.observation(REQUIREMENTS, action="manual", issues=["TEST: cannot certify"])
    response = inspect(client, order, posted.json()["photo"]["id"])
    assert response.status_code == 200, response.text
    assert response.json()["check"]["decision"] == "manual", response.text
    assert_not_ready(get_order(client, order["id"]))


def test_uncertain_counts_never_become_add_remove_or_ready(client, order, upload, analyzer):
    analyzer.result = FakeAnalyzer.observation(
        {part: None for part in REQUIREMENTS}, action="recapture", issues=["TEST occlusion"]
    )
    decisions = []
    for seed in range(4):
        posted = upload(order, seed=seed)
        assert posted.status_code == 201, posted.text
        response = inspect(client, order, posted.json()["photo"]["id"])
        assert response.status_code == 200, response.text
        check = response.json()["check"]
        decisions.append(check["decision"])
        assert check["decision"] in ("recapture", "manual"), response.text
        assert check["action"]["kind"] != "add_remove"
    assert decisions[-1] == "manual", decisions
    assert_not_ready(get_order(client, order["id"]))


def test_old_order_photo_cannot_be_used_for_another_order(client, order, upload):
    posted = upload(order)
    other = client.post("/api/orders", json={"title": "Different kit", "requirements": REQUIREMENTS}).json()["order"]
    response = inspect(client, other, posted.json()["photo"]["id"])
    assert response.status_code in (404, 409), response.text
    assert_not_ready(get_order(client, other["id"]))
