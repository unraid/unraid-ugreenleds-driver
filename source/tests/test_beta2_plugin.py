import hashlib
import json
from pathlib import Path
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


class Beta2PluginTests(unittest.TestCase):
    def test_pinned_downloads_and_normalized_inline_hashes(self):
        plugin = ET.parse(ROOT / "ugreen-leds-beta2.plg").getroot()
        self.assertEqual(plugin.attrib["name"], "ugreen-leds-beta2")
        self.assertNotIn("pluginURL", plugin.attrib)
        self.assertEqual(plugin.attrib["min"], "7.4.0-beta.2")
        self.assertEqual(plugin.attrib["max"], "7.4.0-beta.2")
        pins = json.loads((ROOT / "source/beta2-test-packages.json").read_text())
        downloads = [f for f in plugin.findall("FILE") if f.find("URL") is not None]
        self.assertEqual(len(downloads), 3)
        for entry, package in zip(downloads, pins["packages"]):
            self.assertEqual(entry.findtext("SHA256"), package["sha256"])
            self.assertEqual(entry.findtext("URL"), "https://github.com/unraid/unraid-ugreenleds-driver/releases/download/6.18.47-Unraid/" + package["name"])
            self.assertTrue(entry.attrib["Name"].endswith(package["name"].removeprefix("unraid-7.4.0-beta.2-r1--")))
        for entry in plugin.findall("FILE"):
            if entry.find("INLINE") is not None and entry.find("SHA256") is not None:
                raw = entry.findtext("INLINE").strip() + "\n"
                self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(), entry.findtext("SHA256"))
            if "Run" in entry.attrib:
                subprocess.run(["bash", "-n"], input=entry.findtext("INLINE"), text=True, check=True)

    def test_preflight_precedes_downloads_and_no_approval_bypass(self):
        plugin = ET.parse(ROOT / "ugreen-leds-beta2.plg").getroot()
        entries = plugin.findall("FILE")
        preflight = next(i for i, f in enumerate(entries) if "beta2-test.sh check" in (f.findtext("INLINE") or ""))
        first_download = next(i for i, f in enumerate(entries) if f.find("URL") is not None)
        self.assertLess(preflight, first_download)
        script = (ROOT / "source/beta2-test.sh").read_text()
        self.assertNotIn("approved-unraid", script)
        self.assertNotIn("install-approved-bundle", script)
        self.assertIn("--install-new --reinstall", script)
        self.assertIn("verify-installed-payload.sh", script)
