#!/usr/bin/env python3
"""Create test doubles only inside the disposable runtime-proof directory."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
if not str(root).startswith('/tmp/ugreen-runtime-proof.') or root.parts[-2:] != ('initramfs', 'main'):
    raise SystemExit('Refusing to modify anything except the disposable runtime proof root')
manifest_path = next((root / 'boot/config/plugins/ugreen-leds/packages').glob('*/*/unraid-*-r1.json'))
manifest = json.loads(manifest_path.read_text())
kernel = manifest['kernel']
for path in ('run', 'tmp/plugins', 'var/log/plugins', 'boot/config/plugins', 'dev'):
    (root / path).mkdir(parents=True, exist_ok=True)
# Test-only identity and process boundaries. No /dev, /proc, or /sys host mounts.
uname = root / 'bin/uname'
uname.rename(root / 'bin/uname.real')
doubles = {
    'bin/uname': f'''#!/bin/bash
case "$1" in -r) echo '{kernel}' ;; *) exec /bin/uname.real "$@" ;; esac
''',
    'usr/sbin/dmidecode': '#!/bin/bash\necho "DXP6800 Pro"\n',
    'usr/bin/pgrep': '#!/bin/bash\nexit 1\n',
    'usr/bin/at': '#!/bin/bash\ncat >> /tmp/monitor-start-requests\n',
    'sbin/modprobe': '#!/bin/bash\necho "FORBIDDEN hardware activation" >&2\nexit 97\n',
}
for name, content in doubles.items():
    path = root / name
    if path.is_symlink():
        path.unlink()
    path.write_text(content)
    path.chmod(0o755)
# An ordinary file at /dev/null is sufficient for this filesystem-only proof.
# It is not a passthrough device, and no hardware nodes are exposed.
(root / 'dev/null').touch(exist_ok=True)
approval = {'schema': 1, 'recipe': 1, 'status': 'approved',
            'unraid': manifest['unraid'], 'kernel': kernel,
            'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            'system_product_names': ['DXP6800 Pro'],
            'TEST_ONLY': 'Synthetic admission fixture; NOT hardware approval; never publish'}
# Keep the fixture outside the cache for the initial negative test.
(root / 'tmp/TEST-ONLY-approval.json').write_text(json.dumps(approval))
