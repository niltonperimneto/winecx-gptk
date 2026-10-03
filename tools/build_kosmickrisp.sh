#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
python3 -m unittest discover -s tests -p 'test_kosmickrisp*.py' -v
brew install cmake ninja pkg-config llvm spirv-tools spirv-llvm-translator libclc python@3.13
"$(brew --prefix python@3.13)/bin/python3.13" -m venv "$RUNNER_TEMP/kosmickrisp-python"
source "$RUNNER_TEMP/kosmickrisp-python/bin/activate"
python3 -m pip install meson==1.9.1 mako==1.3.10 packaging==25.0 PyYAML==6.0.3
llvm_prefix=$(brew --prefix llvm)
export PATH="$llvm_prefix/bin:$PATH"
bash runtime/kosmickrisp/build.sh "$RUNNER_TEMP/kosmickrisp-build" "$PWD/payload/kosmickrisp"
# Test in a relocated path with spaces, using the x86_64 process ABI.
probe_dir="$RUNNER_TEMP/kosmickrisp relocated"
mkdir -p "$probe_dir"
cp -R payload/kosmickrisp "$probe_dir/driver"
/usr/bin/clang -arch x86_64 -Wall -Wextra -Werror \
  -I"$RUNNER_TEMP/kosmickrisp-build/headers/include" \
  tests/kosmickrisp_probe.c -o "$probe_dir/host-probe"
unset VK_ICD_FILENAMES VK_ADD_DRIVER_FILES VK_LOADER_DRIVERS_SELECT VK_LOADER_DRIVERS_DISABLE
VK_DRIVER_FILES="$probe_dir/driver/kosmickrisp_icd.json" \
  "$probe_dir/host-probe" "$probe_dir/driver/libvulkan.1.dylib" \
  2>&1 | tee payload/kosmickrisp/host-probe.txt
