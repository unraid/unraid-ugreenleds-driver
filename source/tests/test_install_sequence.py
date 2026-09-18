import os
import hashlib
import io
import json
import tarfile
from pathlib import Path
import subprocess
import unittest

import test_install_bundle


class InstallSequenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_install_bundle.InstallBundleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.runtime = self.fixture.root / "runtime"
        for directory in ("boot/config/plugins", "run", "tmp", "sbin", "usr/bin", "sys/module", "var/lib/pkgtools/packages"):
            (self.runtime / directory).mkdir(parents=True)
        self.plugins = self.runtime / "boot/config/plugins"
        self.log = self.runtime / "effects"
        self.settings = self.plugins / "ugreenleds-driver/settings.cfg"
        self.settings.parent.mkdir()
        self.settings.write_text('CUSTOM="preserve"\n')
        for role, name in self.fixture.manifest["packages"].items():
            archive = self.fixture.root / name
            with tarfile.open(archive, "w:xz") as package:
                data = (role + " payload").encode()
                member = tarfile.TarInfo("usr/share/ugreen-test/" + role)
                member.size = len(data)
                package.addfile(member, io.BytesIO(data))
            record = next(a for a in self.fixture.manifest["assets"] if a["name"] == name)
            record.update(size=archive.stat().st_size, sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
        self.fixture.receipt.write_text(json.dumps(self.fixture.manifest))
        approval = json.loads(self.fixture.approval.read_text())
        approval["manifest_sha256"] = hashlib.sha256(self.fixture.receipt.read_bytes()).hexdigest()
        self.fixture.approval.write_text(json.dumps(approval))
        for name in ("sbin/upgradepkg", "sbin/depmod", "usr/bin/at"):
            script = self.runtime / name
            script.write_text('#!/bin/bash\nset -eu\nprintf "%s %s\\n" "${0##*/}" "$*" >> "$TEST_LOG"\n'
                              '[[ ${0##*/} != "${FAIL_EFFECT:-}" ]] || exit 12\n'
                              'if [[ ${0##*/} == upgradepkg ]]; then\n'
                              '  [[ "$1 $2" == "--install-new --reinstall" ]] || exit 13\n'
                              '  [[ ${SILENT_SKIP:-0} == 0 ]] || exit 0\n'
                              '  tar -xf "$3" -C "$TEST_RUNTIME"\n'
                              '  name=${3##*/}; touch "$TEST_RUNTIME/var/lib/pkgtools/packages/${name%.txz}"\n'
                              '  if [[ ${CORRUPT_PAYLOAD:-0} == 1 ]]; then printf bad > "$TEST_RUNTIME/usr/share/ugreen-test/i2c_tools"; fi\n'
                              'fi\n'
                              'if [[ ${0##*/} == at ]]; then cat >> "$TEST_LOG"; fi\n')
            script.chmod(0o755)
        self.pgrep = self.runtime / "usr/bin/pgrep"
        self.pgrep.write_text('#!/bin/bash\nexit "${PGREP_STATUS:-1}"\n')
        self.pgrep.chmod(0o755)

    def install(self, **environment):
        library = Path(__file__).resolve().parents[1] / "install-approved-bundle.sh"
        env = dict(os.environ, TEST_LOG=str(self.log), TEST_RUNTIME=str(self.runtime), **environment)
        return subprocess.run(["bash", "-c", 'source "$1"; shift; ugreen_install_approved "$@"',
                               "test", str(library), str(self.runtime), str(self.fixture.root),
                               "7.4.0-beta.2", "6.18.47-Unraid", str(self.fixture.config), "DXP6800 Pro"],
                              env=env, capture_output=True, text=True)

    def test_install_orders_packages_then_depmod_then_startup(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.log.read_text().splitlines()
        self.assertIn("/i2c-tools-test.txz", lines[0])
        self.assertIn("/ugreen_leds-test.txz", lines[1])
        self.assertIn("/ugreenleds-driver-test.txz", lines[2])
        self.assertEqual(lines[3:], ["depmod -a 6.18.47-Unraid", "at now -M", "/usr/bin/ugreen-leds"])
        self.assertEqual(self.settings.read_text(), 'CUSTOM="preserve"\n')
        self.assertEqual(list((self.runtime / "tmp").iterdir()), [])

    def test_invalid_approval_has_no_package_or_migration_effect(self):
        self.fixture.approval.unlink()
        old = self.plugins / "ugreenleds-driver.plg"
        old.write_text("old boot plugin")
        self.assertNotEqual(self.install().returncode, 0)
        self.assertTrue(old.exists())
        self.assertFalse(self.log.exists())

    def test_legacy_migration_defers_until_next_boot(self):
        old = self.plugins / "ugreenleds-driver.plg"
        old.write_text("old boot plugin")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Reboot required", result.stdout)
        self.assertFalse(self.log.exists())
        self.assertEqual((self.plugins / "ugreen-leds/legacy/ugreenleds-driver.plg.disabled").read_text(), "old boot plugin")

    def test_loaded_module_or_running_monitor_defers(self):
        self.assertEqual(self.install(PGREP_STATUS="0").returncode, 0)
        self.assertFalse(self.log.exists())
        (self.runtime / "sys/module/led_ugreen").mkdir()
        self.assertEqual(self.install().returncode, 0)
        self.assertFalse(self.log.exists())

    def test_process_inspection_error_does_not_authorize_install(self):
        self.assertNotEqual(self.install(PGREP_STATUS="2").returncode, 0)
        self.assertFalse(self.log.exists())

    def test_failed_package_does_not_start_monitor(self):
        self.assertNotEqual(self.install(FAIL_EFFECT="upgradepkg").returncode, 0)
        self.assertEqual(len(self.log.read_text().splitlines()), 1)
        self.assertEqual(self.settings.read_text(), 'CUSTOM="preserve"\n')

    def test_new_install_creates_original_defaults(self):
        self.settings.unlink()
        self.assertEqual(self.install().returncode, 0)
        defaults = Path(__file__).resolve().parents[1] / "settings.cfg.example"
        self.assertEqual(self.settings.read_bytes(), defaults.read_bytes())

    def test_zero_exit_without_installation_does_not_start_monitor(self):
        self.assertNotEqual(self.install(SILENT_SKIP="1").returncode, 0)
        self.assertEqual(len(self.log.read_text().splitlines()), 1)

    def test_zero_exit_with_corrupt_installed_bytes_does_not_start_monitor(self):
        self.assertNotEqual(self.install(CORRUPT_PAYLOAD="1").returncode, 0)
        self.assertEqual(len(self.log.read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
