# KosmicKrisp local test results — 2026-09-27

The experimental x86_64 bundle builds and passes basic Vulkan device creation
and Win32 presentation tests on this machine. Upstream DXVK remains blocked by
missing geometry shaders and transform feedback.

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
