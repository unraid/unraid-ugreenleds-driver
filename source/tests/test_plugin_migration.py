from pathlib import Path
import subprocess
import tempfile
import unittest


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = self.root / "ugreenleds-driver.plg"
        self.new = self.root / "ugreen-leds.plg"
        self.saved = self.root / "ugreen-leds/legacy/ugreenleds-driver.plg.disabled"
        self.old.write_bytes(b"original boot plugin")
        self.settings = self.root / "ugreenleds-driver/settings.cfg"
        self.settings.parent.mkdir()
        self.settings.write_bytes(b'CUSTOM_DISK_MAPPING="keep me"\n')
        self.package = self.settings.parent / "old-package.txz"
        self.package.write_bytes(b"recovery package")

    def invoke(self, function):
        library = Path(__file__).resolve().parents[1] / "plugin-migration.sh"
        return subprocess.run(["bash", "-c", 'source "$1"; "$2" "$3"', "test",
                               str(library), function, str(self.root)], capture_output=True, text=True)

    def assert_settings_retained(self):
        self.assertEqual(self.settings.read_bytes(), b'CUSTOM_DISK_MAPPING="keep me"\n')
        self.assertEqual(self.package.read_bytes(), b"recovery package")

    def test_migration_and_retry_preserve_original_settings_and_packages(self):
        for _ in range(2):
            result = self.invoke("ugreen_disable_legacy")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.old.exists())
        self.assertEqual(self.saved.read_bytes(), b"original boot plugin")
        self.assert_settings_retained()

    def test_backup_conflict_changes_nothing(self):
        self.saved.parent.mkdir(parents=True)
        self.saved.write_bytes(b"older backup")
        self.assertNotEqual(self.invoke("ugreen_disable_legacy").returncode, 0)
        self.assertEqual(self.old.read_bytes(), b"original boot plugin")
        self.assertEqual(self.saved.read_bytes(), b"older backup")
        self.assert_settings_retained()

    def test_restore_disables_replacement_and_restores_original(self):
        self.assertEqual(self.invoke("ugreen_disable_legacy").returncode, 0)
        self.new.write_bytes(b"replacement boot plugin")
        result = self.invoke("ugreen_restore_legacy")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.old.read_bytes(), b"original boot plugin")
        self.assertFalse(self.new.exists())
        self.assertEqual((self.saved.parent / "ugreen-leds.plg.disabled").read_bytes(), b"replacement boot plugin")
        self.assert_settings_retained()

    def test_restore_conflict_does_not_disable_replacement(self):
        self.assertEqual(self.invoke("ugreen_disable_legacy").returncode, 0)
        self.new.write_bytes(b"replacement boot plugin")
        self.old.write_bytes(b"different plugin")
        self.assertNotEqual(self.invoke("ugreen_restore_legacy").returncode, 0)
        self.assertTrue(self.new.exists())
        self.assertTrue(self.saved.exists())

    def test_symlink_legacy_is_not_moved(self):
        self.old.unlink()
        self.old.symlink_to(self.settings)
        self.assertNotEqual(self.invoke("ugreen_disable_legacy").returncode, 0)
        self.assertTrue(self.old.is_symlink())
        self.assert_settings_retained()

    def test_interrupted_restore_can_resume_with_new_plugin_already_disabled(self):
        self.assertEqual(self.invoke("ugreen_disable_legacy").returncode, 0)
        disabled = self.saved.parent / "ugreen-leds.plg.disabled"
        disabled.write_bytes(b"already disabled replacement")
        self.assertEqual(self.invoke("ugreen_restore_legacy").returncode, 0)
        self.assertTrue(self.old.exists())
        self.assertEqual(disabled.read_bytes(), b"already disabled replacement")


if __name__ == "__main__":
    unittest.main()
