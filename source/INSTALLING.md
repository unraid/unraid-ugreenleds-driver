# Replacement installer: rollout hold

`ugreen-leds.plg` is the replacement installer under development. Do not deploy
it as a stable replacement yet. No real hardware approval exists, so normal
installation must fail before package or legacy-plugin changes.

The old `ugreenleds-driver.plg` remains unchanged for reference. It is not an
alternate installer for the new releases. Do not use the old beta2 test bundles.

## Installation contract

The generated plugin embeds the reviewed scripts, validator, and original
settings defaults. Each embedded file has a SHA-256 and explicit mode, so a
plugin update replaces stale helpers. There is no download of executable helper
code during installation. Regenerate it after source changes:

```bash
python3 source/generate-plugin.py
python3 source/generate-plugin.py --check
```

The production entrypoint reads the running OS version, kernel, DMI product
name, and stock kernel configuration. It admits only an approved bundle with
matching identity and verified package bytes. A per-install lock serializes
migration and activation. The cache uses its own per-bundle writer lock.

If the legacy boot plugin exists, installation saves it and defers activation
until reboot. A loaded LED module or running monitor also requires reboot.
The installer never unloads a live kernel module or kills the existing monitor.

On a clean boot, the installer stages the verified archives under their original
Slackware package names. It installs i2c-tools, the LED module, and the monitor
in that order, with `--reinstall` to prevent version-sort skips. After each
package, it requires the expected pkgtools record and compares installed files
and symlink targets with the approved archive. It then updates module dependencies, creates settings only if
absent, and submits monitor startup through `at`. Startup submission is not
proof of physical LED operation or network safety.

A package or dependency failure stops before startup. Package installation is
not a filesystem transaction. Partial runtime changes can remain after failure.
Inspect the error and reboot before retrying or recovering. The immutable cache
and original settings remain available. No automatic legacy fallback occurs.

## Offline OS upgrades

Before an offline upgrade, obtain the target's stock kernel configuration from
its official installer. Prefetch the exact approved OS/kernel bundle:

```text
bash /usr/local/emhttp/plugins/ugreen-leds/ugreen-plugin.sh prefetch OS KERNEL EXTRACTED_STOCK_CONFIG
```

Replace all three arguments with verified target inputs. Prefetch does not
install packages or change the running driver. It refuses an unapproved target.
The shared legacy update helper is not modified or used. Automatic integration
with Unraid's OS-update prefetch lifecycle is not implemented yet. The plugin
manager's download-only mode skips Run commands and cannot populate this cache.

## Recovery and removal

To restore a saved legacy boot file, use the explicit recovery command:

```bash
bash /usr/local/emhttp/plugins/ugreen-leds/ugreen-plugin.sh restore-legacy
```

This disables the replacement boot file before restoring the old one. It does
not replace running packages. Restore a compatible, previously working OS and
retained legacy packages before rebooting. The original plugin is capped at
7.3.2. Its reported beta2 networking failure remains unresolved.

Plugin Manager removal disables future boot installation. Running modules and
the monitor remain until reboot. Settings, approved caches, and legacy backups
are retained for recovery. Removal does not restore the old plugin implicitly.

## Verification limits

Tests run actual admission, hashing, staging, and migration against isolated
directories. They replace package installation, dependency generation, process
inspection, and `at` with recorded effects. They prove order, rejection,
preservation, reboot deferral, and no startup after package failure. They also
cover a zero exit status with missing package records or corrupt installed bytes.

The shipped beta2 `upgradepkg` was inspected in full. A dry run with a legacy
`2026.09.05` monitor record reproduced the version-sort skip for the new
`7.4.0_beta.2_r1` package. The same dry run with `--reinstall` selected the
upgrade. Its exit status alone does not reliably report all install failures,
which is why the installer checks actual package records and payload bytes.

XML tests check embedded-source identity, helper hashes, shell syntax, and the
boot command. The current webgui Plugin Manager source was inspected for INLINE,
SHA256, Mode, and Run behavior. Full installation through the shipped target
Plugin Manager, real package replacement, boot/update prefetch integration,
physical activation, reboot, and rollback still need verification.
