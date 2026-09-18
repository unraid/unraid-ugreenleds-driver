import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from discover_unraid import discover


def entry(version, date="2026-09-03"):
    channel = "next" if "-" in version else "stable"
    return {
        "url": f"https://releases.unraid.net/dl/{channel}/{version}/"
        + "a" * 64 + f"/unRAIDServer-{version}-x86_64.zip?utm_source=usb_creator",
        "release_date": date,
    }


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.feed = {"os_list": [
            entry("7.3.2", "2026-07-08"),
            entry("7.2.8", "2026-07-29"),
            entry("6.12.15"),
            {"subitems": [entry("7.4.0-beta.2"), entry("7.3.3-rc.1")]},
        ]}

    def test_all_u7_channels_and_parallel_maintenance_branches(self):
        releases = discover(self.feed)
        self.assertEqual({r["version"] for r in releases},
                         {"7.3.2", "7.2.8", "7.4.0-beta.2", "7.3.3-rc.1"})
        self.assertEqual({r["channel"] for r in releases}, {"stable", "next"})
        self.assertTrue(all("?" not in r["url"] for r in releases))
        self.assertTrue(all("kernel" not in r and "sha256" not in r for r in releases))

    def test_new_maintenance_release_not_hidden_by_higher_beta(self):
        self.feed["os_list"].append(entry("7.2.9", "2026-09-19"))
        self.assertEqual(discover(self.feed)[-1]["version"], "7.2.9")

    def test_exact_version_and_no_partial_match(self):
        self.assertEqual([r["version"] for r in discover(self.feed, "7.4.0-beta.2")],
                         ["7.4.0-beta.2"])
        for version in ("7.4", "7.4.0-beta.3", "6.12.15", "../7.3.2"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                discover(self.feed, version)

    def test_identical_duplicates_are_deduplicated(self):
        self.feed["os_list"].append(copy.deepcopy(self.feed["os_list"][0]))
        self.assertEqual(len(discover(self.feed)), 4)

    def test_conflicting_identity_fails(self):
        duplicate = copy.deepcopy(self.feed["os_list"][0])
        duplicate["url"] = duplicate["url"].replace("a" * 64, "b" * 64)
        self.feed["os_list"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            discover(self.feed)

    def test_foreign_or_malformed_urls_fail(self):
        original = entry("7.3.2")["url"]
        bad_urls = [
            original.replace("https:", "http:"),
            original.replace("releases.unraid.net", "example.com"),
            original.replace("releases.unraid.net", "releases.unraid.net@evil.example"),
            original.replace("releases.unraid.net", "releases.unraid.net:443"),
            original.replace("/7.3.2/", "/7.3.1/"),
            original.replace("/stable/", "/next/"),
            original.replace("x86_64", "aarch64"),
            original + "#fragment", original + "\n", "", None,
        ]
        for url in bad_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                discover({"os_list": [{"url": url, "release_date": "2026-09-03"}]})

    def test_feed_shape_and_dates_fail(self):
        for feed in ({}, {"os_list": None}, {"os_list": [None]},
                     {"os_list": [{"subitems": {}}]}, {"os_list": []}):
            with self.subTest(feed=feed), self.assertRaises(ValueError):
                discover(feed)
        for date in (None, "2026-02-30", "20260903", "2026-9-3"):
            with self.subTest(date=date), self.assertRaises(ValueError):
                discover({"os_list": [entry("7.3.2", date)]})

    def test_selection_does_not_hide_malformed_feed_entries(self):
        self.feed["os_list"].append({"url": "https://example.com/installer.zip"})
        with self.assertRaises(ValueError):
            discover(self.feed, "7.3.2")

    def test_future_major_not_silently_supported(self):
        self.feed["os_list"].append(entry("8.0.0"))
        self.assertEqual(len(discover(self.feed)), 4)

    def test_cli_emits_matrix_only_on_success(self):
        script = Path(__file__).resolve().parents[1] / "discover_unraid.py"
        good = subprocess.run([sys.executable, str(script), "--version", "7.3.2"],
                              input=json.dumps(self.feed), text=True, capture_output=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout)["include"][0]["version"], "7.3.2")
        bad = subprocess.run([sys.executable, str(script)], input="{", text=True,
                             capture_output=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(bad.stdout, "")


if __name__ == "__main__":
    unittest.main()
