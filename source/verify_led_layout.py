#!/usr/bin/env python3
"""Compare the LED class boundary in stock input-leds and the candidate driver.

This is a regression gate for the known led_classdev overrun, not a complete
kernel ABI proof. Unknown instruction patterns fail and require review.
"""

import argparse
import json
import lzma
from pathlib import Path
import re
import subprocess
import tempfile


def pointer_offset(disassembly, symbol):
    header = re.search(r"^[0-9a-f]+ <" + re.escape(symbol) + r">:\s*$",
                       disassembly, re.MULTILINE)
    if not header:
        raise ValueError(f"Missing ABI probe function: {symbol}")
    body = re.split(r"\n[0-9a-f]+ <", disassembly[header.end():], maxsplit=1)[0]
    # SysV x86-64 passes cdev as the first argument in rdi. Both reviewed
    # functions read the pointer immediately following their embedded cdev.
    offsets = re.findall(r"\bmovq?\s+0x([0-9a-f]+)\(%rdi\),\s*%r[a-z0-9]+\b", body)
    if len(offsets) != 1:
        raise ValueError(f"Unrecognized ABI probe instructions: {symbol}")
    return int(offsets[0], 16)


def verify_layout(stock, candidate):
    expected = pointer_offset(stock, "input_leds_brightness_get")
    actual = pointer_offset(candidate, "ugreen_led_set_brightness_blocking")
    if expected <= 0 or expected != actual:
        raise ValueError(f"LED layout mismatch: stock={expected}, candidate={actual}")
    return {"result": "pass", "led_classdev_boundary_bytes": expected,
            "scope": "Known cdev overrun regression only; hardware behavior remains untested"}


def disassemble(path):
    data = path.read_bytes()
    if path.suffix == ".xz":
        data = lzma.decompress(data)
    if data[:6] != b"\x7fELF\x02\x01" or data[18:20] != b"\x3e\x00":
        raise ValueError(f"Not a little-endian x86-64 ELF file: {path.name}")
    with tempfile.NamedTemporaryFile(suffix=".ko") as module:
        module.write(data)
        module.flush()
        return subprocess.check_output(
            ["objdump", "-d", "--no-show-raw-insn", module.name], text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock_input_leds", type=Path)
    parser.add_argument("candidate_led_ugreen", type=Path)
    args = parser.parse_args()
    try:
        result = verify_layout(disassemble(args.stock_input_leds),
                               disassemble(args.candidate_led_ugreen))
    except (OSError, ValueError, lzma.LZMAError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"LED layout validation failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
