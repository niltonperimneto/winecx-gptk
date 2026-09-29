# Upstream Mesa update — 2026-09-29

The experimental runtime now pins upstream Mesa main at
`fe554882e4f06cdd2579a77b37b04de605111a28`, fetched from
https://gitlab.freedesktop.org/mesa/mesa.git, and the shadexternals build recipe
at `bac93e022479af8e53f608b355aab7ce4f235c9b`.
The Mesa source pin is independent of the recipe's fork/submodule pin.
The existing six-commit geometry shader patch from MR !44786 applies cleanly
and is retained with its original digest and attribution.

[LunarG's announcement](https://www.lunarg.com/kosmickrisp-achieves-vulkan-1-4-conformance-on-apple-silicon/)
reports Vulkan 1.4 conformance for KosmicKrisp. This repository builds a custom
x86_64 driver with an extra patch; no full CTS run or conformance submission
was performed for this build. Version metadata is not a substitute for CTS.

## Local validation

Built from a fresh source/build directory on macOS 27.2, targeting macOS 26.
The existing Wine 11.17 runtime (4.7.51) selected the new loader through
`CX_LIBVULKAN`; this does not replace the packaged, patched Wine CI validation.
The installed runtime and normal backend were not replaced.

- x86_64 driver/loader build, signing, and dependency audit: passed.
- Relocated host probe under Rosetta: passed.
- x86_64 and i686 Wine probes: passed.
- API version: `1.4.363`; driver-reported conformance: `1.4.6.2`.
- Compute, geometry, adjacency-without-GS, and tessellation-to-geometry
  rendering/readback: passed on all three paths.
- Windowed, resized, borderless-fullscreen, restored presentation: passed on
  both Wine architectures.
- Stock DXVK 2.4 D3D9/D3D11 initialization: failed (exit 1) on both
  architectures; DXVK version confirmed in the new logs.
- Python harness tests: 34 passed; shell syntax and diff whitespace checks passed
  (excluding the verbatim upstream patch, whose blank context lines contain spaces).

The probes now request Vulkan 1.4 and reject a device exposing an older API.
They log the conformance version without claiming to run CTS.
`geometryShader=1`, `fillModeNonSolid=0`, and `VK_EXT_transform_feedback` remains
absent. The upstream DXVK readiness gate remains separate and unmet.

Evidence is retained under
`~/Library/Caches/winecx-kosmickrisp-upstream/`: `build.log`, `bundle/`,
`host.log`, `wine-x86_64.log`, `wine-i686.log`, `results.json`,
`dxvk-results.json`, and `dxvk-2.4/`.
