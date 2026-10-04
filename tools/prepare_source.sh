#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
# CrossOver vendors its compatible FAudio revision in the winecx
# tree. Overlaying a newer upstream release can break that source
# combination, so verify the vendored version instead.
ver() { grep -oE "FAUDIO_${1}_VERSION[[:space:]]+[0-9]+" \
          winecx/libs/faudio/include/FAudio.h | grep -oE '[0-9]+$'; }
got="$(ver MAJOR).$(ver MINOR)"
want="${FAUDIO_VERSION%%.*}.$((10#${FAUDIO_VERSION##*.}))"
[ "$got" = "$want" ] || { echo "::error::faudio headers say $got, not $want"; exit 1; }
echo "faudio: $FAUDIO_VERSION (in-tree)"
# committed in the winecx branch on this lane; the glob guard keeps
# an empty patches/ from failing the loop
for p in "$PWD"/patches/*.patch; do
  [ -e "$p" ] || { echo "no out-of-tree patches"; break; }
  echo "applying $(basename "$p")"
  git -C winecx apply --verbose "$p"
done

if [ "${KOSMICKRISP_ENABLED:-false}" = true ]; then
    git -C winecx apply --check ../runtime/kosmickrisp/wine-loader.patch
    git -C winecx apply ../runtime/kosmickrisp/wine-loader.patch
fi
