import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release_pipeline as pipeline
from test_discover_unraid import entry


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def candidate(self):
        version = "7.4.0-beta.2"
        prefix = f"unraid-{version}-r1--"
        packages = {"kernel": prefix + "ugreen_leds-test.txz",
                    "monitor": prefix + "ugreenleds-driver-test.txz",
                    "i2c_tools": prefix + "i2c-tools-test.txz"}
        names = list(packages.values()) + [prefix + n for n in (
            "stock.config", "config-validation.json", "led-layout.json",
            "compatibility.txt", "userspace-compatibility.txt")]
        for name in names:
            (self.directory / name).write_bytes(b"fixture")
        manifest = {"schema": 1, "recipe": 1, "status": "candidate", "unraid": version,
                    "kernel": "6.18.47-Unraid", "repository_commit": "a" * 40,
                    "packages": packages,
                    "assets": [{"name": n, "size": 7, "sha256": hashlib.sha256(b"fixture").hexdigest()}
                               for n in names]}
        receipt = self.directory / pipeline.receipts_name(version)
        receipt.write_text(json.dumps(manifest))
        return manifest, receipt

    def release(self, draft=False):
        return {"tag_name": "6.18.47-Unraid", "draft": draft,
                "assets": [{"name": p.name} for p in self.directory.iterdir()]}

    def test_complete_receipt_skips_only_that_version(self):
        self.candidate()
        feed = {"os_list": [entry("7.4.0-beta.2"), entry("7.3.3-rc.1")]}
        self.assertEqual([r["version"] for r in pipeline.queue(feed, [self.release()])], ["7.3.3-rc.1"])

    def test_draft_missing_receipt_and_partial_assets_do_not_skip(self):
        manifest, receipt = self.candidate()
        feed = {"os_list": [entry("7.4.0-beta.2")]}
        self.assertEqual(len(pipeline.queue(feed, [self.release(draft=True)])), 1)
        (self.directory / manifest["packages"]["monitor"]).unlink()
        self.assertEqual(len(pipeline.queue(feed, [self.release()])), 1)
        receipt.unlink()
        self.assertEqual(len(pipeline.queue(feed, [self.release()])), 1)

    def test_assets_across_different_kernel_releases_are_not_combined(self):
        self.candidate()
        first, second = self.release(), self.release()
        first["assets"] = first["assets"][:4]
        second["assets"] = second["assets"][4:]
        second["tag_name"] = "6.18.48-Unraid"
        self.assertEqual(len(pipeline.queue({"os_list": [entry("7.4.0-beta.2")]}, [first, second])), 1)

    def test_candidate_hashes_and_package_roles(self):
        manifest, _ = self.candidate()
        self.assertEqual(pipeline.validate_candidate(self.directory)[0], manifest)
        (self.directory / manifest["packages"]["kernel"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            pipeline.validate_candidate(self.directory)

    def test_unsafe_asset_path_rejected(self):
        manifest, receipt = self.candidate()
        manifest["assets"][0]["name"] = "../escape"
        receipt.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            pipeline.validate_candidate(self.directory)

    def test_wrong_package_role_rejected(self):
        manifest, receipt = self.candidate()
        manifest["packages"]["kernel"], manifest["packages"]["monitor"] = (
            manifest["packages"]["monitor"], manifest["packages"]["kernel"])
        receipt.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "identity"):
            pipeline.validate_candidate(self.directory)

    def test_unrecorded_file_rejected(self):
        self.candidate()
        (self.directory / "unexpected").write_text("extra")
        with self.assertRaisesRegex(ValueError, "Unrecorded"):
            pipeline.validate_candidate(self.directory)

    def test_publication_uploads_receipt_last_and_never_clobbers(self):
        _, receipt = self.candidate()
        remote = {"tag_name": "6.18.47-Unraid", "draft": True, "assets": []}
        with patch.object(pipeline, "github_releases", return_value=[remote]), patch.object(pipeline, "run") as run:
            pipeline.publish(self.directory)
        calls = [call.args for call in run.call_args_list]
        uploads = [call for call in calls if call[:3] == ("gh", "release", "upload")]
        self.assertEqual(uploads[-1][4], receipt)
        self.assertTrue(all("--clobber" not in call for call in calls))
        self.assertIn("--prerelease", calls[-1])

    def test_conflicting_remote_bytes_stop_publication(self):
        manifest, _ = self.candidate()
        name = manifest["assets"][0]["name"]
        remote = {"tag_name": "6.18.47-Unraid", "draft": False, "assets": [{"name": name}]}
        def download(*args):
            self.assertEqual(args[:3], ("gh", "release", "download"))
            (Path(args[-1]) / name).write_bytes(b"different")
        with patch.object(pipeline, "github_releases", return_value=[remote]), patch.object(pipeline, "run", side_effect=download):
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                pipeline.publish(self.directory)

    def test_new_release_uses_creation_response_without_relisting(self):
        self.candidate()
        remote = {"tag_name": "6.18.47-Unraid", "draft": True, "assets": []}
        with patch.object(pipeline, "github_releases", return_value=[]) as listing, \
                patch.object(pipeline, "output", return_value=json.dumps(remote)) as create, \
                patch.object(pipeline, "run") as run:
            pipeline.publish(self.directory)
        listing.assert_called_once()
        self.assertIn("tag_name=6.18.47-Unraid", create.call_args.args)
        self.assertIn("draft=true", create.call_args.args)
        self.assertIn("prerelease=true", create.call_args.args)
        self.assertTrue(any(call.args[:3] == ("gh", "release", "upload") for call in run.call_args_list))

    def test_installer_checksums_are_checked_before_build(self):
        archive = self.directory / "installer.zip"
        with zipfile.ZipFile(archive, "w") as z:
            for name in ("bzroot", "bzmodules"):
                z.writestr(name, b"payload")
                z.writestr(name + ".sha256", "0" * 64)
        inputs = self.directory / "inputs"
        inputs.mkdir()
        with self.assertRaisesRegex(ValueError, "payload checksum"):
            pipeline.extract_payloads(archive, inputs)

    def test_numeric_toolchain_versions(self):
        self.assertEqual(pipeline.version_number("150300"), "15.3.0")
        self.assertEqual(pipeline.version_number("24601"), "2.46.1")


if __name__ == "__main__":
    unittest.main()
