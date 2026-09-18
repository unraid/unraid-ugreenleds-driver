#!/bin/bash
# Disposable Linux container only: /inputs and /candidate and /repo read-only.
# No network or host device/proc/sys mounts. Never run against a NAS root.
set -euo pipefail
[[ $(uname -s) == Linux && $EUID == 0 && -f /.dockerenv ]]
work=$(mktemp -d /tmp/ugreen-runtime-proof.XXXXXXXX)
printf 'Disposable runtime proof: %s\n' "$work"
unmkinitramfs /inputs/bzroot "$work/initramfs"
runtime="$work/initramfs/main"
[[ -f $runtime/etc/unraid-version ]]
# bzmodules is the /usr squashfs, including PHP and the shipped Plugin Manager.
unsquashfs -no-progress -d "$runtime/usr" /inputs/bzmodules
mkdir -p "$runtime/boot/config/plugins/ugreen-leds/packages" "$runtime/tmp/plugins"
mapfile -t receipts < <(find /candidate -maxdepth 1 -name 'unraid-*-r1.json')
[[ ${#receipts[@]} == 1 ]]
version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["unraid"])' "${receipts[0]}")
kernel=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["kernel"])' "${receipts[0]}")
cache="$runtime/boot/config/plugins/ugreen-leds/packages/$kernel/$version-r1"
mkdir -p "$cache"
cp /candidate/* "$cache/"
cp /repo/ugreen-leds.plg "$runtime/tmp/plugins/ugreen-leds.plg"
python3 /repo/source/tests/prepare-runtime-fixture.py "$runtime"
manager=/usr/local/emhttp/plugins/dynamix.plugin.manager/scripts/plugin
if chroot "$runtime" "$manager" install /tmp/plugins/ugreen-leds.plg > "$work/rejection.log" 2>&1; then
  echo 'FAIL: unapproved candidate installed' >&2; exit 1
fi
grep -F 'Missing regular candidate or approval receipt' "$work/rejection.log"
[[ ! -e $runtime/tmp/monitor-start-requests ]]
cp "$runtime/tmp/TEST-ONLY-approval.json" "$cache/approved-unraid-$version-r1.json"
chroot "$runtime" "$manager" install /tmp/plugins/ugreen-leds.plg > "$work/install.log" 2>&1 || {
  cat "$work/install.log"; exit 1;
}
[[ $(cat "$runtime/tmp/monitor-start-requests") == /usr/bin/ugreen-leds ]]
[[ -L $runtime/var/log/plugins/ugreen-leds.plg ]]
cmp /repo/ugreen-leds.plg "$runtime/boot/config/plugins/ugreen-leds.plg"
cmp /repo/source/settings.cfg.example "$runtime/boot/config/plugins/ugreenleds-driver/settings.cfg"
for tool in i2cdetect i2cdump i2cget i2cset i2ctransfer; do
  chroot "$runtime" "/usr/sbin/$tool" -V
done
# Exercise migration and repeat installation through the actual manager too.
settings="$runtime/boot/config/plugins/ugreenleds-driver/settings.cfg"
printf '\n# retained custom mapping marker\n' >> "$settings"
cp "$settings" "$work/retained-settings"
cp /repo/ugreenleds-driver.plg "$runtime/boot/config/plugins/ugreenleds-driver.plg"
chroot "$runtime" "$manager" install /tmp/plugins/ugreen-leds.plg forced > "$work/migration.log" 2>&1 || {
  cat "$work/migration.log"; exit 1;
}
grep -F 'Reboot required' "$work/migration.log"
[[ $(wc -l < "$runtime/tmp/monitor-start-requests") == 1 ]]
cmp /repo/ugreenleds-driver.plg "$runtime/boot/config/plugins/ugreen-leds/legacy/ugreenleds-driver.plg.disabled"
cmp "$settings" "$work/retained-settings"
chroot "$runtime" "$manager" install /tmp/plugins/ugreen-leds.plg forced > "$work/reinstall.log" 2>&1 || {
  cat "$work/reinstall.log"; exit 1;
}
[[ $(wc -l < "$runtime/tmp/monitor-start-requests") == 2 ]]
cmp "$settings" "$work/retained-settings"
chroot "$runtime" "$manager" remove ugreen-leds.plg > "$work/removal.log" 2>&1 || {
  cat "$work/removal.log"; exit 1;
}
[[ ! -e $runtime/boot/config/plugins/ugreen-leds.plg && -d $cache ]]
cmp "$settings" "$work/retained-settings"
chroot "$runtime" /bin/bash /usr/local/emhttp/plugins/ugreen-leds/ugreen-plugin.sh restore-legacy
cmp /repo/ugreenleds-driver.plg "$runtime/boot/config/plugins/ugreenleds-driver.plg"
cmp "$settings" "$work/retained-settings"
printf '%s\n' 'PASS: shipped Plugin Manager rejected missing approval, then installed real packages using a private synthetic approval fixture.' \
  'PASS: installed-byte checks, boot registration, original defaults, and stock-library i2c tool version checks.' \
  'PASS: real Plugin Manager migration deferral, repeat installation, removal, retained custom settings/cache, and explicit legacy boot-file recovery.' \
  'LIMIT: identity/process/startup boundaries are test doubles. No hardware approval, module load, physical network test, or real reboot.'
