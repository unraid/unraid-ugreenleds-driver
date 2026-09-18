import copy
import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from promote_candidate import CHECKS, validate_report
import promote_candidate as promotion


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"unraid": "7.4.0-beta.2", "kernel": "6.18.47-Unraid"}
        self.report = {**self.manifest, "manifest_sha256": "a" * 64,
                       "confirm_hardware_tested": True,
                       "evidence_url": "https://github.com/unraid/unraid-ugreenleds-driver/issues/123",
                       "results": [{"system_product_name": "DXP6800 Pro",
                                    "checks": {key: "pass" for key in CHECKS}}]}

    def test_complete_attestation_selects_exact_model(self):
        self.assertEqual(validate_report(self.report, self.manifest, "a" * 64), ["DXP6800 Pro"])

    def test_each_failed_or_absent_check_prohibits_approval(self):
        for key in CHECKS:
            for value in ("fail", "untested", None):
                report = copy.deepcopy(self.report)
                report["results"][0]["checks"][key] = value
                with self.subTest(check=key, value=value), self.assertRaises(ValueError):
                    validate_report(report, self.manifest, "a" * 64)

    def test_confirmation_and_identity_are_required(self):
        for key, value in (("confirm_hardware_tested", False), ("manifest_sha256", "b" * 64),
                           ("unraid", "7.3.2"), ("kernel", "6.18.48-Unraid"), ("results", []),
                           ("evidence_url", "https://example.com/report")):
            report = copy.deepcopy(self.report)
            report[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_report(report, self.manifest, "a" * 64)

    def test_static_model_does_not_claim_activity_tests(self):
        model = self.report["results"][0]
        model["system_product_name"] = "DXP480T Plus"
        with self.assertRaises(ValueError):
            validate_report(self.report, self.manifest, "a" * 64)
        model["static_leds"] = "pass"
        model["checks"]["disk_leds"] = model["checks"]["network_leds"] = "not-applicable-static-model"
        self.assertEqual(validate_report(self.report, self.manifest, "a" * 64), ["DXP480T Plus"])

    def test_unsupported_or_duplicate_models_rejected(self):
        for name in ("GT6800", "iDX6011", "DXP6800\nOther"):
            report = copy.deepcopy(self.report)
            report["results"][0]["system_product_name"] = name
            with self.assertRaises(ValueError):
                validate_report(report, self.manifest, "a" * 64)
        self.report["results"].append(copy.deepcopy(self.report["results"][0]))
        with self.assertRaises(ValueError):
            validate_report(self.report, self.manifest, "a" * 64)

    def exercise_publication(self, existing=None, draft=False):
        receipt = Path("unraid-7.4.0-beta.2-r1.json")
        name = "approved-" + receipt.name
        remote = {"tag_name": self.manifest["kernel"], "draft": draft,
                  "assets": [] if existing is None else [{"name": name}]}
        uploaded = []
        def effect(*args):
            if args[:3] == ("gh", "release", "upload"):
                uploaded.append(json.loads(args[4].read_text()))
            if args[:3] == ("gh", "release", "download"):
                (Path(args[-1]) / name).write_text(json.dumps(existing))
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(promotion, "validate_candidate", return_value=(self.manifest, receipt)), \
                patch.object(promotion, "digest", return_value="a" * 64), \
                patch.object(promotion, "output", return_value=self.report["evidence_url"]), \
                patch.object(promotion, "github_releases", return_value=[remote]), \
                patch.object(promotion, "run", side_effect=effect) as run:
            promotion.approve(Path(directory), self.report, "maintainer")
        return uploaded, [c.args for c in run.call_args_list]

    def test_approval_upload_precedes_release_edit_and_retry_preserves_it(self):
        uploaded, calls = self.exercise_publication()
        self.assertEqual(len(uploaded), 1)
        self.assertEqual(calls[0][:3], ("gh", "release", "upload"))
        self.assertEqual(calls[-1][:3], ("gh", "release", "edit"))
        uploaded, calls = self.exercise_publication(existing=uploaded[0])
        self.assertEqual(uploaded, [])
        self.assertEqual(calls[0][:3], ("gh", "release", "download"))
        self.assertIn("--prerelease=false", calls[-1])

    def test_changed_approval_is_not_overwritten(self):
        uploaded, _ = self.exercise_publication()
        uploaded[0]["manifest_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            self.exercise_publication(existing=uploaded[0])

    def test_draft_cannot_be_approved(self):
        with self.assertRaisesRegex(ValueError, "published kernel candidate"):
            self.exercise_publication(draft=True)


if __name__ == "__main__":
    unittest.main()
