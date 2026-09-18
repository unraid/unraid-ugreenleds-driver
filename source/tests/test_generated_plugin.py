from pathlib import Path
import hashlib
import runpy
import subprocess
import unittest
import xml.etree.ElementTree as ET


class GeneratedPluginTests(unittest.TestCase):
    def test_embedded_sources_and_boot_command_match(self):
        source = Path(__file__).resolve().parents[1]
        generator = runpy.run_path(str(source / "generate-plugin.py"))
        rendered = generator["render"]()
        self.assertEqual((source.parent / "ugreen-leds.plg").read_text(), rendered)
        plugin = ET.fromstring(rendered)
        self.assertEqual(plugin.attrib["name"], "ugreen-leds")
        files = plugin.findall("FILE")
        for item, name in zip(files, generator["FILES"]):
            content = item.find("INLINE").text
            self.assertEqual(content, (source / name).read_text())
            self.assertEqual(item.attrib["Mode"], "0644")
            self.assertEqual(item.find("SHA256").text,
                             hashlib.sha256((content.strip() + "\n").encode()).hexdigest())
            if name.endswith(".sh"):
                result = subprocess.run(["bash", "-n"], input=content, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(files[-2].find("INLINE").text,
                         "bash /usr/local/emhttp/plugins/ugreen-leds/ugreen-plugin.sh\n")
        removal = files[-1].find("INLINE").text
        self.assertIn("rm -f /usr/local/emhttp/plugins/dynamix.plugin.manager/post-hooks/ugreen-leds-prefetch", removal)
        self.assertEqual(files[-3].attrib["Mode"], "0755")
        self.assertEqual(files[-3].find("INLINE").text, (source / "prefetch-os-update.sh").read_text())
        self.assertNotIn("removepkg", removal)
        self.assertNotIn("modprobe", removal)


if __name__ == "__main__":
    unittest.main()
