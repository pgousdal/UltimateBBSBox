import hashlib
import http.server
import json
import pathlib
import sys
import tempfile
import threading
import unittest
from argparse import Namespace

import jsonschema

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ubb_archive as archive  # noqa: E402


class MutableHandler(http.server.BaseHTTPRequestHandler):
    payload = b"network artifact"
    interrupt = False

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Disposition", 'attachment; filename="../unsafe.zip"')
        if self.interrupt:
            self.send_header("Content-Length", str(len(self.payload) + 100))
        else:
            self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload[:4] if self.interrupt else self.payload)
        if self.interrupt:
            self.close_connection = True

    def log_message(self, *_args):
        pass


def ingest_args(root, artifact_id, path, **changes):
    values = dict(root=str(root), artifact_id=artifact_id, file=str(path), source_url="https://example.invalid/download",
                  source_name="test archive", original_filename=None, expected_sha256=None, expected_sha1=None,
                  expected_md5=None, max_bytes=1024 * 1024, rights_status="unknown", install_locally=False,
                  redistribute_original=False, publish_to_bbs_filebase=False, no_owner_export=False,
                  rights_evidence=[], software_family=None, version=None, platform=None, notes="Test description")
    values.update(changes)
    return Namespace(**values)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)
        self.root = self.base / "archive"
        archive.init_archive(self.root)
        self.input = self.base / "sample.bin"
        self.input.write_bytes(b"preserved bytes")

    def tearDown(self):
        self.temp.cleanup()

    def import_one(self, artifact_id="sample", **changes):
        return archive.import_artifact(ingest_args(self.root, artifact_id, self.input, **changes))

    def test_init_and_local_import_hashes_metadata_schema(self):
        self.assertTrue((self.root / "state/archive-v1.json").is_file())
        value = self.import_one()
        data = self.input.read_bytes()
        self.assertEqual(value["artifact"]["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(value["artifact"]["sha1"], hashlib.sha1(data).hexdigest())
        self.assertEqual(value["artifact"]["md5"], hashlib.md5(data).hexdigest())
        self.assertEqual(value, archive.load_metadata(self.root, "sample"))
        schema = json.loads((ROOT / "schemas/artifact-v1.schema.json").read_text())
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(value)

    def test_dedup_duplicate_id_changed_source_and_immutability(self):
        first = self.import_one("first")
        obj = archive.object_path(self.root, first["artifact"]["sha256"])
        inode = obj.stat().st_ino
        second = self.import_one("second")
        self.assertEqual(inode, archive.object_path(self.root, second["artifact"]["sha256"]).stat().st_ino)
        self.assertEqual(stat_mode(obj), 0o444)
        with self.assertRaises(archive.DuplicateArtifact):
            self.import_one("first")
        self.input.write_bytes(b"changed bytes")
        changed = self.import_one("changed")
        self.assertNotEqual(first["artifact"]["sha256"], changed["artifact"]["sha256"])
        self.assertEqual(obj.read_bytes(), b"preserved bytes")
        self.assertTrue(changed["provenance"]["source_changed"])
        self.assertIn("first", changed["provenance"]["previous_artifacts_from_source"])

    def test_expected_checksums_and_quarantine_cleanup(self):
        digest = hashlib.sha256(self.input.read_bytes()).hexdigest()
        self.import_one("pass", expected_sha256=digest)
        with self.assertRaises(archive.ArchiveError):
            self.import_one("fail", expected_sha256="0" * 64)
        self.assertEqual(list((self.root / "quarantine").iterdir()), [])
        self.assertFalse((self.root / "metadata/fail.json").exists())

    def test_derive_lineage_does_not_mutate_parent(self):
        parent = self.import_one("parent")
        derived_file = self.base / "converted.adf"; derived_file.write_bytes(b"converted")
        args = ingest_args(self.root, "child", derived_file)
        args.parent = ["parent"]; args.role = "derived_install_media"; args.action = "converted DMS to ADF"; args.tool = "example 1.0"
        child = archive.derive(args)
        self.assertEqual(child["preservation"]["class"], "derived")
        self.assertEqual(child["preservation"]["lineage"]["parents"][0]["sha256"], parent["artifact"]["sha256"])
        self.assertEqual(archive.object_path(self.root, parent["artifact"]["sha256"]).read_bytes(), b"preserved bytes")

    def test_verify_detects_tampering_and_missing(self):
        value = self.import_one()
        obj = archive.object_path(self.root, value["artifact"]["sha256"])
        obj.chmod(0o644); obj.write_bytes(b"tampered")
        with self.assertRaises(archive.VerificationError):
            archive.verify_one(self.root, "sample")
        obj.unlink()
        with self.assertRaises(archive.VerificationError):
            archive.verify_one(self.root, "sample")

    def test_export_and_rights_gated_publication(self):
        self.import_one("denied")
        bundle = archive.build_export(self.root, "denied", self.base / "exports", False)
        for item in ("artifacts/sample.bin", "metadata.json", "checksums.sha256", "RIGHTS.txt", "README.txt"):
            self.assertTrue((bundle / item).exists(), item)
        with self.assertRaises(archive.ArchiveError):
            archive.build_export(self.root, "denied", self.base / "publication", True)
        allowed = self.import_one("allowed", publish_to_bbs_filebase=True)
        staged = archive.build_export(self.root, "allowed", self.base / "publication", True)
        self.assertEqual((staged / "sample.bin").read_bytes(), self.input.read_bytes())
        self.assertTrue((staged / "sample.bin.json").exists())
        self.assertTrue((staged / "FILE_ID.DIZ.generated").exists())
        self.assertEqual(allowed["artifact"]["sha256"], hashlib.sha256((staged / "sample.bin").read_bytes()).hexdigest())

    def test_redistribution_export_denied_by_default(self):
        self.import_one()
        with self.assertRaises(archive.ArchiveError):
            archive.build_export(self.root, "sample", self.base / "exports", False, True)

    def test_path_traversal_url_and_symlink_rejected(self):
        for bad in ("../escape", "UPPER", "/absolute"):
            with self.assertRaises(archive.ArchiveError):
                archive.validate_id(bad)
        with self.assertRaises(archive.ArchiveError):
            archive.sanitized_url("file:///etc/passwd")
        _request, clean = archive.sanitized_url("https://user:secret@example.invalid/file#fragment")
        self.assertEqual(clean, "https://example.invalid/file")
        sanitized = self.import_one("sanitized", source_url="https://user:secret@example.invalid/file#fragment")
        self.assertEqual(sanitized["provenance"]["source_url"], "https://example.invalid/file")
        self.assertNotIn("secret", json.dumps(sanitized))
        link = self.base / "link"; link.symlink_to(self.input)
        with self.assertRaises(archive.ArchiveError):
            archive.import_artifact(ingest_args(self.root, "link", link))

    def test_invalid_metadata_is_rejected(self):
        self.import_one()
        metadata = self.root / "metadata/sample.json"
        value = json.loads(metadata.read_text())
        value["rights"]["publish_to_bbs_filebase"] = "yes"
        metadata.write_text(json.dumps(value))
        with self.assertRaises(archive.ArchiveError):
            archive.load_metadata(self.root, "sample")


class HttpAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = pathlib.Path(self.temp.name); self.root = self.base / "archive"
        archive.init_archive(self.root)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MutableHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        MutableHandler.payload = b"network artifact"; MutableHandler.interrupt = False
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def args(self, artifact_id):
        dummy = self.base / "unused"
        args = ingest_args(self.root, artifact_id, dummy, source_url=f"http://127.0.0.1:{self.server.server_port}/download")
        args.timeout = 2
        return args

    def test_http_acquisition_quarantine_filename_and_changed_bytes(self):
        first = archive.acquire_http(self.args("net-one"))
        self.assertEqual(first["artifact"]["original_filename"], "unsafe.zip")
        MutableHandler.payload = b"new network bytes"
        second = archive.acquire_http(self.args("net-two"))
        self.assertTrue(second["provenance"]["source_changed"])
        self.assertNotEqual(first["artifact"]["sha256"], second["artifact"]["sha256"])

    def test_interrupted_download_has_no_valid_artifact(self):
        MutableHandler.interrupt = True
        with self.assertRaises(archive.ArchiveError):
            archive.acquire_http(self.args("partial"))
        self.assertFalse((self.root / "metadata/partial.json").exists())
        self.assertEqual(list((self.root / "quarantine").iterdir()), [])


def stat_mode(path):
    return path.stat().st_mode & 0o777


if __name__ == "__main__":
    unittest.main()
