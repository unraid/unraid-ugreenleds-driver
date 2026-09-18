#!/usr/bin/env python3
"""Embed reviewed installer sources in the Unraid plugin without runtime downloads."""
import argparse
import hashlib
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
DESTINATION = "/usr/local/emhttp/plugins/ugreen-leds"
FILES = ("ugreen-plugin.sh", "install-approved-bundle.sh", "plugin-migration.sh",
         "cache-install-bundle.sh", "verify-install-bundle.sh", "verify-installed-payload.sh",
         "prefetch-boot-bundle.sh",
         "validate-install-manifest.jq", "settings.cfg.example")


def render():
    parts = ["<?xml version='1.0' standalone='yes'?>",
             '<PLUGIN name="ugreen-leds" author="unraid" version="2026.09.18" min="7.0.0" '
             'pluginURL="https://raw.githubusercontent.com/unraid/unraid-ugreenleds-driver/master/ugreen-leds.plg" '
             'support="https://github.com/unraid/unraid-ugreenleds-driver/issues">',
             '<CHANGES>Kernel-specific packages require exact target and hardware approval. '
             'Legacy migration preserves settings and defers activation to reboot.</CHANGES>']
    entries = [(name, f"{DESTINATION}/{name}", "0644") for name in FILES]
    entries.append(("prefetch-os-update.sh", "/usr/local/emhttp/plugins/dynamix.plugin.manager/post-hooks/ugreen-leds-prefetch", "0755"))
    for name, destination, mode in entries:
        raw = (HERE / name).read_text()
        # Unraid writes INLINE as trim(content) plus one newline. Hash that
        # representation so later plugin updates replace stale helper files.
        checksum = hashlib.sha256((raw.strip() + '\n').encode()).hexdigest()
        content = escape(raw, quote=False)
        parts.append(f'<FILE Name="{destination}" Mode="{mode}"><INLINE>{content}</INLINE>'
                     f'<SHA256>{checksum}</SHA256></FILE>')
    parts.append(f'<FILE Run="/bin/bash"><INLINE>bash {DESTINATION}/ugreen-plugin.sh\n</INLINE></FILE>')
    parts.append('<FILE Run="/bin/bash" Method="remove"><INLINE>'
                 'rm -f /usr/local/emhttp/plugins/dynamix.plugin.manager/post-hooks/ugreen-leds-prefetch\n'
                 'echo "UGREEN boot startup removed. Reboot to stop the loaded driver and monitor."\n'
                 'echo "Settings, cached packages, and legacy boot-file backups were retained."\n'
                 '</INLINE></FILE>')
    parts.append('</PLUGIN>')
    return '\n'.join(parts) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = HERE.parent / 'ugreen-leds.plg'
    expected = render()
    if args.check:
        if not path.exists() or path.read_text() != expected:
            raise SystemExit('Generated plugin differs: run python3 source/generate-plugin.py')
    else:
        path.write_text(expected)


if __name__ == '__main__':
    main()
