# Experimental beta2 plugin

`ugreen-leds-beta2.plg` is an installable test plugin for exactly Unraid
`7.4.0-beta.2` and kernel `6.18.47-Unraid`. It uses the published beta2 candidate
packages, not the historical GCC 14.2 bundles. It does not need or create a
stable hardware-approval receipt. The stable installer remains unchanged.

**CAUTION: Installation starts LED monitoring. Network safety is not verified.**
Use a spare supported UGREEN NAS with local console access, backed-up flash
configuration, and no important running workloads. Do not test through SSH alone.
The reported networking failure is not diagnosed or proven fixed.

## Install

1. Back up the flash configuration and existing LED settings.
2. Disable the legacy `ugreenleds-driver.plg` and replacement `ugreen-leds.plg`, if present.
   Move their boot files outside `/boot/config/plugins/`. Do not delete settings.
3. Disable custom LED startup commands, then reboot into beta2.
4. Review the existing settings and disk mapping before installation.
5. In **Plugins → Install Plugin**, paste the test plugin URL:

```text
https://github.com/unraid/unraid-ugreenleds-driver/releases/download/6.18.47-Unraid/ugreen-leds-beta2.plg
```

6. Check network access, syslog, disk LEDs, and LAN activity immediately.

The installer supports DX4600, DX4700, DXP2800, DXP4800, DXP6800, and DXP8800
families. DXP480T's separate static-only path and GT/iDX models are outside this
test. Each physical model still needs its own test evidence.

The plugin verifies the exact OS, kernel, stock configuration, model, and three
package hashes before activation. It preserves existing settings and creates
defaults only when absent. It installs the source-built LED module, source-built
i2c-tools, and original disk/network monitor. No stock NIC or I2C module is replaced.

Installing the test plugin enables its boot installation on subsequent beta2
boots. Verified packages remain cached on the flash drive for offline boot.
If the module or monitor is already running, installation defers changes until
reboot. It does not unload a live module or kill the monitor.

## Recover

Remove **ugreen-leds-beta2** in Plugin Manager, then reboot. If the WebGUI is
unreachable, use the local console to move
`/boot/config/plugins/ugreen-leds-beta2.plg` outside `/boot/config/plugins/`
before rebooting. Do not unload network or I2C drivers to recover access.

Removal retains settings and cached packages. The active module and monitor
remain until reboot. Restore a known-compatible OS before restoring the legacy
plugin. Do not restore the original plugin on beta2 as a recovery shortcut.

If package installation fails, partial runtime changes can remain. Stop and
reboot before retrying. A package failure prevents monitor startup but does not
roll back every changed runtime file.

Remove this test plugin and reboot before installing the stable replacement
or changing Unraid versions. It has no automatic update URL or OS-update hook.
Wrong-target installation fails; it never selects a different kernel package.

## Evidence and limits

Source pins are in `beta2-test-packages.json`. The plugin generator embeds all
helpers with SHA-256 hashes and uses fixed package URLs and hashes. The package
selection is immutable for this test. A new test revision needs a new artifact,
not overwritten release bytes.

Automated checks exercise generated XML, hashes, shell syntax, and installation
through the shipped beta2 Plugin Manager in a disposable runtime. Identity,
process inspection, and monitor submission are simulated at the OS boundary.
No physical module is loaded in those tests. Hardware behavior, real reboot,
network continuity, and recovery on a NAS remain unverified.

Use [the hardware checklist](FIRST-HARDWARE-TEST.md) for observations, not its
manual package-install commands. Report the exact model, package identity,
network configuration, LED behavior, and recovery results. Redact private data.
Passing this test does not automatically approve stable installation or other models.
