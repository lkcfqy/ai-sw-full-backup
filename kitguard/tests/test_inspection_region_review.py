"""Independent region/lineage counterexamples; synthetic fixtures, never model accuracy."""

import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
from zipfile import ZipFile

import pytest
from conftest import REQUIREMENTS, FakeAnalyzer
from PIL import Image


class ContextObserver(FakeAnalyzer):
    def __init__(self):
        super().__init__()
        self.contexts = []

    def observe_with_context(self, image_path, requirements, references, context):
        self.contexts.append(deepcopy(context))
        return self.observe(image_path, requirements, references)


@pytest.fixture
def analyzer():
    return ContextObserver()


def current(client, order):
    return client.app.state.store.get(order["id"])


def new_order(client):
    response = client.post("/api/orders", json={"title": "Independent region fixture", "requirements": REQUIREMENTS})
    assert response.status_code == 201, response.text[:500]
    return response.json()["order"]


def region_payload(order, *, rect=(10, 20, 210, 220), root=None):
    photo = order["photos"][-1]
    return {
        "expected_revision": order["revision"], "expected_photo_id": photo["id"],
        "expected_evidence_epoch": order["evidence_epoch"],
        "root_photo_id": root or photo.get("root_photo_id", photo["id"]),
        "mode": "whole_image" if rect is None else "region",
        "region_xyxy": list(rect) if rect is not None else None,
        "confirmed_all_items_inside": True,
    }


def post_region(client, order, *, rect=(10, 20, 210, 220), root=None, body=None):
    return client.post(f"/api/orders/{order['id']}/inspection-region",
                       json=body if body is not None else region_payload(current(client, order), rect=rect, root=root))


def select(client, order, **kwargs):
    response = post_region(client, order, **kwargs)
    assert response.status_code == 200, response.text[:500]
    return response.json()


def inspect(client, order):
    saved = current(client, order)
    return client.post(f"/api/orders/{order['id']}/inspect", json={
        "photo_id": saved["photos"][-1]["id"], "expected_revision": saved["revision"],
    })


def study(client, *, source="engineering_fixture", planned=1):
    response = client.post("/api/studies", json={
        "title": "Region audit engineering fixture", "source_kind": source,
        "planned_cases": planned, "participant_code": "region_review", "note": "Synthetic only",
    })
    assert response.status_code == 201, response.text[:500]
    return response.json()["study"]


def register(client, record, order):
    saved = current(client, order)
    return client.post(f"/api/studies/{record['id']}/cases", json={
        "label": "Fixed synthetic region", "order_id": saved["id"],
        "expected_revision": saved["revision"], "photo_id": saved["photos"][-1]["id"],
        "truth": REQUIREMENTS, "truth_repeat": REQUIREMENTS, "confirmed_independent": True,
        "source_note": "Synthetic geometry only, no physical study",
    })


@pytest.mark.parametrize("rect", [
    [True, 0, 200, 200], [0.0, 0, 200, 200], ["0", 0, 200, 200],
    [0, 0, 2**100, 200], [-1, 0, 200, 200], [0, 0, 641, 200],
    [0, 0, 200, 481], [200, 0, 200, 200], [0, 0, 31, 200],
    [0, 0, 200, 31], [0, 0, 200], [0, 0, 200, 200, 0],
])
def test_region_rejects_unsafe_integer_geometry_without_mutation(client, order, upload, rect):
    upload(order)
    before = current(client, order)
    files = set(client.app.state.store.photos_dir.iterdir())
    response = post_region(client, order, rect=rect)
    assert response.status_code == 422, response.text[:500]
    assert current(client, order) == before
    assert set(client.app.state.store.photos_dir.iterdir()) == files


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_geometry_is_rejected_not_a_server_error(client, order, upload, token):
    upload(order)
    before = current(client, order)
    raw = json.dumps(region_payload(before)).replace('"region_xyxy": [10,', f'"region_xyxy": [{token},')
    response = client.post(f"/api/orders/{order['id']}/inspection-region", content=raw,
                           headers={"Content-Type": "application/json"})
    assert response.status_code in {400, 422}, response.text[:500]
    assert current(client, order) == before


@pytest.mark.parametrize("field,value", [
    ("expected_revision", True), ("expected_evidence_epoch", False),
    ("confirmed_all_items_inside", 1), ("confirmed_all_items_inside", "true"),
    ("confirmed_all_items_inside", False),
])
def test_tokens_and_scope_confirmation_are_strict(client, order, upload, field, value):
    upload(order)
    payload = region_payload(current(client, order))
    payload[field] = value
    response = post_region(client, order, body=payload)
    assert response.status_code == 422, response.text[:500]


@pytest.mark.parametrize("source", ["other_order", "reference", "previous_root"])
def test_current_photo_cannot_borrow_an_unrelated_root(client, order, upload, image_bytes, source):
    first = upload(order).json()["photo"]
    if source == "other_order":
        unrelated = upload(new_order(client), seed=8).json()["photo"]
    elif source == "reference":
        response = client.post(f"/api/orders/{order['id']}/references/nut",
                               files={"photo": ("reference.png", image_bytes(3), "image/png")})
        assert response.status_code == 201, response.text[:500]
        unrelated = response.json()["photo"]
    else:
        unrelated = first
        upload(order, seed=4)
    before = current(client, order)
    response = post_region(client, order, root=unrelated["id"])
    assert response.status_code == 409, response.text[:500]
    assert current(client, order) == before


@pytest.mark.parametrize("field", ["expected_revision", "expected_photo_id", "expected_evidence_epoch"])
def test_current_concurrency_tokens_are_required_even_for_identical_region(client, order, upload, field):
    upload(order)
    selected = select(client, order)
    payload = region_payload(selected["order"])
    payload[field] = "img_stale" if field == "expected_photo_id" else payload[field] + 1
    response = post_region(client, order, body=payload)
    assert response.status_code == 409, response.text[:500]


def test_crop_cannot_refresh_a_photo_from_an_old_order_revision(client, order, upload):
    upload(order)
    response = client.post(f"/api/orders/{order['id']}/revise", json={
        "expected_revision": order["revision"], "requirements": {**REQUIREMENTS, "bolt": 1},
        "instruction": "Synthetic new revision",
    })
    assert response.status_code == 200, response.text[:500]
    assert post_region(client, order).status_code == 409


def test_idempotent_selection_and_whole_restore_preserve_the_original_bytes(client, order, upload):
    root = upload(order).json()["photo"]
    store = client.app.state.store
    raw = store.photo_path(root["id"]).read_bytes()
    first = select(client, order)
    second = select(client, order)
    assert second["changed"] is False
    assert second["order"] == first["order"]
    other = select(client, order, rect=(40, 50, 340, 350))
    view = other["photo"]
    assert view["root_photo_id"] == root["id"]
    assert view["source_family_sha256"] == hashlib.sha256(raw).hexdigest()
    with Image.open(io.BytesIO(raw)) as image:
        expected = io.BytesIO()
        image.convert("RGB").crop((40, 50, 340, 350)).save(expected, format="JPEG", quality=95)
    assert store.photo_path(view["id"]).read_bytes() == expected.getvalue()
    restored = select(client, order, rect=None)
    assert store.photo_path(restored["photo"]["id"]).read_bytes() == raw
    assert restored["photo"]["source_family_sha256"] == root["sha256"]
    events = current(client, order)["events"]
    assert sum(e["kind"] == "photo_uploaded" for e in events) == 1
    assert sum(e["kind"] == "inspection_region_selected" for e in events) == 3


def test_selecting_region_invalidates_a_previously_ready_completion(client, order, upload):
    upload(order)
    checked = inspect(client, order)
    assert checked.status_code == 200, checked.text
    old_check = checked.json()["check"]
    select(client, order)
    response = client.post(f"/api/orders/{order['id']}/complete", json={
        "expected_revision": order["revision"], "check_id": old_check["id"],
        "confirmed": True, "idempotency_key": "region-old-ready-review",
    })
    assert response.status_code == 409, response.text[:500]
    assert current(client, order)["completions"] == []


def test_region_change_is_rejected_while_inference_is_active(client, order, upload, analyzer):
    upload(order)
    analyzer.release.clear()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(inspect, client, order)
        try:
            assert analyzer.started.wait(timeout=3)
            response = post_region(client, order)
            assert response.status_code == 409, response.text[:500]
        finally:
            analyzer.release.set()
        assert pending.result(timeout=5).status_code == 200
    assert len(current(client, order)["photos"]) == 1


@pytest.mark.parametrize("tampered", ["root", "view"])
def test_tampered_region_or_root_blocks_inspection_and_every_archive(client, order, upload, tampered):
    root = upload(order).json()["photo"]
    view = select(client, order)["photo"]
    record = study(client)
    response = register(client, record, order)
    assert response.status_code == 201, response.text[:500]
    closed = client.post(f"/api/studies/{record['id']}/close", json={"confirmed": True})
    assert closed.status_code == 200, closed.text
    target = root if tampered == "root" else view
    client.app.state.store.photo_path(target["id"]).write_bytes(b"intentionally changed synthetic bytes")
    for result in (inspect(client, order), client.get(f"/api/orders/{order['id']}/evidence.zip"),
                   client.get(f"/api/studies/{record['id']}/evidence.zip")):
        assert result.status_code == 409, result.text[:500]


def test_changing_root_during_observation_prevents_committing_a_check(client, order, upload, analyzer):
    root = upload(order).json()["photo"]
    select(client, order)
    analyzer.release.clear()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(inspect, client, order)
        try:
            assert analyzer.started.wait(timeout=3)
            client.app.state.store.photo_path(root["id"]).write_bytes(b"changed root during inspection")
        finally:
            analyzer.release.set()
        response = pending.result(timeout=5)
    assert response.status_code == 409, response.text[:500]
    assert not current(client, order)["checks"]


def test_same_root_views_cannot_manufacture_new_evidence_or_feedback(client, order, upload, analyzer):
    upload(order)
    analyzer.result = analyzer.observation({**REQUIREMENTS, "washer": None}, action="recapture")
    for rect in (None, (10, 20, 210, 220), (40, 50, 340, 350), None):
        if rect is not None or current(client, order)["photos"][-1].get("kind") == "inspection_region_view":
            select(client, order, rect=rect)
        response = inspect(client, order)
        assert response.status_code == 200, response.text[:500]
        check = response.json()["check"]
        assert check["decision"] == "recapture"
        assert check["observation_context"] is None
        feedback = check["evidence_feedback"]
        if feedback is not None:
            assert feedback["outcome"] == "inspection_scope_changed"
            assert feedback["new_physical_evidence"] is False
            assert feedback["physical_action_verified"] is False
            assert feedback["observed_changes"] == feedback["resolved_uncertainties"] == []
    assert analyzer.contexts == []
    for seed, expected in ((7, "recapture"), (8, "manual")):
        upload(order, seed=seed)
        response = inspect(client, order)
        assert response.status_code == 200, response.text[:500]
        assert response.json()["check"]["decision"] == expected


@pytest.mark.parametrize("frozen", [False, True])
def test_registered_case_locks_scope_until_the_study_closes(client, order, upload, frozen):
    upload(order)
    original = select(client, order)["photo"]
    record = study(client)
    registered = register(client, record, order)
    assert registered.status_code == 201, registered.text
    if frozen:
        response = client.post(f"/api/studies/{record['id']}/freeze", json={"confirmed": True})
        assert response.status_code == 200, response.text[:500]
    assert post_region(client, order, rect=(40, 50, 340, 350)).status_code == 409
    response = client.post(f"/api/studies/{record['id']}/close", json={"confirmed": True})
    assert response.status_code == 200, response.text[:500]
    assert post_region(client, order, rect=(40, 50, 340, 350)).status_code == 200
    archived = client.get(f"/api/studies/{record['id']}/evidence.zip")
    assert archived.status_code == 200, archived.text
    with ZipFile(io.BytesIO(archived.content)) as archive:
        assert client.app.state.store.photo_path(original["id"]).read_bytes() in [
            archive.read(name) for name in archive.namelist() if name.endswith(".jpg")
        ]


def test_exposed_crop_prevents_cross_order_whole_photo_claim_of_first_exposure(client, order, upload):
    upload(order)
    select(client, order)
    assert inspect(client, order).status_code == 200
    other = new_order(client)
    upload(other)  # Exact same normalized root, independently created order ID.
    record = study(client, source="self_reported_physical")
    response = register(client, record, other)
    assert response.status_code == 409, response.text[:500]


def test_known_root_jpeg_reupload_cannot_launder_an_observed_crop_as_unseen(client, order, upload):
    root = upload(order).json()["photo"]
    root_bytes = client.app.state.store.photo_path(root["id"]).read_bytes()
    select(client, order)
    assert inspect(client, order).status_code == 200
    other = new_order(client)
    posted = upload(other, payload=root_bytes, name="known-root.jpg", mime="image/jpeg")
    assert posted.status_code == 201, posted.text
    assert posted.json()["photo"]["source_sha256"] == root["sha256"]
    record = study(client, source="self_reported_physical")
    response = register(client, record, other)
    assert response.status_code == 409, response.text[:500]


def test_root_integrity_is_rechecked_at_operator_completion(client, order, upload):
    root = upload(order).json()["photo"]
    select(client, order)
    checked = inspect(client, order)
    assert checked.status_code == 200, checked.text
    client.app.state.store.photo_path(root["id"]).write_bytes(b"changed after successful observation")
    response = client.post(f"/api/orders/{order['id']}/complete", json={
        "expected_revision": order["revision"], "check_id": checked.json()["check"]["id"],
        "confirmed": True, "idempotency_key": "region-root-integrity-review",
    })
    assert response.status_code == 409, response.text[:500]
    assert current(client, order)["completions"] == []


@pytest.mark.parametrize("lineage", ["self_cycle", "root_points_to_view", "view_points_to_view"])
def test_corrupted_recursive_lineage_is_rejected_without_recursion_or_wrong_export(
    client, order, upload, lineage
):
    root = upload(order).json()["photo"]
    first = select(client, order)["photo"]
    second = select(client, order, rect=(40, 50, 340, 350))["photo"]
    store = client.app.state.store
    with store.transaction(order["id"]) as (_, saved):
        photos = {p["id"]: p for p in saved["photos"]}
        if lineage == "self_cycle":
            photos[second["id"]]["root_photo_id"] = second["id"]
        elif lineage == "root_points_to_view":
            photos[root["id"]]["root_photo_id"] = second["id"]
        else:
            photos[second["id"]]["root_photo_id"] = first["id"]
    for result in (post_region(client, order), inspect(client, order),
                   client.get(f"/api/orders/{order['id']}/evidence.zip")):
        assert result.status_code == 409, result.text[:500]


def test_field_registration_and_region_write_share_one_serialized_binding(client, order, upload, monkeypatch):
    upload(order)
    select(client, order)
    record = study(client)
    studies = client.app.state.studies
    original = studies.binding
    captured = Event()
    release = Event()
    scope_returned = Event()
    saved = current(client, order)
    registration = {
        "label": "Fixed synthetic region", "order_id": saved["id"],
        "expected_revision": saved["revision"], "photo_id": saved["photos"][-1]["id"],
        "truth": REQUIREMENTS, "truth_repeat": REQUIREMENTS, "confirmed_independent": True,
        "source_note": "Synthetic concurrency fixture only",
    }

    def paused_binding(db, saved_order):
        binding = original(db, saved_order)
        captured.set()
        assert release.wait(timeout=5), "Independent registration race fixture not released"
        return binding

    monkeypatch.setattr(studies, "binding", paused_binding)

    def change_scope():
        result = post_region(client, order, rect=(40, 50, 340, 350))
        scope_returned.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        registering = pool.submit(studies.add_case, record["id"], registration)
        try:
            assert captured.wait(timeout=3)
            changing = pool.submit(change_scope)
            assert not scope_returned.wait(timeout=0.15), "Region mutation escaped the registration transaction"
        finally:
            release.set()
        registered = registering.result(timeout=5)
        assert len(registered["cases"]) == 1
        response = changing.result(timeout=5)
        assert response.status_code == 409, response.text[:500]


def test_two_crops_of_same_root_cannot_expand_study_sample_size(client, order, upload):
    upload(order)
    select(client, order)
    other = new_order(client)
    upload(other)
    select(client, other, rect=(40, 50, 340, 350))
    record = study(client, planned=2)
    first = register(client, record, order)
    assert first.status_code == 201, first.text
    second = register(client, record, other)
    assert second.status_code == 409, second.text


@pytest.mark.parametrize("field,value", [
    ("region_xyxy", [20, 30, 220, 230]), ("width", 201),
    ("coordinate_space", "client_original_pixels"), ("derivation", "unknown_encoder_v9"),
])
def test_valid_hashes_do_not_excuse_forged_derived_geometry(client, order, upload, field, value):
    upload(order)
    select(client, order)
    store = client.app.state.store
    with store.transaction(order["id"]) as (_, saved):
        saved["photos"][-1][field] = value
    for result in (inspect(client, order), client.get(f"/api/orders/{order['id']}/evidence.zip")):
        assert result.status_code == 409, result.text[:300]


def test_failed_derivation_commit_removes_new_files_and_preserves_the_order(client, order, upload, monkeypatch):
    from kitguard import regions

    root = upload(order).json()["photo"]
    store = client.app.state.store
    before = current(client, order)
    files = set(store.photos_dir.iterdir())
    derive = regions.derive_photo

    def replace_root_after_derivation(*args, **kwargs):
        result = derive(*args, **kwargs)
        store.photo_path(root["id"]).write_bytes(b"root changed before view commit")
        return result

    monkeypatch.setattr(regions, "derive_photo", replace_root_after_derivation)
    result = post_region(client, order)
    assert result.status_code == 409, result.text[:300]
    assert current(client, order) == before
    assert set(store.photos_dir.iterdir()) == files


def test_concurrent_stale_tabs_commit_only_one_scope(client, order, upload):
    upload(order)
    saved = current(client, order)
    bodies = [region_payload(saved, rect=rect) for rect in ((10, 20, 210, 220), (40, 50, 340, 350))]
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(post_region, client, order, body=body) for body in bodies]
        results = [future.result(timeout=5) for future in pending]
    assert sorted(r.status_code for r in results) == [200, 409]
    after = current(client, order)
    assert len(after["photos"]) == 2
    assert after["evidence_epoch"] == saved["evidence_epoch"] + 1
    assert len(list(client.app.state.store.photos_dir.iterdir())) == 2


def test_order_and_closed_study_archives_bind_both_root_and_model_view(client, order, upload):
    root = upload(order).json()["photo"]
    selected = select(client, order)
    view = selected["photo"]
    store = client.app.state.store
    expected_bytes = {p["sha256"]: store.photo_path(p["id"]).read_bytes() for p in (root, view)}
    record = study(client)
    registered = register(client, record, order)
    assert registered.status_code == 201, registered.text[:300]
    case = registered.json()["study"]["cases"][0]
    scope = case["inspection_scope"]
    assert scope["root_photo_id"] == root["id"]
    assert scope["root_photo_sha256"] == root["sha256"]
    assert scope["view_photo_id"] == view["id"]
    assert scope["view_sha256"] == view["sha256"]
    assert scope["region_xyxy"] == [10, 20, 210, 220]
    closed = client.post(f"/api/studies/{record['id']}/close", json={"confirmed": True})
    assert closed.status_code == 200, closed.text[:300]
    for endpoint in (f"/api/orders/{order['id']}/evidence.zip", f"/api/studies/{record['id']}/evidence.zip"):
        response = client.get(endpoint)
        assert response.status_code == 200, response.text[:300]
        with ZipFile(io.BytesIO(response.content)) as archive:
            images = {hashlib.sha256(raw).hexdigest(): raw for name in archive.namelist()
                      if name.endswith(".jpg") for raw in (archive.read(name),)}
            assert expected_bytes.items() <= images.items()
            if "STUDY.json" in archive.namelist():
                archived = json.loads(archive.read("STUDY.json"))["study"]["cases"][0]
                assert archived["inspection_scope"] == scope
                bindings = json.loads(archive.read("MANIFEST.json"))["photo_bindings"]
                assert set(expected_bytes) <= {b["sha256"] for b in bindings}
            else:
                photos = json.loads(archive.read("evidence.json"))["photos"]
                assert set(expected_bytes) <= {p["sha256"] for p in photos}


def test_known_root_reupload_still_inherits_public_origin_restriction(client, order, upload):
    root = upload(order).json()["photo"]
    store = client.app.state.store
    with store.transaction(order["id"]) as (_, saved):
        saved["demo_source"] = {"kind": "public_photo_demo", "physical_completion_allowed": False,
                                "source": "Synthetic metadata fixture, not an actual public photograph"}
    view = select(client, order)["photo"]
    assert view["demo_source"]["kind"] == "public_photo_demo"
    other = new_order(client)
    raw = store.photo_path(root["id"]).read_bytes()
    posted = upload(other, payload=raw, name="root.jpg", mime="image/jpeg")
    assert posted.status_code == 201, posted.text[:300]
    record = study(client, source="self_reported_physical")
    result = register(client, record, other)
    assert result.status_code == 409, result.text[:300]


@pytest.mark.parametrize("change", ["different_rectangle", "whole_image_claim"])
def test_closed_study_archive_checks_frozen_geometry_against_its_exact_bytes(client, order, upload, change):
    upload(order)
    select(client, order)
    record = study(client)
    registered = register(client, record, order)
    assert registered.status_code == 201, registered.text[:300]
    closed = client.post(f"/api/studies/{record['id']}/close", json={"confirmed": True})
    assert closed.status_code == 200, closed.text[:300]
    # Simulate internally inconsistent stored scope without replacing either file or its valid SHA.
    with client.app.state.studies.transaction(record["id"]) as (_, saved):
        scope = saved["cases"][0]["inspection_scope"]
        if change == "different_rectangle":
            scope["region_xyxy"] = [20, 30, 220, 230]
        else:
            scope["mode"] = "whole_image"
            scope["region_xyxy"] = None
            scope["derivation"] = "normalized_root_bytes_v1"
    response = client.get(f"/api/studies/{record['id']}/evidence.zip")
    assert response.status_code == 409, response.text[:100]
