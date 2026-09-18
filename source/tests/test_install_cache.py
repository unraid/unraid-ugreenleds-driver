import os
from pathlib import Path
import subprocess
import sys
import unittest

import test_install_bundle


class InstallCacheTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_install_bundle.InstallBundleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.cache = self.root / "cache"
        self.bundle = self.cache / "6.18.47-Unraid/7.4.0-beta.2-r1"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "requests"
        # Only the HTTP boundary is replaced. Real jq, hashing, filesystem,
        # cache locking, staging, and bundle admission execute unchanged.
        curl = self.bin / "curl"
        curl.write_text(f"#!{sys.executable}\n" + """
import os, pathlib, shutil, sys
args = sys.argv[1:]
url = args[-1]
assert url.startswith('https://github.com/unraid/unraid-ugreenleds-driver/releases/download/6.18.47-Unraid/')
assert args[args.index('--proto') + 1] == '=https'
assert args[args.index('--proto-redir') + 1] == '=https'
with open(os.environ['TEST_REQUESTS'], 'a') as log:
    log.write(url + '\\n')
name = url.rsplit('/', 1)[-1]
source = pathlib.Path(os.environ['TEST_SOURCE']) / name
if not source.exists():
    sys.exit(22)
shutil.copyfile(source, args[args.index('--output') + 1])
""")
        curl.chmod(0o755)

    def acquire(self):
        env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                   TEST_SOURCE=str(self.root), TEST_REQUESTS=str(self.log))
        return subprocess.run(["bash", str(Path(__file__).resolve().parents[1] / "cache-install-bundle.sh"),
                               str(self.cache), "7.4.0-beta.2", "6.18.47-Unraid",
                               str(self.fixture.config), "DXP6800 Pro"],
                              env=env, capture_output=True, text=True)

    def test_download_then_offline_reuse(self):
        result = self.acquire()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.bundle))
        requests = self.log.read_text()
        self.assertEqual(len(requests.splitlines()), 5)
        self.fixture.approval.unlink()  # Remote approval unavailable now.
        self.assertEqual(self.acquire().returncode, 0)
        self.assertEqual(self.log.read_text(), requests)

    def test_missing_approval_leaves_no_published_or_partial_bundle(self):
        self.fixture.approval.unlink()
        result = self.acquire()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.bundle.exists())
        self.assertEqual(list(self.bundle.parent.iterdir()), [])

    def test_invalid_existing_cache_does_not_download_or_replace(self):
        self.assertEqual(self.acquire().returncode, 0)
        requests = self.log.read_text()
        package = self.bundle / self.fixture.manifest["packages"]["kernel"]
        package.write_bytes(b"corrupt")
        result = self.acquire()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.log.read_text(), requests)
        self.assertEqual(package.read_bytes(), b"corrupt")

    def test_lock_refuses_second_writer(self):
        lock = self.bundle.parent / ".7.4.0-beta.2-r1.lock"
        lock.mkdir(parents=True)
        result = self.acquire()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(lock.exists())
        self.assertFalse(self.log.exists())

    def test_corrupt_download_is_not_committed(self):
        package = self.root / self.fixture.manifest["packages"]["monitor"]
        package.write_bytes(b"corrupt remote archive")
        result = self.acquire()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.bundle.exists())
        self.assertEqual(list(self.bundle.parent.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
