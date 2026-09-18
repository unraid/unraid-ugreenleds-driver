#!/bin/bash
# Plugin Manager post-hook: no watcher, no changes to the shared legacy helper.
set -euo pipefail
[[ ${1:-} == plugin ]] || exit 0
case ${2:-} in install|update|remove) ;; *) exit 0 ;; esac
case ${3:-} in unRAIDServer.plg|unRAIDServer-.plg) ;; *) exit 0 ;; esac
[[ -z ${4:-} && -f /boot/config/plugins/ugreen-leds.plg ]] || exit 0
if bash /usr/local/emhttp/plugins/ugreen-leds/ugreen-plugin.sh prefetch-boot; then
  exit 0
fi
message='UGREEN LED plugin is NOT ready for the staged OS. Keep the current boot running until prefetch succeeds, or expect LEDs to remain disabled after reboot. The OS update itself is already staged.'
printf '%s\n' "$message" >&2
if ! logger -t ugreen-leds "$message"; then
  printf '%s\n' 'UGREEN warning could not be written to syslog; attempting notification.' >&2
fi
/usr/local/emhttp/webGui/scripts/notify -e 'UGREEN LED plugin' -s 'Target kernel package unavailable' -d "$message" -i warning
exit 1
