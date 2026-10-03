#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
component=${1:?usage: import_layer.sh COMPONENT EXPORTED_DIRECTORY}
package=${2:?exported directory required}
python3 tools/build/archive.py verify "$package" "$component"
zstd -dc "$package/layer.tar.zst" | python3 tools/build/archive.py check-tar
zstd -dc "$package/layer.tar.zst" | tar -xf -
if [ "$component" = sysroot ]; then
    nix-store --import < sysroot-closure.nar
    rm sysroot-closure.nar
    cat sysroot.env >> "$GITHUB_ENV"
    echo "$PWD/llvm-mingw-20240619-ucrt-macos-universal/bin" >> "$GITHUB_PATH"
fi
