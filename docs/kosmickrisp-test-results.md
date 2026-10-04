# KosmicKrisp local test results — 2026-09-27

The experimental x86_64 bundle builds and passes basic Vulkan device creation
and Win32 presentation tests on this machine. With the local fillModeNonSolid
patch (2026-09-29 entry), upstream DXVK 3.1.1 creates D3D9 and D3D11 (FL 11_1)
devices. Transform feedback is still missing, so D3D10/11 stream output is
unavailable.

## Environment and scope

- macOS 27.2 (26B5091g), SDK 27.0, Apple A18 Pro GPU, Metal 4.
- Mesa 26.3.0-devel at `8b06c1fef1ed316217b805d1068fc74afaa40438`.
- Vulkan loader and headers at the revisions in `runtime/kosmickrisp/pins.env`.
- Native build tools: LLVM 23.1.2, CMake 4.4.3, Meson 1.9.1, Python 3.13.15.
- Windows probes compiled with the workflow's llvm-mingw 20240619 UCRT toolchain.
- Wine tests used the existing 4.7.44 runtime reporting `wine-11.17`, with an
  isolated prefix. No installed runtime or game prefix was modified.

The existing runtime does not include the experimental `WINE_VULKAN_LIBRARY`
patch. These local Wine tests instead used its existing `CX_LIBVULKAN` override
with `CX_ACTIVE_GRAPHICS_BACKEND=wined3d`. This tests the Vulkan bridge and driver,
not the newly patched Wine binary or the entire CI-produced runtime. Launcher
environment/argument behavior is covered separately by its unit tests.

## Results

| Check | Result |
|---|---|
| Driver and loader source build | Passed after fixes below |
| Bundle architecture, signatures, dependency audit | Passed; all three dylibs are x86_64, minos 26.0 |
| Host probe under Rosetta, relocated path containing spaces | Passed |
| 64-bit Windows enumeration and device creation | Passed |
| 32-bit Windows enumeration and device creation through WoW64 | Passed |
| 64-bit Win32 surface, swapchain, GPU clear, and present | Passed |
| 32-bit Win32 surface, swapchain, GPU clear, and present | Passed |
| Follow-up: deterministic compute-shader readback, both PE architectures | Passed |
| Follow-up: windowed, resize, borderless fullscreen, restore, both PE architectures | Passed |
| Stock DXVK 2.4 D3D9/D3D11 initialization, both PE architectures | Failed (exit 1); DXVK v2.4 verified in logs |
| Launcher tests: relocation/arguments/environment, missing component, exit status | Passed |

Presentation success means the Vulkan calls returned success. This is not a
visual-image comparison. The added compute shader verifies four exact output
values, not general shader conformance.

Both host and Wine probes selected driver ID 28, `KosmicKrisp`, with these values:

| Capability | Observed |
|---|---|
| API version | 1.4.363 |
| maxPushConstantsSize | 256 |
| geometryShader | 0 |
| tessellationShader | 1 |
| shaderInt64 / shaderInt8 | 1 / 1 |
| descriptorIndexing / scalarBlockLayout / synchronization2 | 1 / 1 / 1 |
| VK_EXT_transform_feedback | Absent |

No feature masking was used. The probes deliberately report optional feature
gaps without treating device creation as proof of DXVK compatibility.

## Problems found and fixed

1. macOS's Python 3.9 failed Mesa configuration. The workflow now selects Python
   3.13 and the build script checks the minimum before downloading/building.
2. Setting only `CMAKE_OSX_ARCHITECTURES` left the loader using the ARM host's
   assembly selection. It now configures a Darwin/x86_64 cross-build with a fresh
   CMake cache; the successful build includes `unknown_ext_chain_gas_x86.S`.
3. Mesa's zlib fallback remained dynamic despite `--prefer-static`. Packaging
   now includes that exact x86_64 zlib, rewrites the reference to `@loader_path`,
   verifies/signs it, and includes its license.

## Evidence and next gates

Local artifacts and logs are retained under
`~/Library/Caches/winecx-kosmickrisp-test/`: `build-final.log`, `host-probe.log`,
`wine-x64-probe.log`, `wine-x86-probe.log`, `present-x86_64.log`,
`present-i686.log`, and `bundle/` (including source pins/tool versions).

Still required: a clean macOS 26 CI run of the patched Wine runtime, broader
shader/rendering correctness, complete version-specific
DXVK capability auditing, and game/performance tests. A minos 26.0 load command
does not prove runtime compatibility with macOS 26. No production migration or
upstream DXVK compatibility claim follows from these smoke tests.

## Hades Steam installation and first startup attempt (2026-09-28)

Located the Windows Steam installation in the local Whisky Preview bottle.
Steam build ID: `10929685`. Vulkan executable: `x64Vk/Hades.exe`, SHA-256
`f2aadbb0b730f3a6d116fc28bf2ea89e1d7aa89aa6ef1e388184a9b39034a43f`.
This identifies the tested executable, not a complete game-content manifest.

Ran with the existing Wine 11.17 runtime and `CX_LIBVULKAN` pointing to the
locally built KosmicKrisp loader, in a disposable prefix with local save folders.
The synthetic probes' `mscoree` disable override must not carry over to Hades:
its `BasecampBugReporter.Native.dll` imports that module. The first attempt
exited 255 with the override; enabling it allowed game startup.

The subsequent 45-second bounded run recorded `Created window app Hades`,
`Running Vulkan`, and `InputSystem Initialized` in Hades.log. Wine's loader log
recorded the experimental loader and KosmicKrisp ICD. The process did not exit
before the deadline and was terminated (harness code 124). No successful game
swapchain presentation, menu rendering, gameplay, or FPS result was established.
This is an inconclusive startup attempt, not a passing game benchmark or proof
that KosmicKrisp caused the startup stall.

Evidence is retained locally in
`~/Library/Caches/winecx-kosmickrisp-test/hades-startup/`: `result.json`,
`diagnostic.log`, `startup-mscoree.log`, and the isolated prefix's Hades.log.
The hosted CI runner still needs its own provisioned installation and harness.

## DXVK 3.1.1 and both Hades renderers (2026-09-28)

The upstream DXVK test fixture moved from 2.4 to 3.1.1 (`b1a1c99`). Same
KosmicKrisp bundle, now with the Wine 11.17 runtime from 4.7.51, again through
`CX_LIBVULKAN` in disposable prefixes.

| Check | Result |
|---|---|
| Stock DXVK 3.1.1 D3D9/D3D11 initialization, both PE architectures | Failed; DXVK v3.1.1 verified in logs |
| Hades Vulkan, `x64Vk/Hades.exe` | Menu, new run, and first room rendered; clean exit 0 after about 80 s |
| Hades DX11, `x64/Hades.exe` + DXVK 3.1.1 | Failed: `Could not create DXGI factory`, `Failed to initialize ForgeRenderer` |

DXVK 3.1.1 regressed further than 2.4 did. 2.4 created an adapter and then
rejected feature level 10_0 (no geometry shaders). 3.1.1 treats
`fillModeNonSolid` as a hard device requirement: it logs `Skipping: Device does
not support required feature 'fillModeNonSolid'` and reports no adapters. The
probe now prints that feature (KosmicKrisp: 0), and the validator lists it as
known-missing, ahead of geometryShader and VK_EXT_transform_feedback.

For the DX11 run, the DXVK DLLs went into the prefix's system32/syswow64 with
native overrides. Nothing was copied into the game directory. Hades did not
fall back to another renderer; its process stayed up with no window until the
90-second deadline. The Vulkan result is based on screenshots of gameplay
rendering, not on frame-time measurement. No FPS or MoltenVK comparison was
taken.

Evidence in `~/Library/Caches/winecx-kosmickrisp-test/`: `dxvk311-probes/`,
`hades-local/kk-05-vulkan/` (screenshots, Hades.log), `hades-local/dxvk311-dx11/`
(Hades_dxgi.log, Hades.log), and the `hades-run.sh` harness.

## KosmicKrisp bump to recipe `bac93e0` / Mesa `063dfae` (2026-09-28)

The pins moved to the recipe commit that pulls in geometry shader support. The
Mesa range adds `kk: Implement geometry shaders with poly`, `kk: Advertise
geometryShader`, sparse buffer binding, and exact-thread indirect dispatch.

The incremental rebuild reused a Meson configuration from the 2026-09-27 build.
That configuration still set `HAVE_ENDIAN_H`, so the build failed on
`endian.h`. A clean work directory, which is what CI uses, built without
changes. This build did not need the zlib bundling step; the dependency audit
still passed.

| Check | Result |
|---|---|
| Capabilities | `geometryShader=1` (was 0), `fillModeNonSolid=0`, VK_EXT_transform_feedback absent |
| Compute readback, Win32 present, all four presentation modes, both PE architectures | Passed, no regression |
| Stock DXVK 3.1.1 D3D9/D3D11, both PE architectures | Still fails: `Skipping: Device does not support required feature 'fillModeNonSolid'` |
| Hades Vulkan | Same as the previous build: menu, new game, and intro rendered; no new Wine or Hades errors |
| Hades DX11 + DXVK 3.1.1 | Still `Could not create DXGI factory`; same cause |

Geometry shaders are no longer a DXVK blocker at this pin. The remaining
blockers are `fillModeNonSolid`, which DXVK 3.x requires before it will create
any adapter, and VK_EXT_transform_feedback, which the driver only fills
property limits for. KosmicKrisp does not yet advertise the extension.

Evidence: `bundle-bac93e0/`, `build-bac93e0.log`, `kk-bac93e0-probes/`,
`hades-local/kk-06-vulkan/`, `hades-local/kk-06-dx11/`.

## Local fillModeNonSolid patch: DXVK 3.1.1 creates devices (2026-09-29)

`runtime/kosmickrisp/patches/0001-kk-expose-fillModeNonSolid-...patch`, applied
by `build.sh` on top of Mesa `063dfae`, maps `VkPolygonMode` onto Metal's
`setTriangleFillMode:`. Before this, KosmicKrisp never read the polygon mode
and left the feature unset. `VK_POLYGON_MODE_LINE` becomes
`MTLTriangleFillModeLines`. Metal has no point fill mode, so
`VK_POLYGON_MODE_POINT` is drawn as wireframe: the feature is advertised as a
partial implementation. Emulated geometry and tessellation stages rasterize
already-expanded triangles, so the mode applies to the primitives that reach
the rasterizer.

| Check | Result |
|---|---|
| Probe | `fillModeNonSolid=1` |
| Stock DXVK 3.1.1 D3D9/D3D11 initialization, both PE architectures | **Passed**: D3D9 device up; D3D11 feature level 11_1 |
| Hades DX11, `x64/Hades.exe` + DXVK 3.1.1 | **Renders**: DXGI factory, FL 11_1 device, first room with HUD |

DXVK 3.1.1 treats transform feedback as optional (`transformFeedback: 0`), so
missing stream output no longer blocks device creation; D3D10/11 stream output
will not work until it is implemented.

Not yet verified: that wireframe output looks correct. No test draws with
`VK_POLYGON_MODE_LINE` yet, including on emulated geometry/tessellation
draws, where shared edges of expanded triangles may be drawn twice.
`extendedDynamicState3PolygonMode` is still not advertised.

Evidence: `bundle-fillmode/`, `fillmode-probes/`,
`hades-local/kk-07-dx11-fillmode/`.
