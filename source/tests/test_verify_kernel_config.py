from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_kernel_config import verify_configs


CONFIG = '''# fixture
CONFIG_CC_VERSION_TEXT="gcc (GCC) 15.3.0"
CONFIG_CC_IS_GCC=y
CONFIG_GCC_VERSION=150300
CONFIG_AS_IS_GNU=y
CONFIG_AS_VERSION=24601
CONFIG_LD_IS_BFD=y
CONFIG_LD_VERSION=24601
CONFIG_X86_64=y
CONFIG_MODULES=y
# CONFIG_RUST is not set
CONFIG_LEDS_BRIGHTNESS_HW_CHANGED=y
CONFIG_RUST_IS_AVAILABLE=y
CONFIG_RUSTC_VERSION=109800
'''


class ConfigTests(unittest.TestCase):
    def test_real_kernel_symbols_can_contain_lowercase(self):
        stock = CONFIG + "CONFIG_MT76x02_LIB=m\n"
        self.assertEqual(verify_configs(stock, stock)["result"], "pass")
        with self.assertRaisesRegex(ValueError, "CONFIG_MT76x02_LIB"):
            verify_configs(stock, CONFIG)

    def test_identical_config(self):
        self.assertEqual(verify_configs(CONFIG, CONFIG), {
            "result": "pass", "non_runtime_metadata_differences": []})

    def test_led_layout_change_rejected(self):
        changed = CONFIG.replace("CONFIG_LEDS_BRIGHTNESS_HW_CHANGED=y",
                                 "# CONFIG_LEDS_BRIGHTNESS_HW_CHANGED is not set")
        with self.assertRaisesRegex(ValueError, "CONFIG_LEDS_BRIGHTNESS_HW_CHANGED"):
            verify_configs(CONFIG, changed)

    def test_wrong_compiler_and_binutils_rejected(self):
        for original, replacement in (("150300", "140200"), ("24601", "24400")):
            with self.subTest(original=original), self.assertRaises(ValueError):
                verify_configs(CONFIG, CONFIG.replace(original, replacement))

    def test_unused_rust_metadata_recorded(self):
        changed = CONFIG.replace("CONFIG_RUST_IS_AVAILABLE=y",
                                 "# CONFIG_RUST_IS_AVAILABLE is not set")
        changed = changed.replace("CONFIG_RUSTC_VERSION=109800", "CONFIG_RUSTC_VERSION=0")
        report = verify_configs(CONFIG, changed)
        self.assertEqual(len(report["non_runtime_metadata_differences"]), 2)

    def test_kconfig_omits_rust_when_tool_dependency_absent(self):
        changed = CONFIG.replace("# CONFIG_RUST is not set\n", "")
        self.assertEqual(verify_configs(CONFIG, changed)["result"], "pass")

    def test_rust_enabled_is_not_supported(self):
        changed = CONFIG.replace("# CONFIG_RUST is not set", "CONFIG_RUST=y")
        with self.assertRaises(ValueError):
            verify_configs(changed, changed)

    def test_future_rust_option_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, "CONFIG_RUST_FUTURE_FEATURE"):
            verify_configs(CONFIG, CONFIG + "CONFIG_RUST_FUTURE_FEATURE=y\n")

    def test_missing_changed_new_and_duplicate_options_rejected(self):
        for changed in (CONFIG.replace("CONFIG_MODULES=y\n", ""),
                        CONFIG + "CONFIG_NEW_OPTION=y\n",
                        CONFIG + "CONFIG_MODULES=y\n", ""):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                verify_configs(CONFIG, changed)

    def test_gcc_banner_only_is_recorded(self):
        changed = CONFIG.replace("gcc (GCC)", "gcc (Debian)")
        self.assertEqual(verify_configs(CONFIG, changed)[
            "non_runtime_metadata_differences"][0]["key"], "CONFIG_CC_VERSION_TEXT")


if __name__ == "__main__":
    unittest.main()
