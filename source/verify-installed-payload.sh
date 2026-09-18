#!/bin/bash
# Compare installed payload bytes with an already approved archive. The caller
# owns the private staging directory and deletes it after verification.
set -euo pipefail
[[ $# == 3 ]] || exit 1
archive=$1
runtime=$2
stage=$3
[[ -f $archive && -d $runtime && -d $stage && ! -L $stage ]] || exit 1
payload=$(mktemp -d "$stage/payload.XXXXXXXX")
tar -xf "$archive" -C "$payload"
find "$payload" \( -type f -o -type l \) -print0 > "$payload.members"
count=0
while IFS= read -r -d '' member; do
  relative=${member#"$payload"/}
  # Package-manager metadata is recorded in pkgtools, not installed at /install.
  case $relative in install/*) continue ;; esac
  installed="$runtime/$relative"
  if [[ -L $member ]]; then
    [[ -L $installed && $(readlink -- "$member") == "$(readlink -- "$installed")" ]] || {
      echo "Installed symlink mismatch: $relative" >&2; exit 1;
    }
  else
    if [[ ! -f $installed || -L $installed ]] || ! cmp -s -- "$member" "$installed"; then
      echo "Installed payload mismatch: $relative" >&2; exit 1
    fi
  fi
  count=$((count + 1))
done < "$payload.members"
[[ $count -gt 0 ]] || { echo 'Package has no verifiable payload' >&2; exit 1; }
