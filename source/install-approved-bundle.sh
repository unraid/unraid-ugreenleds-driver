#!/bin/bash
# Library. The production entrypoint supplies / as the runtime root. Tests use
# an isolated filesystem and replace only upgradepkg, depmod, pgrep, and at.

ugreen_install_approved() (
  set -euo pipefail
  # Subshell scope keeps trap state available even on an explicit exit.
  root=$1 bundle=$2 version=$3 kernel=$4 config=$5 model=$6
  stage='' active=0
  install_tools=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
  install_plugins="$root/boot/config/plugins"
  settings="$install_plugins/ugreenleds-driver/settings.cfg"
  [[ -d $root && ! -L $root && -d $install_plugins && ! -L $install_plugins ]] || exit 1
  [[ ! -L $install_plugins/ugreenleds-driver && ! -L $settings ]] || exit 1
  [[ ! -e $settings || -f $settings ]] || exit 1
  lock="$root/run/ugreen-leds-install.lock"
  mkdir -- "$lock" 2>/dev/null || { echo 'UGREEN installation is locked' >&2; exit 1; }
  trap 'if [[ -n $stage ]]; then rm -rf -- "$stage"; fi; rmdir -- "$lock"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  rows=$(bash "$install_tools/verify-install-bundle.sh" "$bundle" "$version" "$kernel" "$config" "$model")
  # shellcheck source=source/plugin-migration.sh
  source "$install_tools/plugin-migration.sh"
  if [[ -d $root/sys/module/led_ugreen ]] || "$root/usr/bin/pgrep" -f '^(/bin/)?bash /usr/bin/ugreen-leds|^/usr/bin/ugreen-leds' >/dev/null; then
    active=1
  else
    # pgrep: 1 means no match. Other errors must not authorize activation.
    [[ $? == 1 ]] || exit 1
  fi
  if [[ -e $install_plugins/ugreenleds-driver.plg || -L $install_plugins/ugreenleds-driver.plg ]]; then
    ugreen_disable_legacy "$install_plugins"
    active=1
  fi
  if [[ $active == 1 ]]; then
    echo 'Approved bundle cached. Reboot required; running packages and modules were not changed.'
    exit 0
  fi
  stage=$(mktemp -d "$root/tmp/ugreen-install.XXXXXXXX")
  # Release filenames carry an OS prefix, but Slackware package identities
  # must retain i2c-tools, ugreen_leds, and ugreenleds-driver for upgradepkg.
  while IFS=$'\t' read -r name hash _size; do
    canonical=${name#unraid-"$version"-r1--}
    cp -- "$bundle/$name" "$stage/$canonical"
    copied=$(sha256sum -- "$stage/$canonical")
    [[ ${copied%% *} == "$hash" ]] || exit 1
  done <<< "$rows"
  while IFS=$'\t' read -r name hash _size; do
    canonical=${name#unraid-"$version"-r1--}
    "$root/sbin/upgradepkg" --install-new --reinstall "$stage/$canonical"
    # Stock upgradepkg can return zero after a skipped/failed installation.
    # Require the expected pkgtools record and actual installed bytes.
    [[ -f $root/var/lib/pkgtools/packages/${canonical%.txz} ]] || {
      echo "Expected installed package record is missing: $canonical" >&2; exit 1;
    }
    bash "$install_tools/verify-installed-payload.sh" "$stage/$canonical" "$root" "$stage"
  done <<< "$rows"
  "$root/sbin/depmod" -a "$kernel"
  if [[ ! -e $settings ]]; then
    mkdir -p -- "${settings%/*}"
    (set -o noclobber; cat "$install_tools/settings.cfg.example" > "$settings")
  fi
  printf '/usr/bin/ugreen-leds\n' | "$root/usr/bin/at" now -M
  echo 'Approved packages installed; monitor startup submitted. Check the monitor log and physical LEDs.'
)
