#!/bin/bash
# Explicit experimental installer. Never used by the stable plugin.
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
tools=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
pins="$tools/beta2-test-packages.json"
plugins=/boot/config/plugins
cache="$plugins/ugreen-leds-beta2/packages/6.18.47-Unraid"
settings="$plugins/ugreenleds-driver/settings.cfg"
fail() { echo "UGREEN beta2 TEST: $*" >&2; exit 1; }
[[ $# == 1 && ( $1 == check || $1 == install ) ]] || fail 'Expected check or install'
[[ $EUID == 0 && $(uname -m) == x86_64 ]] || fail 'Requires root on x86-64'
grep -qx 'version="7.4.0-beta.2"' /etc/unraid-version || fail 'Requires exactly Unraid 7.4.0-beta.2'
[[ $(uname -r) == 6.18.47-Unraid ]] || fail 'Requires exactly kernel 6.18.47-Unraid'
config=/usr/src/linux-6.18.47-Unraid/config
[[ -f $config && ! -L $config ]] || fail 'Missing regular stock kernel configuration'
hash=$(sha256sum "$config")
[[ ${hash%% *} == "$(jq -er .config_sha256 "$pins")" ]] || fail 'Stock configuration mismatch'
case "$(dmidecode --string system-product-name)" in
  DX4600*|DX4700*|DXP2800*|DXP4800*|DXP6800*|DXP8800*) ;;
  *) fail 'Unsupported test model (DXP480T static LEDs are outside this test)' ;;
esac
for path in "$plugins" "$plugins/ugreen-leds-beta2" "$plugins/ugreen-leds-beta2/packages" "$cache" \
  "$plugins/ugreenleds-driver" "$settings"; do
  [[ ! -L $path ]] || fail "Refusing symlink: $path"
done
[[ ! -e $settings || -f $settings ]] || fail 'Settings are not a regular file'
for other in ugreenleds-driver ugreen-leds; do
  [[ ! -e $plugins/$other.plg && ! -L $plugins/$other.plg ]] || fail "Disable $other.plg and reboot before testing"
done
for module in i2c-i801 i2c-dev ledtrig-netdev ledtrig-oneshot; do
  modinfo -k 6.18.47-Unraid "$module" >/dev/null || fail "Missing stock module: $module"
done
echo 'EXPERIMENTAL beta2 LED plugin: network safety and physical LEDs are NOT verified.'
echo 'Use only a spare NAS with local console access. Installing this plugin opts into hardware testing.'
[[ $1 == install ]] || exit 0
mkdir /run/ugreen-leds-install.lock || fail 'Another LED installation is active'
stage=''
trap 'if [[ -n $stage ]]; then rm -rf -- "$stage"; fi; rmdir /run/ugreen-leds-install.lock' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
rows=$(jq -er '.packages[] | [.name, .sha256, (.size|tostring)] | @tsv' "$pins")
while IFS=$'\t' read -r asset expected size; do
  name=${asset#unraid-7.4.0-beta.2-r1--}
  package="$cache/$name"
  [[ -f $package && ! -L $package ]] || fail "Missing regular package: $name"
  [[ $(wc -c < "$package") -eq $size ]] || fail "Package size mismatch: $name"
  hash=$(sha256sum "$package")
  [[ ${hash%% *} == "$expected" ]] || fail "Package checksum mismatch: $name"
done <<< "$rows"
if [[ -d /sys/module/led_ugreen ]] || pgrep -f '^(/bin/)?bash /usr/bin/ugreen-leds|^/usr/bin/ugreen-leds' >/dev/null; then
  echo 'Test packages cached. Reboot required; the active driver and monitor were not changed.'
  exit 0
else
  [[ $? == 1 ]] || fail 'Cannot determine whether the monitor is running'
fi
stage=$(mktemp -d /tmp/ugreen-beta2-install.XXXXXXXX)
while IFS=$'\t' read -r asset expected _size; do
  name=${asset#unraid-7.4.0-beta.2-r1--}
  cp -- "$cache/$name" "$stage/$name"
  hash=$(sha256sum "$stage/$name")
  [[ ${hash%% *} == "$expected" ]] || fail "Staged package mismatch: $name"
done <<< "$rows"
while IFS=$'\t' read -r asset _hash _size; do
  name=${asset#unraid-7.4.0-beta.2-r1--}
  upgradepkg --install-new --reinstall "$stage/$name"
  [[ -f /var/lib/pkgtools/packages/${name%.txz} ]] || fail "Missing package record: $name"
  bash "$tools/verify-installed-payload.sh" "$stage/$name" / "$stage"
done <<< "$rows"
depmod -a 6.18.47-Unraid
if [[ ! -e $settings ]]; then
  mkdir -p -- "${settings%/*}"
  (set -o noclobber; cat "$tools/settings.cfg.example" > "$settings")
fi
printf '/usr/bin/ugreen-leds\n' | at now -M
echo 'TEST monitor startup submitted. Check network access, syslog, and physical LEDs now.'
echo 'Remove ugreen-leds-beta2 in Plugin Manager and reboot to stop the test. Settings and cache are retained.'
