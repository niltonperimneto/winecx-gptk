#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
if [ "${1:-}" != --wrappers-only ]; then
curl --fail --location --silent --show-error -O \
  https://github.com/mstorsjo/llvm-mingw/releases/download/20240619/llvm-mingw-20240619-ucrt-macos-universal.tar.xz
tar -xf llvm-mingw-20240619-ucrt-macos-universal.tar.xz
fi
toolchain="$PWD/llvm-mingw-20240619-ucrt-macos-universal/bin"
echo "$toolchain" >> "$GITHUB_PATH"
export PATH="$toolchain:$PATH"
x86_64-w64-mingw32-clang --version | head -1
i686-w64-mingw32-clang --version | head -1
# Wine prefers the gcc/g++ aliases during per-architecture detection, even
# when CROSSCC names clang. Cover both names for each language and PE ABI.
mkdir -p ccache-bin
for t in \
  x86_64-w64-mingw32-clang x86_64-w64-mingw32-clang++ \
  i686-w64-mingw32-clang i686-w64-mingw32-clang++ \
  x86_64-w64-mingw32-gcc x86_64-w64-mingw32-g++ \
  i686-w64-mingw32-gcc i686-w64-mingw32-g++; do
  # resolve the real binary now and bake the absolute path in: doing
  # the lookup inside the wrapper recurses forever, because by then
  # ccache-bin is first on PATH and `command -v` finds the wrapper
  real=$(command -v "$t") || { echo "::error::$t not found"; exit 1; }
  printf '#!/bin/sh\nexport CCACHE_COMPILERTYPE=clang\nexec ccache "%s" "$@"\n' "$real" > "ccache-bin/$t"
  chmod +x "ccache-bin/$t"
done
PATH="$PWD/ccache-bin:$PATH" x86_64-w64-mingw32-clang --version >/dev/null
PATH="$PWD/ccache-bin:$PATH" i686-w64-mingw32-clang --version >/dev/null
