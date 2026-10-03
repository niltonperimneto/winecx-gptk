#!/bin/bash
# Install a prebuilt native bundle into a staged Rosetta Wine runtime.
set -euo pipefail
wine=${1:?usage: install-rosetta.sh WINE_DIRECTORY BUNDLE_DIRECTORY}
bundle=${2:?usage: install-rosetta.sh WINE_DIRECTORY BUNDLE_DIRECTORY}
script_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
[ -d "$wine/lib/wine/x86_64-unix" ] || { echo "Not an x86_64 Wine runtime: $wine" >&2; exit 1; }
[ ! -e "$wine/bin/wine-kosmickrisp" ] || { echo "KosmicKrisp launcher already exists" >&2; exit 1; }
[ ! -e "$wine/lib/kosmickrisp" ] || { echo "KosmicKrisp destination already exists" >&2; exit 1; }
for required in libvulkan.1.dylib libvulkan_kosmickrisp.dylib kosmickrisp_icd.json SOURCE.txt; do
    [ -f "$bundle/$required" ] || { echo "Missing KosmicKrisp component: $required" >&2; exit 1; }
done
python3 - "$bundle/kosmickrisp_icd.json" <<'CHECK_ICD'
import json, sys
with open(sys.argv[1]) as stream:
    manifest = json.load(stream)
if manifest.get("ICD", {}).get("library_path") != "./libvulkan_kosmickrisp.dylib":
    sys.exit("ICD manifest must select the bundled KosmicKrisp library")
CHECK_ICD
for executable in "$wine/bin/wine64" "$wine/bin/wineserver" "$wine/lib/wine/x86_64-unix/win32u.so"; do
    [ "$(lipo -archs "$executable")" = x86_64 ] || { echo "Not an x86_64 binary: $executable" >&2; exit 1; }
done
# This recipe uses CrossOver's guarded host-loader override, as does the
# arm64 launcher. Fail if the supplied Wine build cannot honor that override.
strings -a "$wine/lib/wine/x86_64-unix/win32u.so" | grep 'CX_LIBVULKAN' >/dev/null
for library in "$bundle"/*.dylib; do
    [ "$(lipo -archs "$library")" = x86_64 ] || { echo "Not an x86_64 library: $library" >&2; exit 1; }
    codesign --verify --strict "$library"
    otool -L "$library" | tail -n +3 | while read -r dependency rest; do
        case "$dependency" in
            /usr/lib/*|/System/Library/*) ;;
            @loader_path/*) test -f "$bundle/${dependency#@loader_path/}" ;;
            *) echo "Unbundled dependency: $dependency" >&2; exit 1 ;;
        esac
    done
done
/usr/bin/arch -x86_64 /usr/bin/true || { echo "Rosetta 2 is required on Apple Silicon" >&2; exit 1; }
ditto "$bundle" "$wine/lib/kosmickrisp"
install -m 755 "$script_dir/wine-kosmickrisp" "$wine/bin/wine-kosmickrisp"
