#!/bin/bash
# Install a bundle from build-fex-arm64.sh into a staged arm64 Wine runtime,
# replacing the FEX files carried over from the base runtime.
set -euo pipefail
wine=${1:?usage: install-fex.sh WINE_DIRECTORY BUNDLE_DIRECTORY}
bundle=${2:?usage: install-fex.sh WINE_DIRECTORY BUNDLE_DIRECTORY}
unix="$wine/lib/wine/aarch64-unix"
windows="$wine/lib/wine/aarch64-windows"
[ -d "$unix" ] && [ -d "$windows" ] || { echo "Not an arm64 Wine runtime: $wine" >&2; exit 1; }
[ ! -e "$wine/lib/fex" ] || { echo "FEX provenance destination already exists" >&2; exit 1; }
for required in aarch64-windows/xtajit64.dll aarch64-windows/xtajit.dll \
                aarch64-unix/libarm64ecfex.so aarch64-unix/libwow64fex.so SOURCE.txt; do
    [ -f "$bundle/$required" ] || { echo "Missing FEX component: $required" >&2; exit 1; }
done
# Check each translator's PE machine. An ARM64EC image has the AMD64 machine
# plus CHPE metadata in its load config; an ARM64X image has the ARM64
# machine plus that metadata; the WoW64 translator is plain ARM64. Wine must
# also treat both as builtin.
python3 - "$bundle/aarch64-windows/xtajit64.dll" "$bundle/aarch64-windows/xtajit.dll" <<'CHECK_PE'
import struct, sys

def kind(path):
    with open(path, "rb") as stream:
        data = stream.read()
    try:
        pe = struct.unpack_from("<I", data, 0x3c)[0]
        if data[:2] != b"MZ" or data[pe:pe + 4] != b"PE\0\0":
            sys.exit(f"Not a PE image: {path}")
        if data[0x40:0x50] != b"Wine builtin DLL":
            sys.exit(f"Missing the Wine builtin marker: {path}")
        machine, sections = struct.unpack_from("<HH", data, pe + 4)
        optional_size = struct.unpack_from("<H", data, pe + 20)[0]
        optional = pe + 24
        chpe = 0
        if struct.unpack_from("<H", data, optional)[0] == 0x20b:  # PE32+
            rva = struct.unpack_from("<I", data, optional + 112 + 10 * 8)[0]  # load config
            for index in range(sections if rva else 0):
                header = optional + optional_size + 40 * index
                virtual_size, address, raw_size, raw = struct.unpack_from("<IIII", data, header + 8)
                if address <= rva < address + max(virtual_size, raw_size):
                    offset = raw + rva - address
                    if struct.unpack_from("<I", data, offset)[0] >= 0xd0:
                        chpe = struct.unpack_from("<Q", data, offset + 0xc8)[0]
                    break
    except struct.error:
        sys.exit(f"Truncated PE image: {path}")
    return {(0x8664, True): "ARM64EC", (0xaa64, True): "ARM64X",
            (0xaa64, False): "ARM64"}.get((machine, bool(chpe)), f"machine {machine:#06x}")

for path, wanted in ((sys.argv[1], ("ARM64EC", "ARM64X")), (sys.argv[2], ("ARM64",))):
    found = kind(path)
    if found not in wanted:
        sys.exit(f"{path} is {found}, expected {' or '.join(wanted)}")
CHECK_PE
for library in "$bundle"/aarch64-unix/*.so; do
    [ "$(lipo -archs "$library")" = arm64 ] || { echo "Not an arm64 library: $library" >&2; exit 1; }
    codesign --verify --strict "$library"
done
cp "$bundle/aarch64-windows/xtajit64.dll" "$bundle/aarch64-windows/xtajit.dll" "$windows/"
cp "$bundle/aarch64-unix/libarm64ecfex.so" "$bundle/aarch64-unix/libwow64fex.so" "$unix/"
mkdir -p "$wine/lib/fex"
cp "$bundle/SOURCE.txt" "$wine/lib/fex/"
[ ! -d "$bundle/licenses" ] || cp -R "$bundle/licenses" "$wine/lib/fex/licenses"
