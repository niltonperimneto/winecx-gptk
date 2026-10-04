import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "weak_dispatch", Path(__file__).resolve().parents[1] / "runtime/kosmickrisp/weak_dispatch.py")
dispatch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dispatch)


class WeakDispatchTests(unittest.TestCase):
    def test_only_generated_weak_dynamic_icd_imports_are_optional(self):
        path = "Libraries/Wine/lib/kosmickrisp/libvulkan_kosmickrisp.dylib"
        line = " (undefined) weak external _kk_CreateDevice (dynamically looked up)"
        names = {"_kk_CreateDevice"}
        self.assertTrue(dispatch.optional_dispatch(path, line, names))
        self.assertFalse(dispatch.optional_dispatch(path, line.replace("weak ", ""), names))
        self.assertFalse(dispatch.optional_dispatch(path, line.replace("dynamically looked up", "from Metal"), names))
        self.assertFalse(dispatch.optional_dispatch(path, line, set()))
        self.assertFalse(dispatch.optional_dispatch("Libraries/Wine/lib/ntdll.so", line, names))
        self.assertFalse(dispatch.optional_dispatch(path, line.replace("_kk_CreateDevice", "_newSDKFunction"), names))

    def test_allowlist_comes_from_weak_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for header in dispatch.HEADERS:
                file = root / header
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("VKAPI_ATTR void VKAPI_CALL kk_Optional(void) VK_ENTRY_WEAK VK_ENTRY_HIDDEN;\n"
                                "VKAPI_ATTR void VKAPI_CALL kk_Required(void);\n")
            self.assertEqual(dispatch.generated_symbols(root), ["_kk_Optional"])
            file.write_text("")
            with self.assertRaises(ValueError):
                dispatch.generated_symbols(root)


if __name__ == "__main__":
    unittest.main()
