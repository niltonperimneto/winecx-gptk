#!/bin/bash
# Rebuild the x86_64 driver, bundle it, run Portal 2 d3d9 cold + 2x warm with
# the shader cache trace, then classify the misses.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MESA="${MESA:-$HOME/Projects/mesa}"
BUILD="${BUILD:-$HOME/Projects/kk-shader-build/fastlink-x86_64}"
RUNTIME="${RUNTIME:-$HOME/Library/Application Support/com.dappermint.WhiskyPreview/Runtimes/winecx-gptk-4.7.71}"
BOTTLE="${BOTTLE:-$HOME/Library/Containers/com.dappermint.WhiskyPreview/7B23E2E8-4D1B-451A-A24A-95A4BB90E13F}"
WORK="${WORK:-$HOME/Library/Caches/kk-stutter}"
BUNDLE="${BUNDLE:-$WORK/bundle-fastlink}"
GAME="${GAME:-portal2-d3d9}"
RUNS="${RUNS:-cold,warm,warm}"

stamp="$(date +%Y%m%d-%H%M%S)"
report="$WORK/cache-trace-$stamp.txt"
marker="$(mktemp)"

echo "== build"
PATH=/opt/homebrew/opt/llvm/bin:$PATH ninja -C "$BUILD"

echo "== bundle"
python3 "$HERE/stutter.py" bundle --build-dir "$BUILD" --runtime "$RUNTIME" \
   --source "$MESA" --out "$BUNDLE"

echo "== run $GAME ($RUNS)"
python3 "$HERE/stutter.py" run --runtime "$RUNTIME" --bundle "$BUNDLE" \
   --bottle "$BOTTLE" --game "$GAME" --work "$WORK" --runs "$RUNS" --cache-log \
   --via-steam

runs=()
while IFS= read -r dir; do
   runs+=("$dir")
done < <(find "$WORK/runs" -mindepth 1 -maxdepth 1 -type d -name "*-$GAME-*" \
            -newer "$marker" | sort)
rm -f "$marker"

if [ "${#runs[@]}" -lt 2 ]; then
   echo "expected at least 2 new runs, found ${#runs[@]}" >&2
   exit 1
fi

{
   echo "bundle: $(tr '\n' ' ' < "$BUNDLE/SOURCE.txt")"
   echo
   echo "== frame/compile summary"
   python3 "$HERE/stutter.py" analyze "${runs[@]}"
   echo
   echo "== cache misses"
   python3 "$HERE/cache_misses.py" "${runs[@]}"
} | tee "$report"

echo
echo "report: $report"
