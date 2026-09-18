#!/bin/bash
# Library: callers supply the plugin directory after target/package validation.
# No package effects, process termination, module unload, or settings changes.

ugreen_disable_legacy() (
  set -euo pipefail
  local plugins=$1
  local legacy="$plugins/ugreenleds-driver.plg"
  local directory="$plugins/ugreen-leds/legacy"
  local saved="$directory/ugreenleds-driver.plg.disabled"
  [[ -d $plugins && ! -L $plugins && ! -L $plugins/ugreen-leds && ! -L $directory ]] || {
    echo 'Unsafe plugin migration directory' >&2; exit 1;
  }
  if [[ ! -e $legacy && ! -L $legacy ]]; then
    printf '%s\n' 'No legacy boot plugin to disable'
    exit 0
  fi
  [[ -f $legacy && ! -L $legacy && ! -e $saved && ! -L $saved ]] || {
    echo 'Legacy backup conflict; inspect both files before migration' >&2; exit 1;
  }
  mkdir -p -- "$directory"
  # Rename on the boot filesystem. Never invoke the old uninstall hook, which
  # removes the settings directory. Existing package caches are retained too.
  mv -- "$legacy" "$saved"
  printf '%s\n' 'Legacy boot plugin saved. Reboot before activating the replacement.'
)

ugreen_restore_legacy() (
  set -euo pipefail
  local plugins=$1
  local directory="$plugins/ugreen-leds/legacy"
  local saved="$directory/ugreenleds-driver.plg.disabled"
  local legacy="$plugins/ugreenleds-driver.plg"
  local replacement="$plugins/ugreen-leds.plg"
  local disabled="$directory/ugreen-leds.plg.disabled"
  [[ -d $plugins && ! -L $plugins && ! -L $plugins/ugreen-leds && ! -L $directory ]] || {
    echo 'Unsafe plugin recovery directory' >&2; exit 1;
  }
  [[ -f $saved && ! -L $saved && ! -e $legacy && ! -L $legacy ]] || {
    echo 'No unique legacy backup to restore; inspect the boot files' >&2; exit 1;
  }
  if [[ -e $replacement || -L $replacement ]]; then
    [[ -f $replacement && ! -L $replacement && ! -e $disabled && ! -L $disabled ]] || {
      echo 'Replacement backup conflict; recovery stopped before changes' >&2; exit 1;
    }
    # Disable the new entry before restoring the old one, so a partial failure
    # never leaves both plugins scheduled for the next boot.
    mv -- "$replacement" "$disabled"
  fi
  mv -- "$saved" "$legacy"
  printf '%s\n' 'Legacy boot plugin restored. Reboot to replace the running packages.'
)
