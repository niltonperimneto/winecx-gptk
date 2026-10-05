# KosmicKrisp local test results — 2026-09-27

The experimental x86_64 bundle builds and passes Vulkan shader/readback and
Win32 presentation tests on this machine. The MR !44786 follow-up below adds
geometry shaders; upstream DXVK remains blocked by non-solid fill and transform
feedback. Earlier results below describe the unpatched baseline.

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


## Mesa MR !44786 integration (2026-09-28)

Integrated all six upstream commits through
`0741187d341de5b3df969f8d67024e6ba261ddcf` as an attributed vendored patch.
The patch applies cleanly to the existing Mesa `8b06c1fef1` pin, without changing
the `a82cadb14c` recipe pin. Its SHA-256 is
`fd87dd137cb92e27c9e93b364df46ec550b4b55f5d09d1839c14ebbaa8e36038`.
Both the patch and its provenance are included in the bundle.

Built in a fresh work directory, separate from the independently updated local
shadexternals cache. The source patch helper also recognized the built source as
already patched. All 34 Python tests passed, including corruption, wrong-base,
staged/unstaged/untracked-change rejection and idempotence tests.

| Check | Result |
|---|---|
| Fresh x86_64 driver/loader build, signatures and dependency audit | Passed |
| Host probe under Rosetta from a relocated path with spaces | Passed |
| x86_64 and i686 Wine compute readback | Passed |
| Geometry rendering: exact 8x8 RGBA8 image | Passed on host and both PE architectures |
| Triangle adjacency without a geometry shader | Passed on host and both PE architectures |
| Tessellation to geometry: two patch IDs, exact image | Passed on host and both PE architectures |
| Guarded buffer/image atomics and per-ID image stores | Passed on host and both PE architectures |
| Windowed, resized, borderless fullscreen and restored presentation | Passed on both PE architectures |
| DXVK 2.4 and 3.1.1, D3D9/D3D11, both architectures | Initialization failed |
| Hades Vulkan startup | Loaded Tartarus, then clean exit 0 after 90.69 seconds |

The driver reports `geometryShader=1`, `fillModeNonSolid=0`, and no
`VK_EXT_transform_feedback`. DXVK 3.1.1 explicitly logs rejection for missing
`fillModeNonSolid`, followed by no adapters found. The CI fixture remains DXVK
2.4; the local 3.1.1 run is additional evidence, not a change of runtime default.

An initial test incorrectly assumed geometry shaders execute exactly once per
primitive. It observed six raw invocations for two triangles and 36 for twelve
tessellated triangles. Vulkan permits repeated invocations, so this alone is not
a driver defect. The corrected fixture uses an atomic bitset to guard each
logical update and verifies exactly two buffer/image updates and ID mask `0x3`.
Raw invocation counts remain in the logs. See the
[shader execution rules](https://docs.vulkan.org/spec/latest/chapters/shaders.html#shaders-geometry-execution).

Hades used the existing Wine 4.7.51 (`wine-11.17`) runtime, the harness-owned
`kk-prefix`, and the legacy loader override. The NVAPI disable workaround was
retained. The driver path in the loader log identifies the new bundle. The game
log records starting a new game, loading Tartarus, pause/exit screens, profile
writes, and orderly shutdown. This is startup evidence; no screenshot comparison,
combat/audio acceptance, or frame-time benchmark was collected for this run.
`gameplay_verified` remains false. The installed runtime was not replaced.

Evidence is under `~/Library/Caches/winecx-kosmickrisp-mr44786/`:
`build.log`, `bundle/`, `host.log`, `wine-x86_64.log`, `wine-i686.log`,
`dxvk-2.4/`, `dxvk-3.1.1/`, and `hades/`. The initial counter diagnostic logs are
retained separately. This macOS 27.2 run does not replace the macOS 26 packaged
Wine CI gate, and it does not establish DXVK or full gameplay readiness.
