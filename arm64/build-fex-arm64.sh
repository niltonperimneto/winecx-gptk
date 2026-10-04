#!/bin/bash
# Build FEX for the arm64 runtime from the pinned upstream release plus the
# patches in fex/patches: the ARM64EC and WoW64 translators (PE, cross built
# with llvm-mingw) and their native macOS Unix helpers.
#
# The output matches the runtime layout. Wine loads the translators by their
# Windows names (xtajit64.dll for ARM64EC, xtajit.dll for WoW64) and FEX
# loads its helpers by name (libarm64ecfex.so, libwow64fex.so).
#
# usage: build-fex-arm64.sh WORK_DIRECTORY OUTPUT_DIRECTORY
#   LLVM_MINGW=/path  use an unpacked llvm-mingw instead of the pinned download
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
source "$script_dir/fex/pins.env"
work=${1:?usage: build-fex-arm64.sh WORK_DIRECTORY OUTPUT_DIRECTORY}
output=${2:?usage: build-fex-arm64.sh WORK_DIRECTORY OUTPUT_DIRECTORY}

[ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] || {
    echo "the FEX Unix helpers build natively: run this on an arm64 macOS host" >&2; exit 1; }
for tool in git cmake ninja python3 gzip dd shasum clang++ lipo vtool otool nm codesign install_name_tool; do
    command -v "$tool" >/dev/null || { echo "missing host tool: $tool" >&2; exit 1; }
done
[ ! -e "$output" ] || [ -z "$(ls -A "$output")" ] || {
    echo "output directory is not empty: $output" >&2; exit 1; }
mkdir -p "$work" "$output"
work=$(cd "$work" && pwd -P)
output=$(cd "$output" && pwd -P)
export MACOSX_DEPLOYMENT_TARGET=26.0

# Toolchain: an explicit LLVM_MINGW, the provisioned copy build-arm64-unix.sh
# uses, or the pinned release downloaded into the work directory.
mingw=${LLVM_MINGW:-/Volumes/Wine/toolchains/$LLVM_MINGW_ASSET}
if [ -z "${LLVM_MINGW:-}" ] && [ ! -d "$mingw" ]; then
    mingw="$work/$LLVM_MINGW_ASSET"
    if [ ! -d "$mingw" ]; then
        tarball="$work/$LLVM_MINGW_ASSET.tar.xz"
        [ -f "$tarball" ] || curl -fL -o "$tarball" \
            "https://github.com/mstorsjo/llvm-mingw/releases/download/$LLVM_MINGW_RELEASE/$LLVM_MINGW_ASSET.tar.xz"
        echo "$LLVM_MINGW_SHA256  $tarball" | shasum -a 256 -c -
        tar -xJf "$tarball" -C "$work"
    fi
fi
for triple in arm64ec aarch64; do
    [ -x "$mingw/bin/$triple-w64-mingw32-clang++" ] || {
        echo "no $triple-w64-mingw32-clang++ in $mingw/bin" >&2; exit 1; }
done
readobj="$mingw/bin/llvm-readobj"

src="$work/FEX"
if [ ! -d "$src/.git" ]; then
    git init "$src"
    git -C "$src" remote add origin "$FEX_REPO"
fi
git -C "$src" fetch --depth=1 origin "$FEX_COMMIT"
git -C "$src" checkout --detach FETCH_HEAD
[ "$(git -C "$src" rev-parse HEAD)" = "$FEX_COMMIT" ]
# Reset first so a reused work directory never carries an earlier application;
# a patch that no longer applies fails the build.
git -C "$src" reset --hard --quiet "$FEX_COMMIT"
git -C "$src" clean -ffdxq
for patch in "$script_dir"/fex/patches/*.patch; do
    git -C "$src" apply --index "$patch"
done
# The test binary submodules are large and only used by Linux test suites.
git -C "$src" config -f .gitmodules --get-regexp '^submodule\..*\.path$' | while read -r _ path; do
    case "$path" in External/fex-*-tests-bins|External/fex-posixtest-bins) continue ;; esac
    git -C "$src" submodule update --init --depth=1 -- "$path"
done

# The PE half, configured as upstream's wine_build action does.
build_pe() {
    local triple=$1 target=$2 build="$work/build-$2"
    PATH="$mingw/bin:$PATH" cmake --fresh -S "$src" -B "$build" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_TOOLCHAIN_FILE=Data/CMake/toolchain_mingw.cmake \
        -DMINGW_TRIPLE="$triple" -DENABLE_LTO=False -DENABLE_ASSERTIONS=False \
        -DENABLE_JEMALLOC_GLIBC_ALLOC=False -DBUILD_TESTING=False \
        -DTUNE_ARCH=generic -DTUNE_CPU=none -DRANGES_NATIVE=OFF
    PATH="$mingw/bin:$PATH" cmake --build "$build" --target "$target" --parallel "$(sysctl -n hw.ncpu)"
}
build_pe arm64ec-w64-mingw32 arm64ecfex
build_pe aarch64-w64-mingw32 wow64fex

# The native helpers, with Apple's toolchain.
cmake --fresh -S "$src/Source/Windows/UnixLib" -B "$work/build-unixlib" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
    -DCMAKE_OSX_DEPLOYMENT_TARGET="$MACOSX_DEPLOYMENT_TARGET"
cmake --build "$work/build-unixlib" --parallel "$(sysctl -n hw.ncpu)"

mkdir -p "$output/aarch64-windows" "$output/aarch64-unix" "$output/licenses"
cp "$(find "$work/build-arm64ecfex" -name libarm64ecfex.dll -print -quit)" "$output/aarch64-windows/xtajit64.dll"
cp "$(find "$work/build-wow64fex" -name libwow64fex.dll -print -quit)" "$output/aarch64-windows/xtajit.dll"
cp "$work/build-unixlib/libarm64ecfex.so" "$work/build-unixlib/libwow64fex.so" "$output/aarch64-unix/"

# Fail rather than package a translator for the wrong machine, or one Wine
# would not treat as builtin.
check_pe() {
    local dll=$1 formats=$2 format
    format=$("$readobj" --file-headers "$dll" | awk '$1 == "Format:" {print $2}')
    case " $formats " in
        *" $format "*) ;;
        *) echo "$dll is $format, expected one of: $formats" >&2; exit 1 ;;
    esac
    # patch_library_wine writes wine_builtin.bin at offset 64.
    python3 -c 'import sys; m = open(sys.argv[2], "rb").read(); f = open(sys.argv[1], "rb"); f.seek(64)
sys.exit(f.read(len(m)) != m)' "$dll" "$src/Source/Windows/wine_builtin.bin" || {
        echo "$dll lacks the Wine builtin marker" >&2; exit 1; }
}
check_pe "$output/aarch64-windows/xtajit64.dll" "COFF-ARM64EC COFF-ARM64X"
check_pe "$output/aarch64-windows/xtajit.dll" "COFF-ARM64"

# The helpers: arm64 only, macOS 26 or later, system dependencies only, and
# the table Wine resolves when FEX loads them.
for library in "$output"/aarch64-unix/*.so; do
    [ "$(lipo -archs "$library")" = arm64 ] || {
        echo "$library is $(lipo -archs "$library"), not arm64" >&2; exit 1; }
    minos=$(vtool -show-build "$library" | awk '$1 == "minos" {print $2}')
    python3 -c 'import sys; v = tuple(map(int, sys.argv[1].split("."))); sys.exit(v < (26, 0))' "${minos:-0}" || {
        echo "$library targets macOS ${minos:-unknown}, not 26.0 or later" >&2; exit 1; }
    nm -gU "$library" | grep -q ' ___wine_unix_call_funcs$' || {
        echo "$library does not export __wine_unix_call_funcs" >&2; exit 1; }
    install_name_tool -id "@loader_path/$(basename "$library")" "$library"
    otool -L "$library" | tail -n +3 | while read -r dependency rest; do
        case "$dependency" in
            /usr/lib/*|/System/Library/*) ;;
            *) echo "unexpected dependency in $library: $dependency" >&2; exit 1 ;;
        esac
    done
    codesign --force --sign - --timestamp=none "$library"
    codesign --verify --strict "$library"
done

cp "$src/LICENSE" "$output/licenses/fex.txt"
cp "$script_dir/fex/pins.env" "$output/SOURCE.txt"
for patch in "$script_dir"/fex/patches/*.patch; do
    echo "PATCH=$(basename "$patch") $(shasum -a 256 "$patch" | cut -d' ' -f1)"
done >> "$output/SOURCE.txt"
echo "LLVM_MINGW_USED=$mingw" >> "$output/SOURCE.txt"
echo "MACOSX_DEPLOYMENT_TARGET=$MACOSX_DEPLOYMENT_TARGET" >> "$output/SOURCE.txt"
{
    "$mingw/bin/arm64ec-w64-mingw32-clang++" --version
    /usr/bin/clang++ --version
    cmake --version
    echo "ninja $(ninja --version)"
    python3 --version
} > "$output/BUILD-TOOLS.txt"
echo "== FEX bundle: $output"
