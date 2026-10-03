#!/bin/bash
# Cross-build FEX's Windows translators on macOS; native helpers are separate.
set -euo pipefail
SRC="${FEX_SRC:?set FEX_SRC to dappermint/FEX with its required submodules initialized}"
TOOLCHAIN="${LLVM_MINGW:?set LLVM_MINGW to llvm-mingw with arm64ec support}"
OUT="${1:?new output directory}"
[ ! -e "$OUT" ] || { echo "output directory already exists: $OUT" >&2; exit 1; }
export PATH="$TOOLCHAIN/bin:$PATH"
command -v arm64ec-w64-mingw32-clang >/dev/null
command -v aarch64-w64-mingw32-clang >/dev/null
mkdir -p "$OUT/aarch64-windows"
OUT=$(cd "$OUT" && pwd)
SRC=$(cd "$SRC" && pwd)
for lane in arm64ec wow64; do
    case "$lane" in
        arm64ec) triple=arm64ec-w64-mingw32; target=arm64ecfex ;;
        wow64) triple=aarch64-w64-mingw32; target=wow64fex ;;
    esac
    cmake -S "$SRC" -B "$OUT/build-$lane" -G Ninja \
        -DCMAKE_TOOLCHAIN_FILE="$SRC/Data/CMake/toolchain_mingw.cmake" \
        -DMINGW_TRIPLE="$triple" -DCMAKE_BUILD_TYPE=Release \
        -DENABLE_LTO=False -DENABLE_ASSERTIONS=False \
        -DENABLE_JEMALLOC_GLIBC_ALLOC=False -DBUILD_TESTING=False \
        -DCMAKE_INSTALL_PREFIX=/usr -DTUNE_ARCH=generic -DTUNE_CPU=none \
        -DRANGES_NATIVE=OFF
    cmake --build "$OUT/build-$lane" --target "$target" -j "${FEX_BUILD_JOBS:-4}"
    cp "$OUT/build-$lane/Bin/lib$target.dll" "$OUT/aarch64-windows/"
    llvm-readobj --file-headers --coff-imports --coff-exports \
        "$OUT/aarch64-windows/lib$target.dll" > "$OUT/$lane-inspection.txt"
done
cp "$SRC/LICENSE" "$OUT/LICENSE.FEX"
cat > "$OUT/SOURCE.txt" <<EOF_SOURCE
FEX_REPOSITORY=https://github.com/dappermint/FEX
FEX_COMMIT=$(git -C "$SRC" rev-parse HEAD)
LLVM_MINGW=$TOOLCHAIN
TARGETS=arm64ec,wow64
WINE_EXECUTION_TESTED=no
EOF_SOURCE
git -C "$SRC" submodule status > "$OUT/SUBMODULES.txt"
