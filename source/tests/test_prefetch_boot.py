import hashlib
import os
from pathlib import Path
import subprocess
import unittest

import test_install_cache


class BootPrefetchTests(unittest.TestCase):
    def setUp(self):
        self.cache_test = test_install_cache.InstallCacheTests()
        self.cache_test.setUp()
        self.addCleanup(self.cache_test.doCleanups)
        self.root = self.cache_test.root
        self.boot = self.root / "staged-boot"
        self.boot.mkdir()
        self.changes = self.boot / "changes.txt"
        self.changes.write_text('# Version 7.4.0-beta.2 2026-09-03\n\n## Linux kernel\n\n* version 6.18.47-Unraid\n')
        self.modules = self.boot / "bzmodules"
        self.modules.write_bytes(b"staged module image")
        (self.boot / "bzmodules.sha256").write_text(hashlib.sha256(self.modules.read_bytes()).hexdigest() + "\n")
        mount = self.cache_test.bin / "mount"
        mount.write_text('#!/bin/bash\nset -eu\n[[ "$1 $2 $3 $4" == "-t squashfs -o loop,ro,nodev,nosuid,noexec" ]]\nmkdir -p "$6/src/linux-6.18.47-Unraid"\ncp "$TEST_CONFIG" "$6/src/linux-6.18.47-Unraid/config"\ntouch "$6/.mounted"\n')
        mount.chmod(0o755)
        unmount = self.cache_test.bin / "umount"
        unmount.write_text('#!/bin/bash\nset -eu\nrm "$2/.mounted"\n')
        unmount.chmod(0o755)
        mountpoint = self.cache_test.bin / "mountpoint"
        mountpoint.write_text('#!/bin/bash\n[[ -f $2/.mounted ]]\n')
        mountpoint.chmod(0o755)
        uname = self.cache_test.bin / "uname"
        uname.write_text('#!/bin/bash\necho "Running kernel must not be queried" >&2\nexit 99\n')
        uname.chmod(0o755)

    def prefetch(self):
        env = dict(os.environ, PATH=str(self.cache_test.bin) + os.pathsep + os.environ["PATH"],
                   TEST_REQUESTS=str(self.cache_test.log), TEST_SOURCE=str(self.root),
                   TEST_CONFIG=str(self.cache_test.fixture.config))
        script = Path(__file__).resolve().parents[1] / "prefetch-boot-bundle.sh"
        return subprocess.run(["bash", str(script), str(self.boot), str(self.cache_test.cache), "DXP6800 Pro"],
                              env=env, capture_output=True, text=True)

    def test_target_metadata_and_config_select_bundle_without_uname(self):
        result = self.prefetch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.cache_test.bundle.exists())
        self.assertIn('ready for staged OS 7.4.0-beta.2, kernel 6.18.47-Unraid', result.stdout)

    def test_corrupt_staged_image_does_not_download(self):
        self.modules.write_bytes(b"corrupt")
        self.assertNotEqual(self.prefetch().returncode, 0)
        self.assertFalse(self.cache_test.log.exists())

    def test_kernel_cannot_be_borrowed_from_an_older_section(self):
        self.changes.write_text('# Version 7.4.0-beta.2 2026-09-03\n# Version 7.3.2 2026-07-08\n* version 6.18.47-Unraid\n')
        self.assertNotEqual(self.prefetch().returncode, 0)
        self.assertFalse(self.cache_test.log.exists())

    def test_ambiguous_target_kernel_does_not_download(self):
        self.changes.write_text(self.changes.read_text() + '* version 6.18.48-Unraid\n')
        self.assertNotEqual(self.prefetch().returncode, 0)
        self.assertFalse(self.cache_test.log.exists())

    def test_wrong_stock_config_stops_before_package_downloads(self):
        self.cache_test.fixture.config.write_bytes(b"wrong stock config")
        self.assertNotEqual(self.prefetch().returncode, 0)
        self.assertEqual(len(self.cache_test.log.read_text().splitlines()), 2)
        self.assertFalse(self.cache_test.bundle.exists())

    def test_mount_failure_does_not_download(self):
        (self.cache_test.bin / "mount").write_text('#!/bin/bash\nexit 32\n')
        self.assertNotEqual(self.prefetch().returncode, 0)
        self.assertFalse(self.cache_test.log.exists())


if __name__ == "__main__":
    unittest.main()
