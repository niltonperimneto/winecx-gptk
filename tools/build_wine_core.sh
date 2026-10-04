#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
bash tools/configure_wine.sh
bash tools/make_wine.sh
export PATH="$PWD/ccache-bin:$NIX_TOOL_PATH$PATH"
make -C build -j"$(sysctl -n hw.logicalcpu)" install-lib DESTDIR="$PWD/staging"
