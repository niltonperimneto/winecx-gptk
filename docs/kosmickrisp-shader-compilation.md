# Shader compilation work — 2026-09-29

## Implemented

The pinned Mesa patch now creates KosmicKrisp's persistent disk cache and its
implicit Vulkan pipeline cache. Applications passing a null pipeline-cache
handle can therefore reuse the driver's serialized shaders between processes.
The cache identity includes the driver build, GPU family, MSL version, and
compiler workaround settings. The implicit memory cache uses weak references.
This persists preprocessed shaders/MSL; it does not add a Metal binary archive,
and restoring an entry can still require Metal compilation.

The upstream DXVK launcher keeps caches in
`WINEPREFIX/ShaderCaches/kosmickrisp/{dxvk,mesa}` and preserves explicit path and
disable overrides. The companion Whisky changes use `DXVK_SHADER_CACHE`, wire
the driver's disable switch to the same setting, and create the same folders.
They also handle inherited bottle settings when a program changes backend.
The current client tree calls the upstream DXVK/KosmicKrisp backend `DXVK`.

## GPL is preliminary, not a completed DXVK optimization

The driver supports creating and combining graphics pipeline libraries by
retaining preprocessed NIR and compiling the full Metal pipeline at final link.
The opt-in shared Mesa runtime path handles normal links, LTO links, and nested
libraries; other drivers keep their existing behavior.

Both `graphicsPipelineLibraryFastLinking` and
`graphicsPipelineLibraryIndependentInterpolationDecoration` remain false.
DXVK 3.1.1 logs **Graphics pipeline libraries not supported**, because its
`DxvkDevice::canUseGraphicsPipelineLibrary` requires independent interpolation
decorations. No property was enabled just to bypass that check. Step 3 is
unfinished: it needs interpolation correctness coverage and implementation,
followed by genuinely reusable Metal stage compilation/fast linking. The
current implementation does not establish reduced first-use gameplay stutter.

## Validation

- Cold host process: 64 hits, 18 misses; second process: 82 hits, zero misses.
- Truncated disk entries: safe recompilation and correct readback.
- Disabled caching: correct readback and no disk cache files.
- Compute and graphics readback pass for monolithic pipelines and all three
  library modes, including geometry, adjacency without GS, and tessellation/GS.
- Both x86_64 and i686 Wine probes pass those checks and windowed, resized,
  borderless, and restored presentation. D3D9 and D3D11 device probes pass with
  upstream DXVK 3.1.1 on both architectures.
- Hades DX11 reaches launch-screen initialization, creates its swapchain, and
  stays alive for a bounded 30-second test in a disposable prefix. No gameplay
  correctness, frame-time improvement, or Vulkan conformance claim follows.
- 39 runtime Python tests pass. The companion Whisky environment suite has
  46 passing XCTest cases and 14 passing Swift Testing cases. App, command-line,
  and thumbnail targets build; existing unrelated compiler warnings remain.
  The build used `SKIP_SWIFTLINT_BUILD_PHASE=YES` because of the existing lint
  integration issue.

`runtime/kosmickrisp/shader_cache.py` repeats the cold, warm, corrupt, and disabled
tests using temporary cache directories and retains logs and a JSON report.
The experimental build and downloaded-runtime validation jobs run it on Metal
hardware. The latter also enables GPL in both Wine probes and uploads cache
evidence. These workflow changes have been tested locally, not run remotely.

## Local installation

The new driver and launcher are overlaid on the installed Whisky Preview runtime
`winecx-gptk-4.7.54`. Its published manifest remains unchanged, so this local
overlay is not a release artifact and a reinstall replaces it.

Evidence, the signed client build, and rollback copies are under
`~/Library/Caches/winecx-kosmickrisp-shaders/`; `installed.json` records exact
paths. The client build is staged as `Whisky Preview.app` there. The running
Whisky client canceled the quit request, so it was not replaced. Existing Wine
processes retain the previous mapped driver until restarted.

To rerun the host gate against a bundle:

```sh
python3 runtime/kosmickrisp/shader_cache.py \
  --probe /absolute/path/to/host-probe \
  --loader /absolute/path/to/bundle/libvulkan.1.dylib \
  --icd /absolute/path/to/bundle/kosmickrisp_icd.json \
  --output /absolute/path/to/evidence
```


## Geometry side-effect update (2026-10-01)

The composite patch now includes MR !44786's two compute-side-effect changes
through `2d1ea84b3ea481d312a3a022f2463e9acb905b18`. The driver opts in while a
legacy Poly API wrapper keeps other callers compatible. The cache tests now
require exact unguarded geometry atomic counts and geometry wireframe readback,
in addition to the existing cache and pipeline-library checks. A fresh build
uses the updated patch digest in its build-directory identity. This update is
validated as a separate bundle rather than replacing the installed runtime.


The updated host probe passes cold, warm, corrupt and disabled cache checks,
and both PE architectures pass all three GPL modes plus DXVK device creation.
One initial corrupt-cache shutdown timeout did not reproduce on the follow-up
run; both logs are retained under `winecx-kosmickrisp-gs-side-effects/`.
