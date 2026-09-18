#!/bin/bash
# Fixed beta2 CI entrypoint. /inputs and /runtime are authenticated read-only mounts.
set -euo pipefail
umask 022

[[ $(uname -m) == x86_64 && $EUID == 0 ]]
[[ $(gcc -dumpfullversion) == 14.2.0 ]]
grep -qx 'version="7.4.0-beta.2"' /runtime/etc/unraid-version
kernel_release=6.18.47-Unraid
driver_version=20260918.992fc6d
# Never put this working directory on the host export mount.
work=$(mktemp -d /tmp/ugreen-beta2.XXXXXXXX)
mkdir -p "$work/kernel" "$work/controller" "$work/check" "$work/packages"
tar -xJf /inputs/linux.tar.xz -C "$work/kernel"
tar -xzf /inputs/controller.tar.gz --strip-components=1 -C "$work/controller"
(
  cd "$work/kernel"
  printf '%s\n' \
    'b1401c127661486bd31b2ddcf964acc4481e5d12ac5abd95fd193bb8dc3a0790  .config' \
    '49a87df4efcac3a0d4fe5d14ea42550b9e297d080830618784cf85a99d6265d1  Module.symvers' | sha256sum -c -
)
grep -qx 'CONFIG_CC_VERSION_TEXT="gcc (GCC) 14.2.0"' "$work/kernel/.config"
cp -a /runtime/lib "$work/check/"
for module in i2c-core led-class i2c-dev i2c-i801 ledtrig-netdev ledtrig-oneshot; do
  modinfo -b "$work/check" -k "$kernel_release" "$module" >/dev/null
done

KDIR="$work/kernel" KERNEL_RELEASE="$kernel_release" \
  DRIVER_SRC="$work/controller" DRIVER_VERSION="$driver_version" \
  BUILD=2test JOBS=4 OUTPUT="$work/packages" \
  bash /repo/source/ugreen-driver.SlackBuild | tee "$work/build.log"

package="ugreen_leds-${driver_version}_6.18.47_Unraid-x86_64-2test.txz"
mkdir "$work/unpacked"
tar -xJf "$work/packages/$package" -C "$work/unpacked"
module="$work/unpacked/lib/modules/$kernel_release/extra/led-ugreen.ko.xz"
[[ $(modinfo -F vermagic "$module") == "$(modinfo -b "$work/check" -k "$kernel_release" -F vermagic i2c-core)" ]]
[[ $(modinfo -F vermagic "$module") == "$(modinfo -b "$work/check" -k "$kernel_release" -F vermagic led-class)" ]]
[[ $(modinfo -F depends "$module") == i2c-core,led-class ]]
xz -dc "$module" > "$work/module.ko"
file "$work/module.ko" | grep -F 'ELF 64-bit LSB relocatable, x86-64'
cp -a "$work/unpacked/lib/." "$work/check/lib/"
depmod -e -E "$work/kernel/Module.symvers" -b "$work/check" "$kernel_release" > "$work/depmod.log" 2>&1
if [[ -s $work/depmod.log ]]; then
  cat "$work/depmod.log" >&2
  exit 1
fi

tar --numeric-owner -tvJf "$work/packages/$package" > "$work/package-contents.txt"
awk '
  $2 != "0/0" { bad = 1 }
  $1 != "drwxr-xr-x" && $1 != "-rw-r--r--" { bad = 1 }
  END { exit bad }
' "$work/package-contents.txt"

{
  printf 'kernel=%s\nsource_commit=992fc6dcb5da4cfc9aa25561eff2f584c06f586d\n' "$kernel_release"
  printf 'builder=%s\nrepository_commit=%s\nactions_run=%s\n' "$BUILDER" "$GITHUB_SHA" "$GITHUB_RUN_ID"
  gcc --version
  modinfo "$module"
  printf '\n%s\n' \
    'PASS: pinned build config and Module.symvers, exact GCC, stock module vermagic and dependencies.' \
    'PASS: depmod reported no unresolved symbols or other diagnostics.' \
    'PASS: archive UID/GID 0/0, directories 0755, files 0644.' \
    'This ELF kernel module has no userspace/glibc library dependency.' \
    'No monitor, i2c-tools, NIC, stock I2C, or LED trigger modules are included.' \
    'LIMIT: prepared config disables IKCONFIG and MODVERSIONS. No embedded-config or symbol-CRC proof is claimed.' \
    'Prepared kernel inputs still come from ich777. This is not a fully independent kernel toolchain.' \
    'Hardware, network behavior, and runtime ABI safety are not proven by these static checks.'
} > "$work/compatibility.txt"

# Only finalized, validated files cross to the host filesystem.
cp "$work/packages/$package" "$work/build.log" "$work/compatibility.txt" "$work/package-contents.txt" /export/
cp /inputs/controller.tar.gz /export/controller-source.tar.gz
cp /repo/source/ugreen-driver.SlackBuild /repo/source/build-beta2-in-container.sh /export/
(cd /export; sha256sum "$package" > "$package.sha256")
(cd /export; sha256sum "$package" build.log compatibility.txt package-contents.txt controller-source.tar.gz ugreen-driver.SlackBuild build-beta2-in-container.sh > SHA256SUMS)
