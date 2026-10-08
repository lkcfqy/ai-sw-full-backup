"""Operational readiness tests; synthetic fixtures only, never model inference."""

import sqlite3
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kitguard import __version__, readiness
from scripts import preflight


@pytest.fixture
def setup(tmp_path, monkeypatch):
    package, data = tmp_path / "package", tmp_path / "data"
    (package / "static").mkdir(parents=True)
    (package / "__init__.py").write_text(f'__version__ = "{__version__}"\n')
    data.mkdir()
    for name in readiness.REQUIRED_ASSETS:
        (package / "static" / name).write_text("synthetic resource")
    with sqlite3.connect(data / "kitguard.sqlite3") as db:
        db.execute("CREATE TABLE fixture(value)")
        db.execute("INSERT INTO fixture VALUES ('unchanged')")
    health = {"version": __version__, "model": {**readiness.DEFAULT_EXPECTED_IDENTITY,
              "available": True, "loaded": False, "error": None}, "inference": {"busy": False}}
    detector = {"enabled": True, "available": True, "busy": False, "accepting": True,
                "backend": "cpu_subprocess", "checkpoint_sha256": readiness.V1_CHECKPOINT_SHA256,
                "threshold": 0.5}
    monkeypatch.setattr(readiness, "dependency_inventory", lambda names: {
        name: {"present": True, "version": "test-only", "import_verified": False} for name in names})
    return {"package": package, "data_dir": data, "health": health, "detector": detector}


def indexed(report):
    return {item["check"]: item for item in report["checks"]}


def test_main_ready_when_detector_disabled_and_model_not_loaded(setup):
    setup["detector"] = {"enabled": False}
    report = readiness.build_readiness_report(**setup)
    assert report["ready"]
    assert report["scopes"]["detector"] == {"checked": False, "ready": None}
    assert indexed(report)["main_model_loaded"]["state"] == "warn"
    assert report["verification_level"] == "read_only_preflight_without_model_load_or_inference"
    assert "推理" in report["limitations"]["zh"]


@pytest.mark.parametrize("key,value", [("repo_id", "wrong"), ("revision", "changed"),
                                      ("observation_mode", "spatial_inventory"), ("image_max_side", 1024),
                                      ("observer_protocol_sha256", "different")])
def test_runtime_identity_must_match_trusted_freeze(setup, key, value):
    setup["health"]["model"][key] = value
    report = readiness.build_readiness_report(**setup)
    assert not report["ready"]
    assert indexed(report)[f"main_{key}"]["state"] == "fail"


def test_older_server_wrong_mode_busy_and_missing_assets_are_actionable(setup):
    setup["health"]["version"] = "0.5.0"
    setup["health"]["inference"]["busy"] = True
    (setup["package"] / "static" / "region.js").unlink()
    report = readiness.build_readiness_report(**setup)
    checks = indexed(report)
    for name in ("running_application_version", "main_inference_idle", "static_assets"):
        assert checks[name]["passed"] is False
        assert checks[name]["action"]["ko"] and checks[name]["action"]["zh"]
    assert checks["static_assets"]["detail"]["missing"] == ["region.js"]
    with pytest.raises(ValueError, match="mode"):
        readiness.build_readiness_report(**setup, mode="unknown")


def test_server_compares_against_package_on_disk_without_executing_it(setup):
    (setup["package"] / "__init__.py").write_text('__version__ = "next-version"\nraise RuntimeError("never")\n')
    report = readiness.build_readiness_report(**setup)
    assert not report["ready"]
    assert indexed(report)["running_application_version"]["detail"]["expected"] == "next-version"
    (setup["package"] / "__init__.py").unlink()
    assert not readiness.build_readiness_report(**setup)["ready"]


def test_detectors_are_separate_and_v2_cannot_be_default_ready(setup):
    setup["health"]["model"] = {"available": False}
    report = readiness.build_readiness_report(**setup, mode="detector")
    assert report["ready"] and report["scopes"]["main"]["ready"] is None
    assert indexed(report)["detector_model_loaded"]["passed"] is None
    setup["detector"]["checkpoint_sha256"] = "339fe6f656c380e8a6eb7ab5f0afd44e9c02f0014e37b1f40e2ebf52f923bcad"
    assert not readiness.build_readiness_report(**setup, mode="detector")["ready"]


def test_all_mode_preserves_separate_scope_results(setup):
    setup["detector"] = {"enabled": False}
    report = readiness.build_readiness_report(**setup, mode="all")
    assert not report["ready"]
    assert report["scopes"]["main"]["ready"] is True
    assert report["scopes"]["detector"]["ready"] is False


def test_missing_dependency_is_not_hidden_by_model_file_presence(setup, monkeypatch):
    monkeypatch.setattr(readiness, "dependency_inventory", lambda names: {
        name: {"present": name != "mlx_vlm"} for name in names})
    report = readiness.build_readiness_report(**setup)
    assert not report["ready"]
    assert indexed(report)["main_model_files"]["passed"]
    assert not indexed(report)["main_dependencies"]["passed"]


def test_permission_check_and_quick_check_do_not_write_user_records(setup, monkeypatch):
    path = setup["data_dir"] / "kitguard.sqlite3"
    before = path.read_bytes()
    assert readiness.build_readiness_report(**setup)["ready"]
    assert path.read_bytes() == before
    assert list(setup["data_dir"].iterdir()) == [path]
    missing = setup["data_dir"] / "new" / "nested"
    assert readiness.directory_permissions(missing)["write_probe_performed"] is False
    assert not missing.exists()
    monkeypatch.setattr(readiness.os, "access", lambda *_args: False)
    report = readiness.build_readiness_report(**setup)
    assert not indexed(report)["data_directory_permissions"]["passed"]


def test_corrupt_and_missing_database_fail_without_repair(setup):
    path = setup["data_dir"] / "kitguard.sqlite3"
    path.write_bytes(b"not a database")
    result = readiness.build_readiness_report(**setup)
    assert indexed(result)["local_database_integrity"]["passed"] is False
    assert path.read_bytes() == b"not a database"
    path.unlink()
    assert readiness.database_integrity(path) == {"exists": False, "ok": None, "detail": "database_missing"}
    assert not path.exists()


def test_api_snapshots_only_selected_status_providers(setup):
    calls = []

    class Engine:
        def status(self):
            calls.append("main")
            return setup["health"]["model"]

        def observe(self, *_args):
            pytest.fail("Readiness must never infer")

    async def detector():
        calls.append("detector")
        return setup["detector"]

    app = FastAPI()
    app.include_router(readiness.create_readiness_router(
        store=SimpleNamespace(directory=setup["data_dir"], path=setup["data_dir"] / "kitguard.sqlite3"),
        engine=Engine(), inference_gate=SimpleNamespace(status=lambda: {"busy": False}),
        package=setup["package"], detector_status=detector,
    ))
    with TestClient(app) as client:
        assert client.get("/api/readiness?mode=detector").json()["ready"]
        assert calls == ["detector"]
        assert client.get("/api/readiness").json()["ready"]
        assert calls == ["detector", "main"]
        assert client.get("/api/readiness?mode=nope").status_code == 422
        assert calls == ["detector", "main"]


def test_status_provider_failure_yields_a_report(setup):
    def broken():
        raise RuntimeError("private internal message")

    app = FastAPI()
    app.include_router(readiness.create_readiness_router(
        store=SimpleNamespace(directory=setup["data_dir"], path=setup["data_dir"] / "kitguard.sqlite3"),
        engine=SimpleNamespace(status=broken), inference_gate=SimpleNamespace(status=lambda: {"busy": False}),
        package=setup["package"], detector_status=broken,
    ))
    with TestClient(app) as client:
        response = client.get("/api/readiness?mode=all")
        assert response.status_code == 200 and not response.json()["ready"]
        assert "private internal message" not in response.text


def test_api_download_is_timestamped_attachment_for_selected_mode(setup):
    app = FastAPI()
    app.include_router(readiness.create_readiness_router(
        store=SimpleNamespace(directory=setup["data_dir"], path=setup["data_dir"] / "kitguard.sqlite3"),
        engine=SimpleNamespace(status=lambda: setup["health"]["model"]),
        inference_gate=SimpleNamespace(status=lambda: {"busy": False}),
        package=setup["package"], detector_status=setup["detector"],
    ))
    before = (setup["data_dir"] / "kitguard.sqlite3").read_bytes()
    with TestClient(app) as client:
        response = client.get("/api/readiness?mode=detector&download=true")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert response.headers["content-disposition"].startswith('attachment; filename="kitguard-readiness-detector-')
        assert response.headers["content-disposition"].endswith('Z.json"')
        assert response.headers["cache-control"] == "no-store"
        payload = response.json()
        assert payload["schema"] == "kitguard.readiness.v1" and payload["mode"] == "detector"
        assert payload["scopes"]["main"] == {"checked": False, "ready": None}
        assert payload["checked_at"] and payload["ready"]
        assert "content-disposition" not in client.get("/api/readiness").headers
        assert client.get("/api/readiness?mode=invalid&download=true").status_code == 422
    assert (setup["data_dir"] / "kitguard.sqlite3").read_bytes() == before


def test_cli_accepts_server_report_but_rejects_version_mismatch(setup, monkeypatch):
    report = readiness.build_readiness_report(**setup)
    monkeypatch.setattr(preflight, "fetch_json", lambda _url: deepcopy(report))
    assert preflight.collect_report(8765, "main")["ready"]
    report["version"] = "0.5.0"
    result = preflight.collect_report(8765, "main")
    assert not result["ready"]
    assert not result["scopes"]["main"]["ready"]
    assert indexed(result)["client_server_version"]["detail"]["expected"] == __version__


def test_cli_unreachable_or_legacy_endpoint_is_not_ready(setup, monkeypatch):
    def legacy(url):
        if url.endswith("/api/health"):
            return setup["health"]
        raise URLError("offline")

    monkeypatch.setattr(preflight, "fetch_json", legacy)
    result = preflight.collect_report(8765, "main")
    assert not result["ready"]
    assert indexed(result)["readiness_endpoint"]["state"] == "fail"


def test_cli_invalid_remote_report_cannot_pass(monkeypatch):
    monkeypatch.setattr(preflight, "fetch_json", lambda _url: {
        "schema": "kitguard.readiness.v1", "mode": "main", "checks": [], "scopes": {},
        "ready": "true", "version": __version__,
    })
    assert not preflight.collect_report(8765, "main")["ready"]


def test_cli_output_never_overwrites_existing_file_or_symlink(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(preflight, "collect_report", lambda *_args: {"ready": True})
    output = tmp_path / "report.json"
    assert preflight.main(["--mode", "detector", "--port", "8767", "--output", str(output)]) == 0
    original = output.read_bytes()
    with pytest.raises(SystemExit) as exc:
        preflight.main(["--output", str(output)])
    assert exc.value.code == 2 and output.read_bytes() == original
    link = tmp_path / "missing-link.json"
    link.symlink_to(tmp_path / "no-target")
    with pytest.raises(SystemExit):
        preflight.main(["--output", str(link)])
    assert not (tmp_path / "no-target").exists()
    with pytest.raises(SystemExit) as exc:
        preflight.main(["--output", str(output / "impossible.json")])
    assert exc.value.code == 2


def test_required_asset_manifest_covers_current_packaged_files():
    package = Path(readiness.__file__).parent
    files = {p.relative_to(package / "static").as_posix() for p in (package / "static").rglob("*") if p.is_file()}
    assert set(readiness.REQUIRED_ASSETS) == files
