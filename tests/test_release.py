"""Exercise release/install boundaries using an isolated synthetic source tree."""

import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
install = importlib.import_module("install")
project_checks = importlib.import_module("project_checks")
release = importlib.import_module("release")


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / "tmp/tests"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.source = self.folder / "source"
        self.source.mkdir()
        for relative in project_checks.inventory():
            destination = self.source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        (self.source / "tmp").mkdir()
        self.artifact = self.source / "tmp/synthetic.xlsx"
        self.artifact.write_bytes(b"synthetic release-gate fixture, not a live workbook")
        fingerprint = project_checks.source_digest(self.source)
        self.offline = {"status": "passed", "testCount": 23, "failures": 0, "errors": 0,
                        "testedAt": "synthetic", "sourceDigest": fingerprint}
        self.live = {"status": "passed", "sourceDigest": fingerprint, "testedAt": "synthetic", "dwsVersion": "synthetic",
                     "file": str(self.artifact), "checks": {"sheetCount": 1, "columns": 3, "dataRows": 1,
                     "formulaValues": 1, "referenceValues": 1, "headerFill": True, "headerBorders": True,
                     "bytesUnchanged": True, "viewDeleted": True, "existingViewsUnchanged": True,
                     "idempotentResume": True, "sha256": hashlib.sha256(self.artifact.read_bytes()).hexdigest()}}
        self.write_evidence()

    def write_evidence(self):
        for name, evidence in (("validation", self.offline), ("live_smoke", self.live)):
            (self.source / "tmp" / f"{name}.json").write_text(json.dumps(evidence), encoding="utf-8")

    def extract(self):
        archive = release.build(self.source)
        package = self.folder / "package"
        with zipfile.ZipFile(archive) as stream:
            stream.extractall(package)
        return archive, package

    def test_missing_live_evidence_blocks_release(self):
        (self.source / "tmp/live_smoke.json").unlink()
        with self.assertRaises(FileNotFoundError):
            release.build(self.source)
        self.assertFalse((self.source / "dist").exists())

    def test_failed_tests_block_release(self):
        self.offline["status"] = "failed"
        self.write_evidence()
        with self.assertRaises(ValueError):
            release.build(self.source)

    def test_source_change_invalidates_previous_tests(self):
        with (self.source / "README.md").open("a", encoding="utf-8") as stream:
            stream.write("\nA maintained document changed.\n")
        with self.assertRaises(ValueError):
            release.build(self.source)

    def test_missing_cleanup_blocks_release(self):
        self.live["checks"]["viewDeleted"] = False
        self.write_evidence()
        with self.assertRaises(ValueError):
            release.build(self.source)

    def test_changed_live_file_blocks_release(self):
        self.artifact.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            release.build(self.source)

    def test_package_excludes_private_config_data_and_evidence(self):
        (self.source / ".env").write_text("PRIVATE_CONFIG=do_not_ship", encoding="utf-8")
        archive, package = self.extract()
        with zipfile.ZipFile(archive) as stream:
            names = stream.namelist()
            self.assertIn("skills/dingtalk-aitable-export/SKILL.md", names)
            self.assertIn(".env.example", names)
            self.assertNotIn(".env", names)
            self.assertFalse(any(name.startswith(("output/", "tmp/", "tests/", "tools/")) for name in names))
            self.assertNotIn(str(self.artifact), stream.read("TEST_REPORT.json").decode())
        self.assertTrue((package / "README.md").is_file())
        self.assertTrue(archive.with_suffix(".zip.sha256").exists())

    def test_released_version_cannot_be_overwritten(self):
        release.build(self.source)
        with self.assertRaises(ValueError):
            release.build(self.source)

    def test_install_checks_bytes_and_refuses_existing_destination(self):
        _, package = self.extract()
        destination = self.folder / "installed"
        self.assertEqual(install.install(package, destination), destination)
        for source in (package / "skills/dingtalk-aitable-export").rglob("*"):
            if source.is_file():
                target = destination / source.relative_to(package / "skills/dingtalk-aitable-export")
                self.assertEqual(source.read_bytes(), target.read_bytes())
        with self.assertRaises(ValueError):
            install.install(package, destination)

    def test_modified_or_added_skill_file_blocks_install(self):
        _, package = self.extract()
        script = package / "skills/dingtalk-aitable-export/scripts/export_table.py"
        original = script.read_bytes()
        script.write_bytes(b"modified")
        with self.assertRaises(ValueError):
            install.install(package, self.folder / "installed")
        script.write_bytes(original)
        (script.parent / "unexpected.py").write_text("print('unexpected')", encoding="utf-8")
        with self.assertRaises(ValueError):
            install.install(package, self.folder / "installed")

    def test_manifest_path_escape_is_rejected(self):
        _, package = self.extract()
        manifest_path = package / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"]["../outside"] = "irrelevant"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            install.install(package, self.folder / "installed")


if __name__ == "__main__":
    unittest.main()
