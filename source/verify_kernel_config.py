#!/usr/bin/env python3
"""Compare regenerated kernel configuration with the official installer config."""

import argparse
import json
from pathlib import Path
import re


# Rust is not compiled when CONFIG_RUST=n. These are tool probes, not runtime
# options. Keep an explicit list so future options require review.
UNUSED_RUST_PROBES = {
    "CONFIG_RUSTC_VERSION", "CONFIG_RUST_IS_AVAILABLE",
    "CONFIG_RUSTC_LLVM_VERSION", "CONFIG_RUSTC_HAS_COERCE_POINTEE",
    "CONFIG_RUSTC_HAS_SPAN_FILE", "CONFIG_RUSTC_HAS_UNNECESSARY_TRANSMUTES",
    "CONFIG_RUSTC_HAS_FILE_WITH_NUL", "CONFIG_RUSTC_HAS_FILE_AS_C_STR",
    "CONFIG_RUSTC_HAS_SUSPICIOUS_RUNTIME_SYMBOL_DEFINITIONS",
}
REQUIRED = {
    "CONFIG_CC_IS_GCC": "y", "CONFIG_AS_IS_GNU": "y",
    "CONFIG_LD_IS_BFD": "y", "CONFIG_X86_64": "y",
    "CONFIG_MODULES": "y",
}


def parse_config(text):
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r"(CONFIG_[A-Za-z0-9_]+)=(.+)", line)
        disabled = re.fullmatch(r"# (CONFIG_[A-Za-z0-9_]+) is not set", line)
        if match:
            key, value = match.groups()
        elif disabled:
            key, value = disabled[1], "n"
        elif not line or line.startswith("#"):
            continue
        else:
            raise ValueError(f"Unrecognized configuration line: {line}")
        if key in result:
            raise ValueError(f"Duplicate configuration key: {key}")
        result[key] = value
    # Kconfig omits CONFIG_RUST entirely when its tool dependency is absent.
    # Both omission and an explicit 'not set' disable compilation of Rust.
    result.setdefault("CONFIG_RUST", "n")
    if result["CONFIG_RUST"] != "n":
        raise ValueError("Rust-enabled targets are not supported by this builder")
    for key, value in REQUIRED.items():
        if result.get(key) != value:
            raise ValueError(f"Unsupported or missing {key}: expected {value}")
    for key in ("CONFIG_GCC_VERSION", "CONFIG_AS_VERSION", "CONFIG_LD_VERSION"):
        if not re.fullmatch(r"[1-9][0-9]*", result.get(key, "")):
            raise ValueError(f"Missing or invalid tool version: {key}")
    if not result.get("CONFIG_CC_VERSION_TEXT", "").startswith('"gcc '):
        raise ValueError("Missing GCC compiler identity")
    return result


def verify_configs(stock, prepared):
    expected, actual = parse_config(stock), parse_config(prepared)
    differences = []
    metadata = []
    for key in sorted(expected.keys() | actual.keys()):
        if expected.get(key) == actual.get(key):
            continue
        change = {"key": key, "stock": expected.get(key), "generated": actual.get(key)}
        # The package-specific banner can differ, but GCC_VERSION must match.
        if key == "CONFIG_CC_VERSION_TEXT" or key in UNUSED_RUST_PROBES:
            metadata.append(change)
        else:
            differences.append(change)
    if differences:
        raise ValueError("Target configuration differs: " + json.dumps(differences))
    return {"result": "pass", "non_runtime_metadata_differences": metadata}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("prepared", type=Path)
    args = parser.parse_args()
    try:
        report = verify_configs(args.stock.read_text(), args.prepared.read_text())
    except (OSError, ValueError) as error:
        parser.exit(1, f"Kernel configuration validation failed: {error}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
