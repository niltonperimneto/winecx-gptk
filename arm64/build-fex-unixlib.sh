#!/bin/bash
# Build the macOS Unix helpers from dappermint/FEX without its Linux/Windows
# top-level configure. These helpers do not contain the PE translators.
set -euo pipefail

SRC="${FEX_SRC:?set FEX_SRC to a checkout of dappermint/FEX}"
OUT="${1:?output directory}"
COMMIT=$(git -C "$SRC" rev-parse HEAD)
SOURCE="$SRC/Source/Windows/UnixLib/FEXUnixLib.cpp"
[ -f "$SOURCE" ] || { echo "missing FEX Unix helper source: $SOURCE" >&2; exit 1; }
[ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] || {
    echo "FEX macOS helpers require a native arm64 macOS host" >&2; exit 1;
}
[ ! -e "$OUT" ] || { echo "output directory already exists: $OUT" >&2; exit 1; }
mkdir -p "$OUT"
for name in arm64ecfex wow64fex; do
    library="$OUT/lib$name.so"
    clang++ -arch arm64 -std=c++20 -O2 -Wall -Wextra -Werror -dynamiclib \
        "-Wl,-install_name,@loader_path/lib$name.so" "$SOURCE" -o "$library"
    codesign -s - "$library"
    codesign --verify --strict "$library"
    [ "$(lipo -archs "$library")" = arm64 ] || { echo "unexpected library architecture" >&2; exit 1; }
done
cp "$SRC/LICENSE" "$OUT/LICENSE.FEX"
cat > "$OUT/SOURCE.txt" <<EOF_SOURCE
FEX_REPOSITORY=https://github.com/dappermint/FEX
FEX_COMMIT=$COMMIT
FEX_SRC=$SRC
TARGET=macOS-arm64-unix-helpers
TRANSLATORS_INCLUDED=no
EOF_SOURCE
