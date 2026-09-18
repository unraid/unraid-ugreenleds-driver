#!/bin/bash
# Hosted Linux CI only, inside a private mount namespace. No NAS configuration,
# hardware devices, driver loading, or approval publication is performed.
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && $EUID == 0 && $(uname -s) == Linux && $# == 2 ]]
inputs=$1 assets=$2
mapfile -t receipts < <(find "$assets" -maxdepth 1 -name 'unraid-*-r1.json')
[[ ${#receipts[@]} == 1 ]]
receipt=${receipts[0]}
version=$(jq -er '.unraid' "$receipt")
kernel=$(jq -er '.kernel' "$receipt")
[[ $version =~ ^7\.[0-9]+\.[0-9]+(-(beta|rc)\.[0-9]+)?$ ]]
[[ $kernel =~ ^[0-9]+\.[0-9]+\.[0-9]+-Unraid$ ]]
work=$(mktemp -d /tmp/ugreen-prefetch-host.XXXXXXXX)
cleanup() {
  if mountpoint -q "$work/probe"; then
    umount -- "$work/probe" || { echo "Retained mounted proof directory: $work" >&2; return 1; }
  fi
  rm -rf -- "$work"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$work/boot" "$work/probe"
cp --reflink=auto "$inputs/bzmodules" "$work/boot/bzmodules"
sha256sum "$work/boot/bzmodules" | cut -d ' ' -f1 > "$work/boot/bzmodules.sha256"
printf '# Version %s 2026-09-18\n\n## Linux kernel\n\n* version %s\n' "$version" "$kernel" > "$work/boot/changes.txt"
cache="$work/cache/$kernel/$version-r1"
mkdir -p "$cache"
cp "$assets/"* "$cache/"
hash=$(sha256sum "$receipt")
jq -n --arg unraid "$version" --arg kernel "$kernel" --arg hash "${hash%% *}" \
  '{schema:1,recipe:1,status:"approved",unraid:$unraid,kernel:$kernel,manifest_sha256:$hash,
    system_product_names:["TEST-ONLY-NOT-HARDWARE"],TEST_ONLY:"Private CI fixture, never publish"}' \
  > "$cache/approved-unraid-$version-r1.json"

# Prove kernel support and actual mount flags, then exercise the production
# prefetch script with real mount/umount and byte-identical target inputs.
mount -t squashfs -o loop,ro,nodev,nosuid,noexec "$work/boot/bzmodules" "$work/probe"
options=$(findmnt -n -o OPTIONS --target "$work/probe")
device=$(findmnt -n -o SOURCE --target "$work/probe")
[[ $device =~ ^/dev/loop[0-9]+$ ]]
for option in ro nodev nosuid noexec; do
  [[ ,$options, == *,"$option",* ]] || { echo "Missing mount option: $option" >&2; exit 1; }
done
cmp "$work/probe/src/linux-$kernel/config" "$assets/unraid-$version-r1--stock.config"
umount -- "$work/probe"
before=$(findmnt -rn -o TARGET | sort)
tools=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
bash "$tools/prefetch-boot-bundle.sh" "$work/boot" "$work/cache" TEST-ONLY-NOT-HARDWARE
after=$(findmnt -rn -o TARGET | sort)
[[ $before == "$after" ]] || { echo 'Prefetch leaked a mount' >&2; exit 1; }
printf '%s\n' 'PASS: actual SquashFS loop mount enforces ro,nodev,nosuid,noexec and matches the stock config.' \
  'PASS: production prefetch uses real mounts, verifies its cached fixture bundle, and leaves no mount behind.' \
  'LIMIT: hosted Linux kernel, not physical UGREEN hardware. Synthetic approval remains private and is removed.'
