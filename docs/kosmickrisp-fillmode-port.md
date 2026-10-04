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
