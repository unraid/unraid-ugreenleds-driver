#!/bin/bash
# Isolated shipped beta2 runtime only. No real module loading or device access.
set -euo pipefail
[[ $(uname -s) == Linux && $EUID == 0 && -f /.dockerenv ]]
work=$(mktemp -d /tmp/ugreen-runtime-proof.XXXXXXXX)
echo "Beta2 plugin proof: $work"
unmkinitramfs /inputs/bzroot "$work/initramfs"
runtime="$work/initramfs/main"
unsquashfs -no-progress -d "$runtime/usr" /inputs/bzmodules
original="$runtime/boot/config/plugins/ugreen-leds/packages/6.18.47-Unraid/7.4.0-beta.2-r1"
cache="$runtime/boot/config/plugins/ugreen-leds-beta2/packages/6.18.47-Unraid"
mkdir -p "$original" "$cache" "$runtime/tmp/plugins"
cp /candidate/* "$original/"
python3 /repo/source/tests/prepare-runtime-fixture.py "$runtime"
rm -- "$runtime/tmp/TEST-ONLY-approval.json"
assets=$(python3 -c 'import json; print("\n".join(p["name"] for p in json.load(open("/repo/source/beta2-test-packages.json"))["packages"]))')
while read -r asset; do
  cp "/candidate/$asset" "$cache/${asset#unraid-7.4.0-beta.2-r1--}"
done <<< "$assets"
cp /repo/ugreen-leds-beta2.plg "$runtime/tmp/plugins/ugreen-leds-beta2.plg"
manager=/usr/local/emhttp/plugins/dynamix.plugin.manager/scripts/plugin
run_install() {
  chroot "$runtime" "$manager" install /tmp/plugins/ugreen-leds-beta2.plg forced > "$work/install.log" 2>&1
}
# Wrong target and plugin conflicts must stop before package/startup effects.
cp "$runtime/etc/unraid-version" "$work/version"
printf 'version="7.3.2"\n' > "$runtime/etc/unraid-version"
if run_install; then echo 'FAIL: wrong OS accepted'; exit 1; fi
[[ ! -e $runtime/tmp/monitor-start-requests ]]
cp "$work/version" "$runtime/etc/unraid-version"
cp "$runtime/bin/uname" "$work/uname"
sed 's/6.18.47-Unraid/6.18.48-Unraid/g' "$work/uname" > "$runtime/bin/uname"
if run_install; then echo 'FAIL: wrong kernel accepted'; exit 1; fi
grep -F 'Requires exactly kernel' "$work/install.log"
cp "$work/uname" "$runtime/bin/uname"
cp "$runtime/usr/src/linux-6.18.47-Unraid/config" "$work/config"
printf '\n# changed configuration\n' >> "$runtime/usr/src/linux-6.18.47-Unraid/config"
if run_install; then echo 'FAIL: wrong configuration accepted'; exit 1; fi
grep -F 'Stock configuration mismatch' "$work/install.log"
cp "$work/config" "$runtime/usr/src/linux-6.18.47-Unraid/config"
cp "$runtime/usr/sbin/dmidecode" "$work/dmidecode"
printf '#!/bin/bash\necho Unsupported\n' > "$runtime/usr/sbin/dmidecode"
if run_install; then echo 'FAIL: unsupported model accepted'; exit 1; fi
grep -F 'Unsupported test model' "$work/install.log"
cp "$work/dmidecode" "$runtime/usr/sbin/dmidecode"
cp /repo/ugreenleds-driver.plg "$runtime/boot/config/plugins/ugreenleds-driver.plg"
if run_install; then echo 'FAIL: conflicting plugin accepted'; exit 1; fi
grep -F 'Disable ugreenleds-driver.plg' "$work/install.log"
rm -- "$runtime/boot/config/plugins/ugreenleds-driver.plg"
run_install || { cat "$work/install.log"; exit 1; }
[[ $(cat "$runtime/tmp/monitor-start-requests") == /usr/bin/ugreen-leds ]]
cmp /repo/ugreen-leds-beta2.plg "$runtime/boot/config/plugins/ugreen-leds-beta2.plg"
settings="$runtime/boot/config/plugins/ugreenleds-driver/settings.cfg"
cmp /repo/source/settings.cfg.example "$settings"
printf '\n# retained test settings\n' >> "$settings"
cp "$settings" "$work/settings"
# An active module defers installation and never submits a second monitor.
mkdir -p "$runtime/sys/module/led_ugreen"
run_install || { cat "$work/install.log"; exit 1; }
grep -F 'Reboot required' "$work/install.log"
[[ $(wc -l < "$runtime/tmp/monitor-start-requests") == 1 ]]
cmp "$settings" "$work/settings"
rmdir "$runtime/sys/module/led_ugreen"
# Direct installer admission must reject modified cached package bytes too.
package=$(python3 -c 'import json; print(json.load(open("/repo/source/beta2-test-packages.json"))["packages"][2]["name"])')
name=${package#unraid-7.4.0-beta.2-r1--}
printf corrupt >> "$cache/$name"
if chroot "$runtime" /bin/bash /usr/local/emhttp/plugins/ugreen-leds-beta2/beta2-test.sh install > "$work/corrupt.log" 2>&1; then
  echo 'FAIL: corrupt package accepted'; exit 1
fi
grep -F 'Package size mismatch' "$work/corrupt.log"
[[ $(wc -l < "$runtime/tmp/monitor-start-requests") == 1 ]]
cp "/candidate/$package" "$cache/$name"
printf A | dd of="$cache/$name" bs=1 count=1 conv=notrunc status=none
if chroot "$runtime" /bin/bash /usr/local/emhttp/plugins/ugreen-leds-beta2/beta2-test.sh install > "$work/corrupt.log" 2>&1; then
  echo 'FAIL: same-size corruption accepted'; exit 1
fi
grep -F 'Package checksum mismatch' "$work/corrupt.log"
[[ $(wc -l < "$runtime/tmp/monitor-start-requests") == 1 ]]
cp "/candidate/$package" "$cache/$name"
run_install || { cat "$work/install.log"; exit 1; }
[[ $(wc -l < "$runtime/tmp/monitor-start-requests") == 2 ]]
cmp "$settings" "$work/settings"
chroot "$runtime" "$manager" remove ugreen-leds-beta2.plg > "$work/remove.log" 2>&1 || {
  cat "$work/remove.log"; exit 1;
}
[[ ! -e $runtime/boot/config/plugins/ugreen-leds-beta2.plg && -d $cache ]]
cmp "$settings" "$work/settings"
echo 'PASS: real beta2 Plugin Manager installs pinned test packages without approval, preserves settings, defers active drivers, rejects conflicts/corruption, and removes boot startup.'
echo 'LIMIT: identity/process/startup boundaries are doubles. No physical module load, network test, or real reboot.'
