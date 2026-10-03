#!/bin/bash
# Run tests/x86_smoke.c as x86_64 (ARM64EC) and i686 (WoW64) on an arm64 Wine
# tree with FEX installed, in a fresh prefix. Passes only if both report the
# arm64 host and every check matches.
#
# usage: smoke-fex.sh WINE_DIRECTORY WORK_DIRECTORY
#   LLVM_MINGW=/path   llvm-mingw used to build the two test executables
#   WINE_APP_PROFILE=<profile> WINE_APP_IDENTITY=<sha1>
#                      first wrap the tree's loader in a wine.app signed for the
#                      cross-architecture entitlement (make-wine-app.sh)
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
wine=${1:?usage: smoke-fex.sh WINE_DIRECTORY WORK_DIRECTORY}
work=${2:?usage: smoke-fex.sh WINE_DIRECTORY WORK_DIRECTORY}
mingw=${LLVM_MINGW:?set LLVM_MINGW to an unpacked llvm-mingw}
unix="$wine/lib/wine/aarch64-unix"
for required in "$wine/bin/wine" "$unix/ntdll.so" "$unix/libarm64ecfex.so" "$unix/libwow64fex.so" \
                "$wine/lib/wine/aarch64-windows/xtajit64.dll" "$wine/lib/wine/aarch64-windows/xtajit.dll"; do
    [ -e "$required" ] || { echo "Missing $required" >&2; exit 1; }
done
[ "$(lipo -archs "$unix/ntdll.so")" = arm64 ] || { echo "Not an arm64 Wine tree: $wine" >&2; exit 1; }
mkdir -p "$work"
work=$(cd "$work" && pwd -P)

if [ -n "${WINE_APP_PROFILE:-}" ] && [ ! -d "$unix/wine.app" ]; then
    bash "$script_dir/make-wine-app.sh" "$unix/wine" "$unix/wine.app" "$WINE_APP_PROFILE" \
        "${WINE_APP_IDENTITY:?set WINE_APP_IDENTITY to the signing identity SHA-1}" ntdll.so=../../../ntdll.so
    rm "$unix/wine"
    ln -s wine.app/Contents/MacOS/wine "$unix/wine"
fi

"$mingw/bin/x86_64-w64-mingw32-clang" -O2 -o "$work/x86_64-smoke.exe" "$script_dir/../tests/x86_smoke.c"
"$mingw/bin/i686-w64-mingw32-clang" -O2 -msse2 -o "$work/i686-smoke.exe" "$script_dir/../tests/x86_smoke.c"

export WINEPREFIX="$work/prefix" WINEDEBUG=err+all
rm -rf "$WINEPREFIX"
status=0
for arch in x86_64 i686; do
    echo "== $arch"
    timeout 300 "$wine/bin/wine" "$work/$arch-smoke.exe" > "$work/$arch.log" 2>&1 || true
    cat "$work/$arch.log"
    if grep -q '^x86 smoke passed' "$work/$arch.log" && grep -q 'native 0xaa64' "$work/$arch.log"; then
        echo "== $arch: passed under FEX"
    else
        status=1
        if grep -q 'failed to map the shared user data' "$work/$arch.log"; then
            echo "== $arch: the loader cannot use the low 4GB; it needs the cross-architecture entitlement"
        else
            echo "== $arch: FAILED"
        fi
    fi
done
"$wine/bin/wineserver" -k 2>/dev/null || true
exit "$status"
