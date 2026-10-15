#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
cp -R payload/kosmickrisp Libraries/Wine/lib/kosmickrisp
mkdir -p Libraries/Wine/lib/kosmickrisp/tests
test -x Libraries/Wine/lib/kosmickrisp/tests/host-probe
install -m 755 runtime/kosmickrisp/wine-kosmickrisp Libraries/Wine/bin/wine-kosmickrisp
# Keep real device enumeration strict when assembling an experimental runtime.
unset VK_ICD_FILENAMES VK_ADD_DRIVER_FILES VK_LOADER_DRIVERS_SELECT VK_LOADER_DRIVERS_DISABLE
VK_DRIVER_FILES="$PWD/Libraries/Wine/lib/kosmickrisp/kosmickrisp_icd.json" \
  Libraries/Wine/lib/kosmickrisp/tests/host-probe \
  "$PWD/Libraries/Wine/lib/kosmickrisp/libvulkan.1.dylib" \
  2>&1 | tee Libraries/Wine/lib/kosmickrisp/host-probe.txt
probe_dir="$RUNNER_TEMP/kosmickrisp-pe"
mkdir -p "$probe_dir"
for target in x86_64 i686; do
  "$target-w64-mingw32-clang" -Wall -Wextra -Werror \
    -I"$PWD/payload/kosmickrisp/headers" \
    tests/kosmickrisp_probe.c -o "$probe_dir/$target.exe"
  cp "$probe_dir/$target.exe" "Libraries/Wine/lib/kosmickrisp/tests/$target.exe"
  "$target-w64-mingw32-clang" -O2 tests/d3d11feat.c -ld3d11 -ldxgi -ldxguid -luuid \
    -o "Libraries/Wine/lib/kosmickrisp/tests/d3d11-$target.exe"
  "$target-w64-mingw32-clang" -O2 tests/d3d9feat.c -ld3d9 \
    -o "Libraries/Wine/lib/kosmickrisp/tests/d3d9-$target.exe"
  WINEPREFIX="$RUNNER_TEMP/kosmickrisp-prefix" WINEDEBUG=-all \
    Libraries/Wine/bin/wine-kosmickrisp "$probe_dir/$target.exe" --present \
    2>&1 | tee "Libraries/Wine/lib/kosmickrisp/wine-$target-probe.txt"
done
rm -rf Libraries/Wine/lib/kosmickrisp/headers
# Upstream DXVK for KosmicKrisp ships beside Wine, with the per-prefix
# launcher and its transactional install helper.
install -m 755 runtime/kosmickrisp/wine-kosmickrisp-dxvk Libraries/Wine/bin/wine-kosmickrisp-dxvk
mkdir -p Libraries/Wine/share/kosmickrisp
install -m 644 runtime/kosmickrisp/dxvk-prefix.py Libraries/Wine/share/kosmickrisp/dxvk-prefix.py
bash runtime/kosmickrisp/package-dxvk.sh Libraries/DXVK3
(cd Libraries/DXVK3 && shasum -a 256 -c SHA256SUMS)
