"""Recognize Mesa's generated optional dispatch slots in the symbol audit."""
import argparse
import json
from pathlib import Path
import re


HEADERS = ("kosmickrisp/vulkan/kk_entrypoints.h",
           "vulkan/runtime/vk_common_entrypoints.h",
           "vulkan/runtime/vk_cmd_enqueue_entrypoints.h",
           "vulkan/wsi/wsi_common_entrypoints.h")


def generated_symbols(source):
    symbols = set()
    for relative in HEADERS:
        text = (source / relative).read_text()
        names = re.findall(r"VKAPI_CALL\s+(\w+)\([^;]*?\)\s+VK_ENTRY_WEAK", text)
        if not names:
            raise ValueError(f"no generated weak entrypoints in {relative}")
        symbols.update("_" + name for name in names)
    return sorted(symbols)


def optional_dispatch(path, nm_line, symbols):
    return (Path(path).as_posix().endswith("/Wine/lib/kosmickrisp/libvulkan_kosmickrisp.dylib")
            and "(undefined) weak external " in nm_line
            and "(dynamically looked up)" in nm_line
            and (match := re.search(r"external (\S+)", nm_line)) is not None
            and match.group(1) in symbols)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("generated_source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(generated_symbols(args.generated_source), indent=2) + "\n")
