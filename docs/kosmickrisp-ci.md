# KosmicKrisp CI

New runtimes use layout v2: Khronos Vulkan Loader, KosmicKrisp and upstream
DXVK in `DXVK3/{x64,x32}`. There is no MoltenVK or legacy DXVK packaging lane.
Old releases, installed bottles and the v1 catalog are preserved.

## Required job graph

1. Shared static QA and the hub unit suite gate the build. Content-addressed
   Wine, payload, sysroot/tools and Mesa/loader components build or restore
   independently. DXVK downloads occur in the payload layer.
2. Hosted macOS assembles a fresh runtime, compiles the probes and validates
   dependency closure, deployment floor, media, networking and base Wine. It
   packages an inventory and the archive digest. Assembly does not execute GPU
   workloads or silently skip required graphics evidence.
3. The pinned Whisky consumer downloads those exact bytes and runs its complete
   suite, including the layout contract and runtime manifest tests.
4. Separate trusted physical macOS 26 and newer-OS hosts validate the same
   archive in a relocated path containing spaces. Missing/corrupt loaders and
   invalid or empty developer overrides must fail Vulkan without fallback;
   base Wine must still operate when Vulkan is absent.
5. Native and 32/64-bit Windows probes require the actual KosmicKrisp device,
   compute readback, geometry and tessellation rendering/side effects, and
   windowed, resized, borderless-fullscreen and restored presentation. Upstream
   DXVK D3D9/10/11 device probes and D3D11 constant-array readback require the
   actual DXVK version and KosmicKrisp identity in logs. These focused fixtures
   do not establish general shader conformance or exclusive-fullscreen support.
6. A pinned licensed-game campaign covers Hades Vulkan and DXVK, Portal 2
   32-bit D3D9, Skywalker gameplay and Steam CEF GPU compositing without changing
   the game backend. Frozen 1280x720/VSync-off settings, two warmups and three
   measured repetitions compare the candidate against the previous validated
   runtime. Repeatable losses over 5% mean FPS or 10% p99 frame time block
   promotion. Focus loss, sleep and invalid capture cannot count as success.
7. Publication explicitly requires the build, consumer and both physical
   readiness results. `WHISKY_LAYOUT_V2_AVAILABLE` additionally requires a
   compatible Whisky release. Publication updates only the opt-in v2 catalog
   and refuses to overwrite a runtime version with different bytes.

Configure `MACOS_GPU_RUNNER_26`, `MACOS_GPU_RUNNER_NEWER`,
`MACOS_GPU_CAMPAIGN` and `MACOS_GPU_CAMPAIGN_SHA256` for trusted physical
validation. Missing hosts or licensed fixtures are blockers, not passing smoke
tests. Each lane checks only its own runner label. An unconfigured lane fails
its gate on a Linux runner, and the readiness job reports every lane's missing
evidence. The checked-in single-game plan is not a provisioned campaign. See
[runtime layout v2](runtime-layout-v2.md) for the full evidence schema and
[cross-repository CI](ci-integration.md) for pins and dispatches.

Whisky uses a bounded `--device-only` probe for availability checks; the physical
release gate runs the full shader and presentation workloads. Installation and
supported non-Vulkan paths remain available without a usable Vulkan device.

## Local verification

```sh
python3 -m unittest discover -s tests -p 'test_kosmickrisp*.py' -v
actionlint
```

The committed compute shader fixture was generated with glslang 16.6.0:

```sh
glslangValidator -V --target-env vulkan1.0 --vn kosmickrisp_compute_spv \
  tests/kosmickrisp_compute.comp -o tests/kosmickrisp_compute_spv.h
```

The geometry shader fixtures can be regenerated with the same glslang tool:

```sh
for stage in vert tesc tese geom frag; do
  glslangValidator -V --target-env vulkan1.0 --vn "kk_$stage" \
    "tests/kosmickrisp_geometry/draw.$stage" \
    -o "tests/kosmickrisp_geometry/${stage}_spv.h"
done
```

Geometry invocations may be replayed under Vulkan's
[shader execution rules](https://docs.vulkan.org/spec/latest/chapters/shaders.html#shaders-geometry-execution).
The fixture records raw invocation counts, but does not require exactly one
invocation per primitive. An atomic bitset guards the counted buffer/image
updates so they occur once per input primitive (or input patch with tessellation).
The test checks exact green RGBA8 pixels, the primitive-ID mask, the guarded
counts, per-ID image-store values, and the minimum raw invocation count. It also requires zero geometry
side effects in the adjacency case without a GS.

Earlier extended GPU probes passed locally on macOS 27.2 through the existing Wine
runtime. That does not replace execution on a physical macOS 26 runner or
establish that the new patched Wine artifact has passed GPU validation. See [local results](kosmickrisp-test-results.md).
