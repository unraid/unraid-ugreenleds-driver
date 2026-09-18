import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_install_manifest


class InstallBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = test_install_manifest.InstallManifestTests()
        self.fixture.setUp()
        self.manifest = self.fixture.manifest
        self.config = self.root / "stock.config"
        self.config.write_bytes(b"stock configuration")
        config_hash = hashlib.sha256(self.config.read_bytes()).hexdigest()
        self.manifest["config_sha256"] = config_hash
        for asset in self.manifest["assets"]:
            path = self.root / asset["name"]
            path.write_bytes(self.config.read_bytes() if path.name.endswith("stock.config") else b"package fixture")
            asset.update(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.receipt = self.root / "unraid-7.4.0-beta.2-r1.json"
        self.receipt.write_text(json.dumps(self.manifest))
        approval = self.fixture.approval
        approval["manifest_sha256"] = hashlib.sha256(self.receipt.read_bytes()).hexdigest()
        self.approval = self.root / ("approved-" + self.receipt.name)
        self.approval.write_text(json.dumps(approval))

    def verify(self):
        return subprocess.run(["bash", str(Path(__file__).resolve().parents[1] / "verify-install-bundle.sh"),
                               str(self.root), "7.4.0-beta.2", "6.18.47-Unraid", str(self.config),
                               "DXP6800 Pro"], capture_output=True, text=True)

    def assert_rejected(self):
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_verified_bytes_emit_three_ordered_packages(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 3)

    def test_last_package_corruption_emits_no_partial_selection(self):
        path = self.root / self.manifest["packages"]["monitor"]
        path.write_bytes(b"PACKAGE FIXTURE")  # Same length, different checksum.
        self.assert_rejected()

    def test_truncated_package_rejected(self):
        (self.root / self.manifest["packages"]["kernel"]).write_bytes(b"short")
        self.assert_rejected()

    def test_symlink_package_rejected(self):
        path = self.root / self.manifest["packages"]["kernel"]
        path.unlink()
        path.symlink_to(self.root / self.manifest["packages"]["monitor"])
        self.assert_rejected()

    def test_missing_approval_rejected(self):
        self.approval.unlink()
        self.assert_rejected()

    def test_receipt_byte_change_invalidates_approval(self):
        self.receipt.write_text(self.receipt.read_text() + "\n")
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
