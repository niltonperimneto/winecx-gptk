# KosmicKrisp CI

The build workflow now runs automatically on pushes to
`feat/kosmickrisp-experimental`. It can also be dispatched with the
`kosmickrisp` input enabled. The experimental branch always selects this lane,
even if the checkbox is left off. Experimental artifacts never reach the
release/catalog publishing job.

The hosted macOS 26 image used by the current CI run did not expose a working
Metal/Vulkan device. CI now compiles a small Metal device probe before the
KosmicKrisp build. When Metal is unavailable, it still builds and audits the
runtime artifact, then records a notice and skips GPU execution and the separate
validation/readiness jobs. Skipped GPU jobs are **not** evidence of runtime or
migration readiness. On a GPU-capable runner, probe failures stop the build
instead of being hidden by `tee`, and validation logs are uploaded even on
failure. A physical Apple Silicon macOS 26 runner is needed to complete the
full gate. See the [CI failure investigation](kosmickrisp-ci-failure-2026-09-29.md).

## Checks

1. **Build:** build the pinned x86_64 ICD, loader, and patched Wine on the hosted
   macOS 26 runner. Package the probe executables, shader fixture, and stock
   DXVK 2.4 test DLLs with the artifact. DXVK remains a test fixture; the shipped
   default DXVK directory is unchanged. Run the launcher and CI-harness unit tests.
2. **KosmicKrisp / macOS 26 packaged runtime:** download the resulting artifact
   on a separate hosted runner and extract it into a path with spaces. Verify
   the archive checksum and every file in `RuntimeManifest.json`. Refuse any OS
   major version other than 26, and record the actual OS/GPU details.
3. Run the host probe, then a negative test that points `WINE_VULKAN_LIBRARY` at
   a missing file. Require the expected load failure to prove the patched
   override is present. No legacy `CX_LIBVULKAN` fallback is set.
4. Run both 64-bit and 32-bit Windows probes through the packaged launcher.
   Require KosmicKrisp driver ID 28, device creation, a deterministic compute
   shader with exact CPU readback, geometry rendering and guarded buffer/image
   side effects, adjacency without GS, tessellation-to-GS primitive IDs, and
   swapchain recreation/presentation in
   windowed, resized, borderless-fullscreen, and restored modes. This does not
   test exclusive fullscreen or general shader conformance.
5. Execute upstream DXVK 2.4 D3D9/D3D11 initialization probes for both PE
   architectures. Use application-local DLLs and native-only overrides, require
   the DXVK version in its logs, and retain missing-feature evidence. These are
   focused initialization checks, not an exhaustive D3D feature-level audit.
6. **KosmicKrisp / migration readiness:** separately require successful runtime,
   shader-smoke, DXVK, and configured game evidence. A successful Vulkan smoke
   test cannot make this gate green while DXVK or game requirements are unmet.

The runtime check can pass while migration readiness fails. With the currently
patched Mesa driver, geometry shaders are exposed, but `fillModeNonSolid` and
transform feedback remain absent. Stock DXVK initialization still fails locally. The selected Hades test remains
blocked until its installation and gameplay harness are provisioned. This expected red readiness result keeps the missing
migration requirements visible without hiding successful runtime work.

Each subprocess has a timeout. Probe logs, source pins, capabilities, durations,
and `results.json` are uploaded as `kosmickrisp-validation-results`, including on
failure. The Wine prefix sits outside the diagnostics directory, and the upload
lists only result files and logs. Game/DXVK binaries are excluded. The build's existing probe logs remain available too.

## Configure the game benchmark

`runtime/kosmickrisp/game.json` selects **Hades (Windows)**. Its
`provisioned-game-plan` profile records the selection and reports a named blocked
result until the installation and gameplay harness are available; it does not
launch or download the game yet.

Use `x64Vk/Hades.exe` for the first native Vulkan/KosmicKrisp test. Use
`x64/Hades.exe` for a subsequent DirectX/upstream-DXVK test once the DXVK
capability gate passes. These are the renderer-specific Windows executables
listed in [Supergiant's Hades FAQ](https://www.supergiantgames.com/faqs/hades/).
The macOS game build does not exercise Wine. A Vulkan Hades pass alone cannot
satisfy the separate upstream DXVK readiness gate.

Provision a licensed Windows copy on a dedicated macOS 26 Apple Silicon runner,
record its exact build and file hashes, and use an isolated test prefix/save.
The current hosted job has no Hades installation. The gameplay harness still
needs a fixed save and input sequence, backend evidence, visual checks, and
frame-time capture with hardware-specific thresholds. Do not treat reaching the
menu or keeping the process alive as a gameplay/performance pass. No unattended
Hades benchmark flags or telemetry format have been established. Keep game files
and saves out of uploaded diagnostic artifacts.

The existing downloadable ZIP benchmark adapter remains available for other
redistributable fixtures. Its example contract is:

```json
{
  "name": "chosen-game-fixed-replay",
  "archive_url": "https://publisher.example/benchmark.zip",
  "archive_sha256": "<64 lowercase hexadecimal characters>",
  "executable": "benchmark/benchmark.exe",
  "arguments": ["--fixed-replay", "--exit-after-replay"],
  "timeout_seconds": 300,
  "success_pattern": "REPLAY CHECKSUM PASS",
  "driver_pattern": "KosmicKrisp",
  "metric_pattern": "average_fps=([0-9.]+)",
  "minimum_metric": 30
}
```

These example markers/arguments are a contract illustration, not an existing
game configuration. Set them to the selected benchmark's real output, and
choose its performance floor for the CI hardware. The game runs from its
executable directory through the experimental launcher in the isolated prefix.
An exit code alone is insufficient: both markers and the numeric threshold must
pass. The runner accepts ZIPs up to 512 MiB compressed / 2 GiB expanded, rejects
path traversal and symlinks, and verifies the SHA-256 before extraction.

Prefer a native Vulkan benchmark while upstream DXVK is blocked. A D3D game's
backend setup must be part of its reproducible fixture; the launcher does not
silently install test DXVK into that game's directory. Steam/account-bound
games require a separately provisioned runner and replay harness; this workflow
does not access personal libraries or account credentials.

## Local verification

```sh
python3 -m unittest discover -s tests -p 'test_kosmickrisp*.py' -v
actionlint -shellcheck= .github/workflows/build.yml
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

The extended GPU probes passed locally on macOS 27.2 through the existing Wine
runtime. That does not replace execution on a physical macOS 26 runner or
establish that the new patched Wine artifact has passed GPU validation. See [local results](kosmickrisp-test-results.md).
