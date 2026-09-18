#!/bin/bash
# Caller authenticates /inputs/{bzroot,bzmodules,linux.tar.xz,controller.tar.gz,i2c-tools.tar.xz}.
# Mount /inputs and /repo read-only, /export writable, and disable networking.
set -euo pipefail
umask 022

: "${UNRAID_VERSION:?}" "${KERNEL_RELEASE:?}" "${DRIVER_VERSION:?}" "${PLUGIN_VERSION:?}" "${BUILD:?}"
[[ $UNRAID_VERSION =~ ^7\.[0-9]+\.[0-9]+(-(beta|rc)\.[0-9]+)?$ ]]
[[ $KERNEL_RELEASE =~ ^[0-9]+\.[0-9]+\.[0-9]+-Unraid$ ]]
[[ $(uname -m) == x86_64 && $EUID == 0 ]]
[[ -d /export && -z $(find /export -mindepth 1 -maxdepth 1 -print -quit) ]]
work=$(mktemp -d /tmp/ugreen-build.XXXXXXXX)
exec > >(tee "$work/build.log") 2>&1
printf 'Native build staging: %s\n' "$work"
mkdir -p "$work/kernel" "$work/controller" "$work/packages" "$work/unpacked"
unmkinitramfs /inputs/bzroot "$work/initramfs"
mapfile -t versions < <(find "$work/initramfs" -path '*/etc/unraid-version' -type f)
[[ ${#versions[@]} == 1 ]]
runtime=${versions[0]%/etc/unraid-version}
grep -qx "version=\"$UNRAID_VERSION\"" "${versions[0]}"
mapfile -t kernels < <(find "$runtime/lib/modules" -mindepth 1 -maxdepth 1 -type d -printf '%f\n')
[[ ${#kernels[@]} == 1 && ${kernels[0]} == "$KERNEL_RELEASE" ]]
unsquashfs -cat /inputs/bzmodules "src/linux-$KERNEL_RELEASE/config" > "$work/stock.config"
unsquashfs -cat /inputs/bzmodules "src/linux-$KERNEL_RELEASE/System.map" > "$work/System.map"
[[ -s $work/stock.config && -s $work/System.map ]]

tar -xJf /inputs/linux.tar.xz -C "$work/kernel"
tar -xzf /inputs/controller.tar.gz --strip-components=1 -C "$work/controller"
bash /repo/source/prepare-kernel.sh "$work/kernel" "$work/stock.config" "$KERNEL_RELEASE"

# Use the target's Slackware packager; staging and ownership remain Linux-native.
install -m755 "$runtime/sbin/makepkg" /usr/local/bin/makepkg
for module in i2c-core led-class i2c-dev i2c-i801 ledtrig-netdev ledtrig-oneshot input-leds; do
  modinfo -b "$runtime" -k "$KERNEL_RELEASE" "$module" >/dev/null
done
KDIR="$work/kernel" DRIVER_SRC="$work/controller" OUTPUT="$work/packages" JOBS=4 \
  bash /repo/source/ugreen-driver.SlackBuild
package="ugreen_leds-${DRIVER_VERSION}_${KERNEL_RELEASE//-/_}-x86_64-${BUILD}.txz"
tar -xJf "$work/packages/$package" -C "$work/unpacked"
module="$work/unpacked/lib/modules/$KERNEL_RELEASE/extra/led-ugreen.ko.xz"
for dependency in i2c-core led-class; do
  [[ $(modinfo -F vermagic "$module") == "$(modinfo -b "$runtime" -k "$KERNEL_RELEASE" -F vermagic "$dependency")" ]]
done
[[ $(modinfo -F depends "$module") == i2c-core,led-class ]]
stock_led=$(modinfo -b "$runtime" -k "$KERNEL_RELEASE" -n input-leds)
python3 /repo/source/verify_led_layout.py "$stock_led" "$module" > "$work/led-layout.json"
cp -a "$work/unpacked/lib/." "$runtime/lib/"
depmod -e -F "$work/System.map" -b "$runtime" "$KERNEL_RELEASE" > "$work/depmod.log" 2>&1
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
mkdir "$work/i2c-source" "$work/userspace"
tar -xJf /inputs/i2c-tools.tar.xz --strip-components=1 -C "$work/i2c-source"
RUNTIME="$runtime" I2C_SRC="$work/i2c-source" \
  MONITOR_SRC=/repo/source/usr/bin/ugreen-leds OUTPUT="$work/userspace" \
  bash /repo/source/ugreen-userspace.SlackBuild
{
  printf 'unraid=%s\nkernel=%s\n' "$UNRAID_VERSION" "$KERNEL_RELEASE"
  gcc --version
  as --version
  ld --version
  modinfo "$module"
  printf '\n%s\n' \
    'PASS: regenerated configuration matches stock except documented non-runtime tool probes.' \
    'PASS: stock LED class boundary, exact vermagic, stock System.map dependency checks.' \
    'PASS: root ownership, directories 0755, files 0644.' \
    'Kernel archive contains only the external module. No replacement stock modules.' \
    'Separate monitor and i2c-tools packages passed target loader and Bash syntax checks.' \
    'LIMIT: prepared source and Module.symvers still come from ich777.' \
    'LIMIT: no hardware execution or complete runtime ABI proof.'
} > "$work/compatibility.txt"
# Publication is outside the compiler container. Only validated output crosses
# the host mount. Never publish a partial /export from a failed container run.
cp "$work/packages/$package" "$work/compatibility.txt" "$work/package-contents.txt" \
  "$work/led-layout.json" "$work/kernel/config-validation.json" "$work/stock.config" /export/
cp /inputs/controller.tar.gz /export/controller-source.tar.gz
cp /inputs/i2c-tools.tar.xz /export/i2c-tools-source.tar.xz
cp "$work/userspace/"* /export/
cp /repo/source/ugreen-driver.SlackBuild /repo/source/build-packages-in-container.sh \
  /repo/source/ugreen-userspace.SlackBuild \
  /repo/source/prepare-kernel.sh /repo/source/verify_kernel_config.py \
  /repo/source/verify_led_layout.py /export/
(
  cd /export
  sha256sum "$package" > "$package.sha256"
  md5sum "$package" | cut -d ' ' -f1 > "$package.md5"
  sha256sum ./* > SHA256SUMS
)
printf 'Validated package: %s\n' "$package"
if [[ -n ${EXPORT_UID:-} && -n ${EXPORT_GID:-} ]]; then
  [[ $EXPORT_UID =~ ^[0-9]+$ && $EXPORT_GID =~ ^[0-9]+$ ]]
  # This changes only exported file ownership, never ownership inside packages.
  chown -R "$EXPORT_UID:$EXPORT_GID" /export
fi
