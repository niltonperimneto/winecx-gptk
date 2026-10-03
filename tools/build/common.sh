#!/bin/bash
# Shared environment for the same scripts in Actions and a local checkout.
BUILD_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$BUILD_ROOT" || exit 1
source tools/build/pins.env
mkdir -p .build
export GITHUB_ENV=${GITHUB_ENV:-$BUILD_ROOT/.build/environment}
export GITHUB_PATH=${GITHUB_PATH:-$BUILD_ROOT/.build/path}
export GITHUB_OUTPUT=${GITHUB_OUTPUT:-$BUILD_ROOT/.build/output}
export GITHUB_STEP_SUMMARY=${GITHUB_STEP_SUMMARY:-$BUILD_ROOT/.build/summary.md}
export GITHUB_WORKSPACE=${GITHUB_WORKSPACE:-$BUILD_ROOT}
export GITHUB_SHA=${GITHUB_SHA:-$(git rev-parse HEAD)}
export RUNNER_TEMP=${RUNNER_TEMP:-$BUILD_ROOT/.build/tmp}
mkdir -p "$RUNNER_TEMP"
# Environment files contain literal values, not executable shell code.
if [ -f "$GITHUB_ENV" ]; then
    while IFS='=' read -r name value; do
        [[ "$name" =~ ^[A-Za-z_][A-Za-z_0-9]*$ ]] || continue
        export "$name=$value"
    done < "$GITHUB_ENV"
fi
if [ -f "$GITHUB_PATH" ]; then
    while IFS= read -r directory; do export PATH="$directory:$PATH"; done < "$GITHUB_PATH"
fi
export OPT_LEVEL=${OPT_LEVEL:-standard}
export KOSMICKRISP_ENABLED=${KOSMICKRISP_ENABLED:-false}
export RUNTIME_SERIES=${RUNTIME_SERIES:-4.7}
export CCACHE_DIR=${CCACHE_DIR:-$HOME/.ccache}
export CCACHE_MAXSIZE=4G CCACHE_COMPILERCHECK=content
export CCACHE_BASEDIR="$BUILD_ROOT" CCACHE_NOHASHDIR=1 CCACHE_FILECLONE=1
export CCACHE_SLOPPINESS=time_macros,locale,include_file_mtime,include_file_ctime
