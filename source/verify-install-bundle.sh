#!/bin/bash
# Read-only verification. The caller owns trusted acquisition and target identity.
set -euo pipefail

fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ $# == 5 ]] || fail 'Usage: verify-install-bundle.sh BUNDLE OS KERNEL STOCK_CONFIG MODEL'
bundle=$1
version=$2
kernel=$3
stock_config=$4
model=$5
[[ $version =~ ^7\.[0-9]+\.[0-9]+(-(beta|rc)\.[0-9]+)?$ ]] || fail 'Invalid OS version'
[[ $kernel =~ ^[0-9]+\.[0-9]+\.[0-9]+-Unraid$ ]] || fail 'Invalid kernel'
[[ -d $bundle && ! -L $bundle ]] || fail 'Bundle must be a regular directory'
[[ -f $stock_config && ! -L $stock_config ]] || fail 'Missing regular stock configuration'
manifest="$bundle/unraid-$version-r1.json"
approval="$bundle/approved-unraid-$version-r1.json"
for record in "$manifest" "$approval"; do
  [[ -f $record && ! -L $record ]] || fail 'Missing regular candidate or approval receipt'
done
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
config_hash=$(sha256sum -- "$stock_config")
config_hash=${config_hash%% *}
manifest_hash=$(sha256sum -- "$manifest")
manifest_hash=${manifest_hash%% *}
rows=$(jq -ner --slurpfile manifest "$manifest" --slurpfile approval "$approval" \
  --arg unraid "$version" --arg kernel "$kernel" --arg config_sha256 "$config_hash" \
  --arg manifest_sha256 "$manifest_hash" --arg model "$model" \
  -f "$script_dir/validate-install-manifest.jq")

# Do not emit any installable path until every archive passes verification.
while IFS=$'\t' read -r name expected_hash expected_size; do
  package="$bundle/$name"
  [[ -f $package && ! -L $package ]] || fail "Missing regular package: $name"
  actual_size=$(wc -c < "$package")
  [[ $actual_size -eq $expected_size ]] || fail "Package size mismatch: $name"
  actual_hash=$(sha256sum -- "$package")
  actual_hash=${actual_hash%% *}
  [[ $actual_hash == "$expected_hash" ]] || fail "Package checksum mismatch: $name"
done <<< "$rows"
printf '%s\n' "$rows"
