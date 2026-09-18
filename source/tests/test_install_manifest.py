import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


class InstallManifestTests(unittest.TestCase):
    def setUp(self):
        self.target = dict(unraid="7.4.0-beta.2", kernel="6.18.47-Unraid",
                           config_sha256="a" * 64, manifest_sha256="b" * 64,
                           model="DXP6800 Pro")
        prefix = "unraid-7.4.0-beta.2-r1--"
        packages = {"kernel": prefix + "ugreen_leds-test.txz",
                    "monitor": prefix + "ugreenleds-driver-test.txz",
                    "i2c_tools": prefix + "i2c-tools-test.txz"}
        self.manifest = dict(schema=1, recipe=1, status="candidate",
                             unraid=self.target["unraid"], kernel=self.target["kernel"],
                             config_sha256=self.target["config_sha256"], packages=packages,
                             assets=[dict(name=n, sha256="a" * 64, size=123)
                                     for n in [*packages.values(), prefix + "stock.config"]])
        self.approval = dict(schema=1, recipe=1, status="approved",
                             unraid=self.target["unraid"], kernel=self.target["kernel"],
                             manifest_sha256=self.target["manifest_sha256"],
                             system_product_names=[self.target["model"]])

    def evaluate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (("manifest", self.manifest), ("approval", self.approval)):
                (root / name).write_text(json.dumps(value))
            args = ["jq", "-n", "-e", "-r", "--slurpfile", "manifest", str(root / "manifest"),
                    "--slurpfile", "approval", str(root / "approval")]
            for name, value in self.target.items():
                args.extend(["--arg", name, value])
            args.extend(["-f", str(Path(__file__).resolve().parents[1] / "validate-install-manifest.jq")])
            return subprocess.run(args, capture_output=True, text=True)

    def assert_rejected(self):
        result = self.evaluate()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "", "No package may escape a failed admission check")

    def test_exact_approved_target_emits_only_ordered_packages(self):
        result = self.evaluate()
        self.assertEqual(result.returncode, 0, result.stderr)
        names = [line.split("\t")[0] for line in result.stdout.splitlines()]
        self.assertEqual(names, [self.manifest["packages"][r] for r in ("i2c_tools", "kernel", "monitor")])

    def test_target_mismatches_fail_before_any_output(self):
        for key, value in (("unraid", "7.3.2"), ("kernel", "6.18.48-Unraid"),
                           ("config_sha256", "c" * 64), ("manifest_sha256", "d" * 64),
                           ("model", "DXP6800")):
            with self.subTest(key=key):
                original = self.target[key]
                self.target[key] = value
                self.assert_rejected()
                self.target[key] = original

    def test_missing_approval_or_wrong_status_rejected(self):
        for status in (None, "candidate", "revoked"):
            self.approval["status"] = status
            self.assert_rejected()

    def test_unsafe_duplicate_missing_and_wrong_role_assets_rejected(self):
        original = copy.deepcopy(self.manifest)
        for mutation in ("path", "duplicate", "missing", "role", "hash", "size", "config"):
            self.manifest = copy.deepcopy(original)
            if mutation == "path":
                self.manifest["assets"][0]["name"] = "../escape.txz"
            elif mutation == "duplicate":
                self.manifest["assets"].append(self.manifest["assets"][0])
            elif mutation == "missing":
                self.manifest["assets"].pop(0)
            elif mutation == "role":
                self.manifest["packages"]["kernel"] = self.manifest["packages"]["monitor"]
            elif mutation == "hash":
                self.manifest["assets"][0]["sha256"] = "bad"
            elif mutation == "size":
                self.manifest["assets"][0]["size"] = -1
            else:
                self.manifest["assets"].pop()
            with self.subTest(mutation=mutation):
                self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
