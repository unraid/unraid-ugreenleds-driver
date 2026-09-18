#!/bin/bash
# Resolve the already staged OS, never the running uname/configuration.
set -euo pipefail
[[ $# == 3 ]] || { echo 'Usage: prefetch-boot-bundle.sh BOOT CACHE MODEL' >&2; exit 1; }
boot=$1 cache=$2 model=$3
[[ -d $boot && ! -L $boot ]]
for name in changes.txt bzmodules bzmodules.sha256; do
  [[ -f $boot/$name && ! -L $boot/$name ]] || { echo "Missing regular target file: $name" >&2; exit 1; }
done
version=$(sed -n '1s/^# Version \([^ ]*\) .*/\1/p' "$boot/changes.txt")
[[ $version =~ ^7\.[0-9]+\.[0-9]+(-(beta|rc)\.[0-9]+)?$ ]] || { echo 'Cannot identify staged OS version' >&2; exit 1; }
# The first version section owns this target; older changelog sections cannot
# supply a kernel when its own section lacks one.
kernel=$(awk 'NR>1 && /^# Version / {exit} /^\* version [0-9]+\.[0-9]+\.[0-9]+-Unraid$/ {print $3}' "$boot/changes.txt")
[[ $kernel =~ ^[0-9]+\.[0-9]+\.[0-9]+-Unraid$ ]] || { echo 'Cannot identify one staged kernel' >&2; exit 1; }
expected=$(cat "$boot/bzmodules.sha256")
[[ $expected =~ ^[0-9a-f]{64}$ ]] || { echo 'Invalid staged bzmodules checksum' >&2; exit 1; }
actual=$(sha256sum -- "$boot/bzmodules")
[[ ${actual%% *} == "$expected" ]] || { echo 'Staged bzmodules checksum mismatch' >&2; exit 1; }
work=$(mktemp -d /tmp/ugreen-prefetch.XXXXXXXX)
cleanup() {
  if mountpoint -q "$work/usr"; then
    umount -- "$work/usr" || { echo "Cannot unmount prefetch image at $work/usr; retained for inspection" >&2; return 1; }
  fi
  rm -rf -- "$work"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir "$work/usr"
mount -t squashfs -o loop,ro,nodev,nosuid,noexec "$boot/bzmodules" "$work/usr"
cp -- "$work/usr/src/linux-$kernel/config" "$work/config"
[[ -s $work/config ]]
umount -- "$work/usr"
tools=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bash "$tools/cache-install-bundle.sh" "$cache" "$version" "$kernel" "$work/config" "$model"
printf 'UGREEN approved bundle ready for staged OS %s, kernel %s.\n' "$version" "$kernel"
