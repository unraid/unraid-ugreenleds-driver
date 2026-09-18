#!/bin/bash
set -euo pipefail
# Fixed production paths. Never infer target identity from the candidate.
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
[[ $EUID == 0 && $(uname -m) == x86_64 ]] || { echo 'Requires root on x86-64 Unraid' >&2; exit 1; }
entry_tools=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=source/install-approved-bundle.sh
source "$entry_tools/install-approved-bundle.sh"
case ${1:-install} in
  install)
    [[ $# -le 1 ]] || { echo 'install takes no arguments' >&2; exit 1; }
    ;;
  prefetch)
    [[ $# == 4 ]] || { echo 'Usage: prefetch OS KERNEL EXTRACTED_STOCK_CONFIG' >&2; exit 1; }
    model=$(dmidecode --string system-product-name)
    bash "$entry_tools/cache-install-bundle.sh" /boot/config/plugins/ugreen-leds/packages "$2" "$3" "$4" "$model"
    exit 0
    ;;
  prefetch-boot)
    [[ $# == 1 ]] || exit 1
    model=$(dmidecode --string system-product-name)
    bash "$entry_tools/prefetch-boot-bundle.sh" /boot /boot/config/plugins/ugreen-leds/packages "$model"
    exit 0
    ;;
  restore-legacy)
    [[ $# == 1 ]] || exit 1
    mkdir /run/ugreen-leds-install.lock || { echo 'UGREEN installation is locked' >&2; exit 1; }
    trap 'rmdir /run/ugreen-leds-install.lock' EXIT
    # shellcheck source=source/plugin-migration.sh
    source "$entry_tools/plugin-migration.sh"
    ugreen_restore_legacy /boot/config/plugins
    echo 'Boot-file recovery only. Restore a compatible OS before rebooting with the legacy driver.'
    exit 0
    ;;
  *) echo 'Supported commands: install, prefetch, prefetch-boot, restore-legacy' >&2; exit 1 ;;
esac
version=$(sed -n 's/^version="\([^"]*\)"$/\1/p' /etc/unraid-version)
kernel=$(uname -r)
model=$(dmidecode --string system-product-name)
config="/usr/src/linux-$kernel/config"
bundle=$(bash "$entry_tools/cache-install-bundle.sh" /boot/config/plugins/ugreen-leds/packages \
  "$version" "$kernel" "$config" "$model")
ugreen_install_approved / "$bundle" "$version" "$kernel" "$config" "$model"
