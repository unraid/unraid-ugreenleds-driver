#!/bin/bash
# Regenerate a reviewed source tree. The caller must authenticate all inputs.
# Run only inside a disposable x86_64 Linux container on native storage.
set -euo pipefail

[[ $# == 3 ]] || { echo 'Usage: prepare-kernel.sh KDIR STOCK_CONFIG KERNEL_RELEASE' >&2; exit 1; }
kdir=$(readlink -f "$1")
stock=$(readlink -f "$2")
release=$3
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]]
[[ $release =~ ^[0-9]+\.[0-9]+\.[0-9]+-Unraid$ ]]
[[ -s $kdir/Makefile && -s $kdir/Module.symvers && -s $stock ]]
[[ $stock != "$kdir/"* ]]
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
saved=$(mktemp -d /tmp/ugreen-kernel-inputs.XXXXXXXX)
cp "$kdir/Module.symvers" "$saved/Module.symvers"
cp "$stock" "$saved/stock.config"

# Prepared archives can contain generated GCC- and configuration-specific state.
# Do not use it, even when kernel.release and vermagic appear to match.
make -C "$kdir" mrproper
cp "$saved/stock.config" "$kdir/.config"
make -C "$kdir" olddefconfig
python3 "$scripts/verify_kernel_config.py" "$saved/stock.config" "$kdir/.config" \
  > "$saved/config-validation.json"
make -C "$kdir" -j4 modules_prepare
[[ $(<"$kdir/include/config/kernel.release") == "$release" ]]
cp "$saved/Module.symvers" "$kdir/Module.symvers"
cp "$saved/config-validation.json" "$kdir/config-validation.json"
cp "$saved/stock.config" "$kdir/stock.config"
printf 'Regenerated headers for %s. Input evidence retained in %s\n' "$release" "$saved"
