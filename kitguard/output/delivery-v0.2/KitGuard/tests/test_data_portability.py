"""A backed-up data directory must retain its evidence after relocation."""

import shutil

from kitguard.store import Store


def test_copied_data_keeps_photo_references(tmp_path):
    original = Store(tmp_path / "original")
    order = original.create("engineering backup test", {"bolt": 1, "nut": 0, "washer": 0, "bracket": 0})
    path = original.photos_dir / "engineering.jpg"
    path.write_bytes(b"not a visual-accuracy fixture; file-mapping check only")
    original.add_photo(order["id"], {"id": "testphoto", "revision": 1}, path, expected=1)
    shutil.copytree(original.directory, tmp_path / "restored")
    # Removing the original ensures this test cannot accidentally read the old path.
    shutil.rmtree(original.directory)
    restored = Store(tmp_path / "restored")
    assert restored.photo_path("testphoto").parent == restored.photos_dir
    assert restored.photo_path("testphoto").read_bytes().startswith(b"not a visual-accuracy")
    assert restored.get(order["id"])["photos"][0]["id"] == "testphoto"
