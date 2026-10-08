"""Metadata-only contracts: no archive opening, image decoding, or preparation."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/v08/prepare_foda_grouped_development.py"
SPEC = importlib.util.spec_from_file_location("foda_prepare", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MetadataContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.meta = self.root / "metadata"
        self.meta.mkdir()
        self.mapping = self.meta / "voc_original_group_mapping.jsonl"
        self.candidates = self.meta / "metadata_candidates.jsonl"
        self.summary = self.meta / "group_recovery_summary.json"
        self.mapping.write_text('{"voc_image_id":"000001"}\n')
        self.candidates.write_text('{"image_id":"000001"}\n')
        self.summary.write_text('{}\n')
        self.groups = self.meta / "groups.json"
        self.refresh_hashes()
        self.addCleanup(patch.stopall)
        patch.object(MODULE, "ROOT", self.root).start()
        patch.object(MODULE, "META", self.meta).start()

    def refresh_hashes(self):
        self.groups.write_text(json.dumps({"source_sha256": {
            str(p.relative_to(self.root)): MODULE.sha(p)
            for p in (self.mapping, self.candidates, self.summary)}}))

    def test_valid_chain_has_no_archive_access(self):
        with patch.object(MODULE.zipfile, "ZipFile", side_effect=AssertionError("image archive accessed")):
            _, mappings, candidates, _, _ = MODULE.verified_metadata(self.groups)
        self.assertEqual(list(mappings), ["000001"])
        self.assertEqual(len(candidates), 1)

    def test_changed_metadata_is_rejected_before_parsing(self):
        self.candidates.write_text('corrupt changed input\n')
        with self.assertRaisesRegex(ValueError, "SHA-256 changed"):
            MODULE.verified_metadata(self.groups)

    def test_duplicate_mapping_ids_cannot_be_silently_overwritten(self):
        self.mapping.write_text('{"voc_image_id":"000001"}\n' * 2)
        self.refresh_hashes()
        with self.assertRaisesRegex(ValueError, "Duplicate mapping IDs"):
            MODULE.verified_metadata(self.groups)

    def test_repeated_prefix_cannot_receive_separate_class_roles(self):
        groups = [{"group_id": f"{category}_{i}", "author_class": category}
                  for category in MODULE.CLASSES for i in range(3)]
        groups[0]["group_id"] = groups[3]["group_id"] = "GOPR_SHARED"
        with self.assertRaisesRegex(ValueError, "cross-class group"):
            MODULE.roles(groups)


if __name__ == "__main__":
    unittest.main()
