"""Compatibility smoke uses synthetic frozen raw responses, never candidate prefix data."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.v08 import replay_reference_workspace_compat as c


def test_metadata_exception_is_top_level_and_preserves_semantic_fields():
    original = {"reference_evidence": {"new": True}, "observed": {"nut": 4},
                "action": {"kind": "recapture", "reference_evidence": "semantic nested value"}}
    expected = copy.deepcopy(original)
    del expected["reference_evidence"]
    assert c.semantic_copy(original) == expected
    assert "reference_evidence" in original


@pytest.mark.parametrize("change_schema", [False, True])
def test_current_workspace_replays_synthetic_frozen_records_and_checks_full_json_schema(tmp_path, change_schema):
    root = str(c.ROOT)
    entry = "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')"
    fixture = c.ROOT / "tests/test_reference_guarded_audit_v08.py"
    first = subprocess.run([sys.executable, "-I", "-c", entry, root, str(fixture), "success", str(tmp_path)],
                           capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    second = subprocess.run([sys.executable, "-I", "-c", entry, root, str(Path(__file__).resolve()),
                             str(tmp_path), "changed" if change_schema else "same"], capture_output=True, text=True, check=False)
    assert second.returncode == 0, second.stdout + second.stderr
    assert json.loads(second.stdout)["model_called"] is False


def worker(directory, changed):
    import PIL
    root = Path(directory)
    frozen = c.a.H.load_frozen_modules(c.ROOT)
    schemas = c.prior_schemas((c.ROOT / c.a.FREEZE_REL).parent / "source_snapshot")
    if changed:
        schemas["SpatialInventory"]["additionalProperties"] = "changed contract"
    model = c.a.read(c.ROOT / c.a.FREEZE_REL)["model"]["status"]["path"]
    engine = c.compatible_engine(frozen, schemas, Path(model))
    refs = {p: root / f"{p}.png" for p in ("nut", "washer")}
    row = c.a.read(root / "fixture_record.json")
    freeze = {"versions": {"pillow": PIL.__version__}, "references": {
        p: {"crop": {"sha256": c.a.sha(path)}, "prepared_sha256": c.a.sha(path), "prepared_size": [40, 36]}
        for p, path in refs.items()}}
    if changed:
        try:
            c.a.replay(engine, root / "normalized.jpg", refs, root / "case", row, frozen)
        except c.a.AuditError as exc:
            assert "JSON schema changed" in str(exc)
        else:
            raise AssertionError("Changed schema accepted")
    else:
        counts, opaque = c.a.replay(engine, root / "normalized.jpg", refs, root / "case", row, frozen)
        assert counts["calls"] == 3 and not opaque
        c.check_metadata(engine.compat_diagnostics["reference_evidence"], freeze, row, engine.status())
    assert not any(n == "mlx" or n.startswith("mlx.") for n in sys.modules)
    print(json.dumps({"model_called": False, "schema_mutation_rejected": changed}))


if __name__ == "__main__":
    worker(sys.argv[1], sys.argv[2] == "changed")
