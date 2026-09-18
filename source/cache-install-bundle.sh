#!/bin/bash
# Acquire an immutable approved bundle. No package installation or activation.
set -euo pipefail
fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ $# == 5 ]] || fail 'Usage: cache-install-bundle.sh CACHE_ROOT OS KERNEL STOCK_CONFIG MODEL'
cache=$1
version=$2
kernel=$3
config=$4
model=$5
[[ $cache == /* && $cache != / && ! -L $cache ]] || fail 'Use an absolute, non-symlink cache directory'
[[ $version =~ ^7\.[0-9]+\.[0-9]+(-(beta|rc)\.[0-9]+)?$ ]] || fail 'Invalid OS version'
[[ $kernel =~ ^[0-9]+\.[0-9]+\.[0-9]+-Unraid$ ]] || fail 'Invalid kernel'
[[ -f $config && ! -L $config ]] || fail 'Missing regular stock configuration'
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
parent="$cache/$kernel"
bundle="$parent/$version-r1"
[[ ! -L $parent ]] || fail 'Kernel cache must not be a symlink'
mkdir -p -- "$parent"
lock="$parent/.$version-r1.lock"
mkdir -- "$lock" 2>/dev/null || fail 'Bundle cache is locked; inspect the active writer before retrying'
stage=''
cleanup() {
  if [[ -n $stage ]]; then rm -rf -- "$stage"; fi
  rmdir -- "$lock"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [[ -e $bundle || -L $bundle ]]; then
  bash "$script_dir/verify-install-bundle.sh" "$bundle" "$version" "$kernel" "$config" "$model" >/dev/null
  printf '%s\n' "$bundle"
  exit 0
fi

stage=$(mktemp -d "$parent/.$version-r1.download.XXXXXXXX")
base="https://github.com/unraid/unraid-ugreenleds-driver/releases/download/$kernel"
download() {
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
    --connect-timeout 15 --max-time 300 --output "$stage/$1" "$base/$1"
}
receipt="unraid-$version-r1.json"
download "$receipt"
download "approved-$receipt"
manifest_hash=$(sha256sum -- "$stage/$receipt")
config_hash=$(sha256sum -- "$config")
rows=$(jq -ner --slurpfile manifest "$stage/$receipt" --slurpfile approval "$stage/approved-$receipt" \
  --arg unraid "$version" --arg kernel "$kernel" --arg config_sha256 "${config_hash%% *}" \
  --arg manifest_sha256 "${manifest_hash%% *}" --arg model "$model" \
  -f "$script_dir/validate-install-manifest.jq")
while IFS=$'\t' read -r name _hash _size; do download "$name"; done <<< "$rows"
bash "$script_dir/verify-install-bundle.sh" "$stage" "$version" "$kernel" "$config" "$model" >/dev/null
# The lock covers all writers using this entrypoint. Rename within the same
# filesystem exposes only a fully verified bundle, never partial downloads.
mv -- "$stage" "$bundle"
stage=''
printf '%s\n' "$bundle"
