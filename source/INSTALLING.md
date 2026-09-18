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
The shared legacy update helper is not modified or used. The replacement adds
its own executable Plugin Manager post-hook for successful OS installation,
update, and removal operations. The hook reads the staged `/boot/changes.txt`,
verifies `/boot/bzmodules.sha256`, and reads that kernel's stock configuration
through a temporary SquashFS mount with `loop,ro,nodev,nosuid,noexec` options.
It unmounts before any package download. Cleanup must unmount successfully
before deleting temporary files. A failed unmount retains the mount for inspection.
Stock Unraid does not provide `unsquashfs`, so prefetch does not depend on it.
The hook verifies target identity
before requesting the approved bundle. It does not use the running kernel or
the configuration of the current OS. Other plugin events and failed OS
operations do not trigger prefetch.

The hook reports failure in command output, syslog, and an Unraid warning
notification. The OS update is already staged, and Plugin Manager does not
use post-hook status to undo it. Keep the current boot running until prefetch
succeeds, or expect LED startup to fail after reboot. The installer will not
load a mismatched or unapproved driver. A failed boot install can move the
replacement `.plg` to Plugin Manager's error directory, requiring reinstallation
after the missing target is approved.

Plugin Manager's download-only mode skips hooks and Run commands. The explicit
prefetch command remains necessary for that path and for manual boot-media
replacement. Successful normal OS update/remove operations use the post-hook.

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
SHA256, Mode, and Run behavior.

`tests/prove-target-install.sh` also passed against the shipped beta2 runtime
assembled from `bzroot` and the `bzmodules` /usr image. It uses the real Plugin
Manager, package tools, dependency generator, libraries, and published packages.
It proves missing-approval rejection, new installation, boot registration,
migration deferral, repeat package replacement, removal, retained custom settings,
and explicit legacy boot-file restoration.

That proof substitutes hardware identity, process lookup, `at` submission, and
the read-only mount operation used by prefetch.
It creates a clearly marked synthetic approval only inside a disposable chroot.
No fixture approval is published or copied to candidate assets. The container
has no network or host device/proc/sys mounts, and modprobe is a refusing test
double. This is not evidence of physical activation, a real reboot, or working
legacy rollback on a NAS. The installed post-hook verifies a real staged
bzmodules checksum and cached test bundle, with configuration reads supplied by
the mount test double. Actual loop mounting, full interactive OS upgrade, and
failure-notification delivery still require verification.

The candidate workflow runs this proof before artifact upload. To rerun checks
for an already published version, select an exact version with `rebuild=true`
and `publish=false`. Rebuild mode cannot publish or replace existing assets.
