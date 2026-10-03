#!/bin/bash
# Exercise the real llvm-mingw driver aliases Wine selects, not a mock compiler.
set -euo pipefail
source "$(dirname "$0")/../tools/build/common.sh"
export CCACHE_DIR="$RUNNER_TEMP/pe-compiler-cache-test"
export CCACHE_MAXSIZE=100M
mkdir -p "$CCACHE_DIR" .build/pe-cache-test
bash tools/setup_mingw.sh --wrappers-only
export PATH="$PWD/ccache-bin:$PATH"
ccache --zero-stats
cat > .build/pe-cache-test/probe.cpp <<'CPP'
#include <windows.h>
#include <atomic>
std::atomic<unsigned> counter{0};
extern "C" unsigned probe() { return counter.fetch_add(sizeof(HWND)); }
CPP
for target in x86_64 i686; do
  for compiler in gcc clang g++ clang++; do
    driver="$target-w64-mingw32-$compiler"
    selected=$(command -v "$driver")
    [ "$selected" = "$PWD/ccache-bin/$driver" ] || { echo "Uncached compiler selected: $selected" >&2; exit 1; }
    case "$compiler" in
      gcc|clang) input=tests/wsarecvmsg.c ;;
      *) input=.build/pe-cache-test/probe.cpp ;;
    esac
    object=".build/pe-cache-test/$target-$compiler.o"
    for attempt in 1 2; do
      echo "$driver compilation $attempt"
      rm -f "$object"
      "$driver" -target "$target-windows" -fuse-ld=lld --no-default-config \
        -O2 -c "$input" -o "$object"
      test -s "$object"
    done
  done
done
ccache --print-stats > .build/pe-cache-test/stats.txt
ccache --show-stats | tee -a "$GITHUB_STEP_SUMMARY"
python3 - <<'PY'
from pathlib import Path
stats = {}
for line in Path('.build/pe-cache-test/stats.txt').read_text().splitlines():
    key, value = line.split()
    stats[key] = int(value)
hits = stats.get('direct_cache_hit', 0) + stats.get('preprocessed_cache_hit', 0)
if hits < 8:
    raise SystemExit(f'Expected at least 8 hits from repeated C/C++ PE compilations, got {hits}: {stats}')
print(f'Both PE architectures and all compiler aliases cached successfully: {hits} hits')
PY
