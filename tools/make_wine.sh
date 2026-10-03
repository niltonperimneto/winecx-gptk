#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
export PATH="$PWD/ccache-bin:$NIX_TOOL_PATH$PATH"
cd build
# the runner has few cores and much of the work is i/o bound behind
# winebuild, so oversubscribing by half keeps them fed
ncpu=$(sysctl -n hw.logicalcpu)
ccache -z >/dev/null
set -o pipefail
make -j"$(( ncpu + ncpu / 2 ))" 2>&1 | tee /tmp/make.log

# pinning the deployment target stops the binaries claiming to be
# newer, but not configure finding an API the SDK declares and the
# floor does not have: v4.0.1 linked pipe2, macOS 27 only, weakly, so
# ntdll.so loads on 26 and then calls a null pointer at the first
# server_pipe. build on a runner whose SDK matches the floor and this
# stays quiet.
if grep -q "has been marked as being introduced in macOS" /tmp/make.log; then
  syms=$(grep -oE "'[a-z_0-9]+' has been marked as being introduced in macOS [0-9.]+" /tmp/make.log | sort -u)
  # the self hosted lane is a newer macOS than the floor, so its SDK
  # always offers something and failing every push there would cost the
  # fast lane for nothing. so the build stays green and hands the
  # verdict to the publish job instead, which is the step that has to
  # care. only an explicit release build stops here.
  echo "shippable=false" >> "$GITHUB_OUTPUT"
  if [ "${OPT_LEVEL:-}" = "release" ]; then
    printf '%s\n' "$syms" | sed 's/^/::error::newer than the floor: /'
    echo "::error::a release cannot link these; build on a runner whose SDK matches $MACOSX_DEPLOYMENT_TARGET"
    exit 1
  fi
  printf '%s\n' "$syms" | sed 's/^/::warning::newer than the floor: /'
  echo "::warning::not shippable as built; publish will skip this run, a release needs the hosted lane"
fi
# per-run numbers, not lifetime ones: this is how we tell whether
# the restored cache actually did anything
{
  echo "### ccache"
  echo '```'
  ccache -s
  echo '```'
} >> "$GITHUB_STEP_SUMMARY"
