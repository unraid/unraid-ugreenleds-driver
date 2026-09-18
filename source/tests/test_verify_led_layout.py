from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_led_layout import verify_layout


STOCK = '''0000000000000000 <input_leds_brightness_get>:
   0: mov 0x1b0(%rdi),%rax
   7: mov 0x1b8(%rdi),%edx
0000000000000040 <unrelated>:
  40: mov 0x20(%rdi),%rax
'''
MODULE = '''0000000000000060 <ugreen_led_set_brightness_blocking>:
  60: movq 0x1b0(%rdi), %r13
  67: ret
'''


class LedLayoutTests(unittest.TestCase):
    def test_matching_stock_boundary(self):
        self.assertEqual(verify_layout(STOCK, MODULE)["led_classdev_boundary_bytes"], 432)

    def test_original_416_byte_layout_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "stock=432, candidate=416"):
            verify_layout(STOCK, MODULE.replace("1b0", "1a0"))

    def test_unknown_and_ambiguous_patterns_fail(self):
        for module in ("", MODULE.replace("%rdi", "%rsi"),
                       MODULE + "  68: movq 0x20(%rdi), %rax\n"):
            with self.subTest(module=module), self.assertRaises(ValueError):
                verify_layout(STOCK, module)

    def test_missing_stock_symbol_fails(self):
        with self.assertRaises(ValueError):
            verify_layout(STOCK.replace("input_leds_brightness_get", "unknown"), MODULE)


if __name__ == "__main__":
    unittest.main()
