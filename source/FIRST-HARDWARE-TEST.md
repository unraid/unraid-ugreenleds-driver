# First hardware test: Unraid 7.4.0-beta.2

This procedure tests the published candidate manually on a spare NAS. It does
not install the replacement `.plg`, enable boot startup, or grant stable approval.
It does not prove automatic migration or upgrade behavior.

**CAUTION: The reported network failure is not diagnosed or proven fixed.**
Use local console access and recoverable boot media. Do not perform the first
activation through SSH alone or on a server with important running workloads.

The target is exactly Unraid `7.4.0-beta.2`, kernel `6.18.47-Unraid`, x86-64.
The activity-monitor families in scope are DX4600, DX4700, DXP2800, DXP4800,
DXP6800, and DXP8800. Do not use this procedure on GT or iDX models.
DXP480T has a separate static-LED path and is outside this module test.

## Prepare the test

1. Back up the flash configuration, LED settings, and known-working recovery packages.
2. Disable both old and replacement LED plugin boot files, if present.
   Move them outside `/boot/config/plugins/`; preserve the settings directory.
3. Disable custom LED startup commands in `go`, cron, or other launchers.
4. Reboot into the exact target OS with the array stopped.
5. Copy all beta2 candidate assets into a new temporary directory on the NAS.
6. Copy `verify-installed-payload.sh` and `settings.cfg.example` from this reviewed repository's `source` directory into that directory.
7. Open a root Bash shell at the local console and enter that directory.

Use the assets from the
[6.18.47-Unraid kernel release](https://github.com/unraid/unraid-ugreenleds-driver/releases/tag/6.18.47-Unraid)
with prefix `unraid-7.4.0-beta.2-r1--`, plus `unraid-7.4.0-beta.2-r1.json`.
Do not mix OS versions or use the rejected historical `1test`/`2test` packages.
The maintainer must supply reviewed helper files and record their repository
commit. The helpers are repository inputs, not release assets.

## Preflight

Any failed command must stop the test before installation:

```bash
set -euo pipefail
test "$(id -u)" = 0
test "$(uname -m)" = x86_64
test "$(uname -r)" = 6.18.47-Unraid
grep -qx 'version="7.4.0-beta.2"' /etc/unraid-version
test ! -e /boot/config/plugins/ugreenleds-driver.plg
test ! -e /boot/config/plugins/ugreen-leds.plg
test ! -d /sys/module/led_ugreen
test ! -e /var/run/ugreen-leds.lock
test ! -e /usr/bin/ugreen-leds
if modinfo led-ugreen >/dev/null 2>&1; then
  echo 'An existing LED driver is installed. Stop and resolve the conflict.'
  exit 1
fi
for module in i2c-i801 i2c-dev ledtrig-netdev ledtrig-oneshot; do
  modinfo "$module" >/dev/null
done
receipt=unraid-7.4.0-beta.2-r1.json
printf '%s  %s\n' \
  f829c033d9ac6c2c8401596a8f8177478ce30a7efa479d5aa6307e813fffb045 \
  "$receipt" | sha256sum -c -
jq -er '.assets[] | "\(.sha256)  \(.name)"' "$receipt" | sha256sum -c -
cmp /usr/src/linux-6.18.47-Unraid/config \
  unraid-7.4.0-beta.2-r1--stock.config
case "$(dmidecode --string system-product-name)" in
  DX4600*|DX4700*|DXP2800*|DXP4800*|DXP6800*|DXP8800*) ;;
  *) echo 'Model outside this test scope'; exit 1 ;;
esac
dmidecode --string system-product-name
ip -br link
ip route
```

Retain the model and network output as the baseline. From another device,
confirm normal WebGUI and network access. Keep diagnostics private until serial
numbers, addresses, credentials, and unrelated data are redacted.

## Install without activation

These packages have no boot launcher. Installation does not start the monitor
or load the module. Strip the release prefix so Slackware records the correct
package identities. Reinstall all three packages to test the exact bundle.

Continue in the same Bash shell:

```bash
stage=$(mktemp -d /tmp/ugreen-hardware-test.XXXXXXXX)
prefix=unraid-7.4.0-beta.2-r1--
for role in i2c_tools kernel monitor; do
  asset=$(jq -er --arg role "$role" '.packages[$role]' "$receipt")
  canonical=${asset#"$prefix"}
  test "$canonical" != "$asset"
  cp -- "$asset" "$stage/$canonical"
  cmp -- "$asset" "$stage/$canonical"
  upgradepkg --install-new --reinstall "$stage/$canonical"
  test -f "/var/lib/pkgtools/packages/${canonical%.txz}"
  bash ./verify-installed-payload.sh "$stage/$canonical" / "$stage"
done
depmod -a 6.18.47-Unraid
test "$(modinfo -F vermagic led-ugreen | cut -d ' ' -f1)" = 6.18.47-Unraid
for tool in i2cdetect i2cdump i2cget i2cset i2ctransfer; do
  "$tool" -V
done
ip -br link
ip route
```

Confirm every tool reports version 4.3 and networking still matches the baseline.
If installation fails partway through, stop and reboot before retrying.
Do not add these commands to any startup mechanism.

## Activate once

The monitor sources settings as root. Review existing settings before use.
Preserve disk mappings; do not replace them with defaults.
For a new installation only:

```bash
if [ ! -e /boot/config/plugins/ugreenleds-driver/settings.cfg ]; then
  install -Dm600 settings.cfg.example /boot/config/plugins/ugreenleds-driver/settings.cfg
fi
```

Confirm the disk mapping and network interface before activation.
From the local console, start the monitor in the foreground:

```bash
bash /usr/bin/ugreen-leds
```

**This is the hardware-risk boundary.** The monitor loads the module, creates
the I2C device, and configures disk and network LED monitoring.

From another console, inspect `ip -br link`, `ip route`, and `dmesg` immediately.
From another device, confirm WebGUI access and normal connectivity.
Stop at the first network regression, kernel warning, or incorrect LED behavior.

On a spare test array, confirm each disk LED matches its bay during ordinary
read activity. Confirm LAN activity LEDs while transferring disposable data.
Record the interface, bridge/bond configuration, settings, steps, and observations.
Do not run raw-disk writes or I2C bus scans as part of this test.

## Recover and report

1. Press Ctrl+C to stop the foreground monitor.
2. Reboot for a clean runtime rollback; do not unload network or I2C bus drivers.
3. Confirm the candidate module and monitor are absent after reboot.
4. Confirm normal network access and unchanged persistent LED settings.
5. Record the first failing step, or the completed checks, with the receipt hash.

Stopping the monitor does not remove its module, I2C device, or triggers.
With boot launchers disabled, runtime packages disappear after reboot.
The settings and saved boot files remain. Do not restore the original plugin
on beta2. Restore a known-compatible OS before restoring legacy boot startup.

A passing manual test does **not** approve the replacement installer. Automatic
new installation, legacy migration, settings preservation, reboot activation,
and working legacy rollback still require their own physical validation.
See [the installation contract](INSTALLING.md) and
[the complete approval requirements](APPROVAL.md). Do not invent passing results
or publish a synthetic approval to bypass the installer gate.
