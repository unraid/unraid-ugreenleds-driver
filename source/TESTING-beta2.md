# UGREEN LED candidates for Unraid 7.4.0-beta.2

## Current candidate and rollout hold

The corrected candidate is published under the exact
[6.18.47-Unraid kernel release](https://github.com/unraid/unraid-ugreenleds-driver/releases/tag/6.18.47-Unraid).
Select the assets with the `unraid-7.4.0-beta.2-r1--` prefix and the
`unraid-7.4.0-beta.2-r1.json` receipt. Other Unraid versions can share this
kernel release. Their assets are not interchangeable with the beta2 bundle.

This candidate builds the module with GCC 15.3.0 and binutils 2.46.1.
It also builds i2c-tools 4.3 from pinned source and packages the unchanged
original disk/network monitor. The receipt records package hashes and build
inputs. The workflow checks the packages against the official target runtime.
It does not replace stock network drivers or stock I2C modules.

No physical UGREEN test or hardware approval exists. The reported network
failure remains unresolved. The replacement installer deliberately rejects
unapproved candidates. Do not create an approval receipt to bypass this hold.

See [the replacement installation contract](INSTALLING.md) for installation,
migration, and recovery behavior. See [the hardware approval requirements](APPROVAL.md)
for the evidence required before stable promotion. The commands in the
historical section below do **not** apply to the corrected candidate.
Use [the first hardware test procedure](FIRST-HARDWARE-TEST.md) for the corrected
candidate. That manual test does not approve automatic installation or migration.

## Historical procedure — rejected bundles, do not execute

**HOLD: Do not activate the historical bundles described below.** They used
GCC 14.2.0, while the official beta2 configuration specifies GCC 15.3.0.
The corrected candidate is described above. These
instructions remain as a record of the earlier test procedure, not approval
to load those packages.

This is a manual-start test bundle, not a production `.plg` release. The kernel
module is newly compiled from pinned upstream source. The monitor and i2c-tools
packages are unchanged copies from the original plugin.

**CAUTION: The reported network failure is not diagnosed or fixed by this build.**
Use a spare supported UGREEN NAS with a local console and no important running
workloads. Do not perform the first activation through SSH alone. Compilation
and package checks do not prove that LEDs or networking work on physical hardware.

The intended test scope is the original Intel DX4600, DX4700, DXP2800, DXP4800,
DXP6800, and DXP8800 families. Do not use this test on GT or iDX models. The
original monitor also has a separate static-LED path for DXP480T, which does not
exercise this rebuilt module and is outside this test.

## Contents and provenance

- `ugreen_leds-20260918.992fc6d_6.18.47_Unraid-x86_64-1test.txz`: newly built module.
- `ugreenleds-driver-2026.09.05.txz`: original disk and network monitor.
- `i2c-tools-4.3-x86_64-1.txz`: original dependency, not rebuilt here.
- `controller-source.tar.gz`: complete pinned upstream source, including license notices.
- `ugreen-driver.SlackBuild`: the build script used for this module.
- `settings.cfg.example`: original default settings, for a new installation only.
- `build.log`, `build-provenance.txt`, and `SHA256SUMS`: build evidence and checksums.

The target is exactly Unraid `7.4.0-beta.2`, kernel `6.18.47-Unraid`, x86-64.
Its stock root filesystem includes `i2c-i801`, `i2c-dev`, `ledtrig-netdev`, and
`ledtrig-oneshot`. This bundle does not replace those modules or any network driver.

The build still uses ich777's prepared kernel archive and pinned compiler image.
It does not reuse ich777's compiled `led-ugreen` module. The i2c-tools build recipe
has not been established, so that binary dependency remains an explicit limitation.

## Prepare the test server

1. Back up existing UGREEN plugin settings and the Unraid flash configuration.
2. Disable the original plugin's boot installation, including any custom startup commands.
   Move its `.plg` outside `/boot/config/plugins/` rather than deleting the settings.
3. Reboot, then confirm that the old module and monitor are absent.
4. Copy and extract this bundle into a temporary directory on the test server.
5. Open a root Bash shell at the local console, then enter that directory.

Run these checks before installing anything. A failed check must stop the test.

```bash
test "$(id -u)" = 0 || exit 1
test "$(uname -m)" = x86_64 || exit 1
test "$(uname -r)" = 6.18.47-Unraid || exit 1
grep -qx 'version="7.4.0-beta.2"' /etc/unraid-version || exit 1
sha256sum -c SHA256SUMS || exit 1
test ! -e /boot/config/plugins/ugreenleds-driver.plg || exit 1
test ! -d /sys/module/led_ugreen || exit 1
test ! -e /var/run/ugreen-leds.lock || exit 1
test ! -e /usr/bin/ugreen-leds || exit 1
if modinfo led-ugreen >/dev/null 2>&1; then
  echo 'An existing driver is installed. Stop and resolve the conflict.'
  exit 1
fi
for module in i2c-i801 i2c-dev ledtrig-netdev ledtrig-oneshot; do
  modinfo "$module" >/dev/null || exit 1
done
dmidecode --string system-product-name
ip -br link
ip route
```

Confirm the model before continuing. Retain the network output as the baseline.
Do not share unredacted diagnostics publicly.

## Install without starting

These packages have no boot launcher. The commands do not load the module or
start the monitor. They install into Unraid's runtime filesystem only.

If i2c-tools is already installed, retain it and record its version. Otherwise,
install the supplied dependency:

```bash
if ! command -v i2cdetect >/dev/null && ! command -v i2cset >/dev/null; then
  installpkg ./i2c-tools-4.3-x86_64-1.txz || exit 1
fi
command -v i2cdetect >/dev/null || exit 1
command -v i2cset >/dev/null || exit 1
installpkg ./ugreen_leds-20260918.992fc6d_6.18.47_Unraid-x86_64-1test.txz || exit 1
installpkg ./ugreenleds-driver-2026.09.05.txz || exit 1
depmod -a 6.18.47-Unraid || exit 1
modinfo led-ugreen
ip -br link
```

If installation fails partway through, stop and reboot before another attempt.
Do not add these commands to `go`, cron, or any other startup mechanism.

## Activate once

The original monitor reads a root-owned shell settings file. Review existing
settings before use. Do not replace a tester's disk mapping with the example.
For a new installation only, create the settings file with this command:

```bash
if [ ! -e /boot/config/plugins/ugreenleds-driver/settings.cfg ]; then
  install -Dm600 settings.cfg.example /boot/config/plugins/ugreenleds-driver/settings.cfg
fi
```

This settings file is persistent on the flash drive, but it cannot start the
test by itself. Confirm the disk mapping before activation.

From the local console, start the original monitor in the foreground:

```bash
bash /usr/bin/ugreen-leds
```

This step loads the driver, creates the I2C device, and enables disk and network
LED monitoring. It is the hardware-risk boundary. From another console, inspect
`ip -br link`, `ip route`, and `dmesg` before testing network access and LEDs.
Confirm that each disk LED matches its bay and that LAN activity does not impair
connectivity. Record the exact NAS model, interface/bond/bridge setup, and the
first failing step if the test fails.

## Stop and recover

Press Ctrl+C to stop the foreground monitor. This does not remove the kernel
module, I2C device, or LED triggers. Reboot for a clean rollback. Do not unload
network or I2C bus drivers to recover access.

With the original plugin disabled and no startup commands added, these runtime
packages are absent after reboot. The settings file remains for inspection.
Keep this build experimental until a physical test confirms networking and LED
behavior. A successful rebuild alone is not a network-failure fix.
