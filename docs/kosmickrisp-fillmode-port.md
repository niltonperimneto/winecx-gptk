# KosmicKrisp non-solid fill on the Mesa Vulkan 1.4 runtime

The imported Whisky runtime 4.7.54 was built from `98c0072`. Its bundled
`SOURCE.txt` names `44786-geometry-shaders.patch`, and its driver reports
`fillModeNonSolid=0`. It therefore cannot initialize upstream DXVK 3.1.1.
The fill-mode change existed separately on the repository's `kk/02-fill-mode`
branch (`55b311b`); it was omitted when the experimental runtime branch moved
to upstream Mesa `fe554882e4` and the geometry-shader merge-request patch.

This branch now carries `44786-geometry-fillmode.patch`, combining that Mesa
geometry-shader work with the local non-solid-fill change. The latter maps
`VK_POLYGON_MODE_LINE` to Metal's triangle line fill mode. Metal has no
equivalent point fill mode, so `VK_POLYGON_MODE_POINT` currently renders as
lines. This is an **experimental partial implementation**, not a claim of
complete Vulkan rasterization conformance. It is our local patch; we have not
verified the implementation details of CrossOver Preview's proprietary driver.

Local validation on an Apple A18 Pro with the rebuilt Mesa `fe554882e4`
bundle:

| Probe | Result |
|---|---|
| Vulkan API and feature query | 1.4.363; `geometryShader=1`, `fillModeNonSolid=1` |
| Compute, geometry, adjacency, tessellation readback | Passed |
| Upstream DXVK 3.1.1 D3D9, x86_64 and i686 | Created devices; exit 0 |
| Upstream DXVK 3.1.1 D3D11, x86_64 and i686 | Created feature-level 11_1 devices; exit 0 |
| Hades DX11 through DXVK 3.1.1 | Renderer loaded and swapchain created; process still running at 60-second deadline |

Evidence is in `~/Library/Caches/winecx-kosmickrisp-fillmode-current/` and
its `host-probe.log` and `hades-dx11/` logs. The tests used Wine from
4.7.54 with the newly built KosmicKrisp bundle and an isolated prefix already
containing upstream DXVK. Window capture failed during the Hades run, so
visual correctness remains unverified.

The installed Whisky Preview client already has a "DXVK 3 + KosmicKrisp"
backend. It discovers the upstream DLLs at `DXVK3/`, while the imported
4.7.54 runtime shipped them at `DXVK-Upstream/`. The next runtime artifact
uses the client layout. Meanwhile, the installed 4.7.54 runtime now has a
local overlay: the rebuilt driver is in `Wine/lib/kosmickrisp/`, DXVK 3.1.1
is in `DXVK3/`, and its opt-in launcher uses that directory. The original
driver and launcher are backed up at the path recorded in
`~/Library/Caches/winecx-kosmickrisp-fillmode-current/whisky-4.7.54-backup-path.txt`.
The installed runtime reports `fillModeNonSolid=1`, and its D3D11 probe creates
a DXVK 3.1.1 feature-level 11_1 device. Reimporting the original 4.7.54
archive would replace this local overlay.


## Geometry side-effect follow-up (2026-10-01)

Both `44786-geometry-fillmode.patch` and the active build patch
`44786-geometry-fillmode-shader-cache-gpl.patch` include this follow-up. It retains the non-solid fill,
persistent shader cache and deferred graphics-pipeline-library additions and
integrates these upstream MR !44786 changes:

- `e11cdcbf24c3034cfa9fde2102c7ddbd28157791`: optionally run geometry side effects
  in Poly's main shader.
- `2d1ea84b3ea481d312a3a022f2463e9acb905b18`: enable that path for KosmicKrisp.

For shaders whose rasterized output does not depend on their stores or atomics,
the compute pass executes those side effects and the rasterization shader has
them removed. This also moves work that only feeds side effects out of the
rasterization vertex shader. Output-dependent side effects retain the upstream
fallback behavior. A local compatibility wrapper preserves the old Poly API
for other drivers; their source files are unchanged.

The geometry fixture now checks unguarded buffer/image atomic counts: two for
two input triangles and twelve for two tessellated patches. Image stores remain
guarded by primitive ID to avoid overlapping writes. A fourth draw uses
`VK_POLYGON_MODE_LINE` with a geometry shader and requires rendered edges and a
clear triangle interior. These checks also run through normal, LTO and nested
pipeline-library links. Point-mode rendering remains the earlier experimental
line fallback; these fixes do not implement correct polygon point mode.


Validation of the updated composite bundle on macOS 27.2 / Apple A18 Pro:

- Fresh x86_64 build, bundled dependency audit and signatures passed.
- Host readback passed with monolithic pipelines and all three GPL link modes.
- x86_64 and i686 Wine readback and all four presentation modes passed.
- Upstream DXVK 3.1.1 D3D9 and D3D11 device probes passed on both architectures.
- 39 Python runtime tests passed. The patch helper accepted the updated source
  as already applied.

Evidence is under `~/Library/Caches/winecx-kosmickrisp-gs-side-effects/`.
The former composite bundle produces raw counts of 6, 36 and 3 for the ordinary,
tessellated and wireframe cases; the updated bundle produces 2, 12 and 1.
This verifies the opted-in compute path for output-independent side effects.
Vulkan permits repeated invocations generally; the former counts alone were
not a conformance failure. No installed runtime was overlaid by this update.


Cold/warm/corrupt/disabled cache validation passed on the follow-up run:
89 hits / 17 misses cold, 106 hits / zero misses warm, and safe recompilation
of 106 truncated entries. The initial corrupt run completed all GPU readbacks
but timed out during shutdown after 120 seconds; the same check then completed
in 1.86 seconds. Both attempts are retained in `cache-validation/` and
`cache-validation-recheck/`. The shutdown timeout did not reproduce and remains
an observed limitation rather than a diagnosed or fixed cache defect.
