#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
[ ! -e Libraries/Wine/lib/kosmickrisp ] && [ ! -L Libraries/Wine/lib/kosmickrisp ] || {
  echo "::error::refusing to merge a stale Vulkan driver into the runtime"; exit 1;
}
cp -R payload/kosmickrisp Libraries/Wine/lib/kosmickrisp
mkdir -p Libraries/Wine/lib/kosmickrisp/tests
test -x Libraries/Wine/lib/kosmickrisp/tests/host-probe
install -m 755 runtime/kosmickrisp/wine-kosmickrisp Libraries/Wine/bin/wine-kosmickrisp
probe_dir="$RUNNER_TEMP/kosmickrisp-pe"
mkdir -p "$probe_dir"
for target in x86_64 i686; do
  "$target-w64-mingw32-clang" -Wall -Wextra -Werror \
    -I"$PWD/payload/kosmickrisp/headers" \
    tests/kosmickrisp_probe.c -o "$probe_dir/$target.exe"
  cp "$probe_dir/$target.exe" "Libraries/Wine/lib/kosmickrisp/tests/$target.exe"
  "$target-w64-mingw32-clang" -O2 tests/d3d11feat.c -ld3d11 -ldxgi -ldxguid -luuid \
    -o "Libraries/Wine/lib/kosmickrisp/tests/d3d11-$target.exe"
  "$target-w64-mingw32-clang" -O2 tests/d3d11_constants.c -ld3d11 -ld3dcompiler -ldxgi -ldxguid -luuid \
    -o "Libraries/Wine/lib/kosmickrisp/tests/d3d11-constants-$target.exe"
  "$target-w64-mingw32-clang" -O2 tests/d3d10feat.c -ld3d10 \
    -o "Libraries/Wine/lib/kosmickrisp/tests/d3d10-$target.exe"
  "$target-w64-mingw32-clang" -O2 tests/d3d9feat.c -ld3d9 \
    -o "Libraries/Wine/lib/kosmickrisp/tests/d3d9-$target.exe"
done
rm -rf Libraries/Wine/lib/kosmickrisp/headers
# Upstream DXVK for KosmicKrisp ships beside Wine, with the per-prefix
# launcher and its transactional install helper.
install -m 755 runtime/kosmickrisp/wine-kosmickrisp-dxvk Libraries/Wine/bin/wine-kosmickrisp-dxvk
mkdir -p Libraries/Wine/share/kosmickrisp
install -m 644 runtime/kosmickrisp/dxvk-prefix.py Libraries/Wine/share/kosmickrisp/dxvk-prefix.py
(cd Libraries/DXVK3 && shasum -a 256 -c SHA256SUMS)
