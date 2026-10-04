#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
usage() {
    echo 'Usage: tools/dev-build.sh [--fast] [--configure] [--module MAKE_TARGET]'
    echo 'First restore sysroot/tools OCI layers and prepare winecx; see docs/oci-build-system.md.'
}
fast=false
configure=false
module=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --fast) fast=true ;;
        --configure) configure=true ;;
        --module) module=${2:?MAKE_TARGET required}; shift ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
    shift
done
command -v ccache >/dev/null
[ -r store-outs.txt ] && [ -x build-tools/tools/winebuild/winebuild ] && [ -d winecx/.git ] || {
    echo 'Missing local foundation or Wine source. Restore OCI layers before building.' >&2
    exit 1
}
[ "$fast" != true ] || export OPT_LEVEL=fast
# Reconfigure on optimisation changes; never silently label O2 objects as O0.
previous_opt=$(cat .build/opt-level 2>/dev/null || true)
if [ -f build/Makefile ] && [ "$previous_opt" != "$OPT_LEVEL" ]; then
    # Make does not track command-line flags as object prerequisites.
    export PATH="$PWD/ccache-bin:$NIX_TOOL_PATH$PATH"
    make -C build clean
fi
if [ ! -f build/Makefile ] || [ "$configure" = true ] || [ "$previous_opt" != "$OPT_LEVEL" ]; then
    bash tools/setup_mingw.sh --wrappers-only
    bash tools/configure_wine.sh
    printf '%s\n' "$OPT_LEVEL" > .build/opt-level
fi
export PATH="$PWD/ccache-bin:$PWD/llvm-mingw-20240619-ucrt-macos-universal/bin:$NIX_TOOL_PATH$PATH"
if [ -n "$module" ]; then
    make -C build -j"$(sysctl -n hw.logicalcpu)" "$module"
else
    bash tools/make_wine.sh
    make -C build -j"$(sysctl -n hw.logicalcpu)" install-lib DESTDIR="$PWD/staging"
fi
