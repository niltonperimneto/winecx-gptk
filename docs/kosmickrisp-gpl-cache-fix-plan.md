# GPL cache and Metal PSO fix scaffold

Private implementation scaffold: biblioklept.

## Objective

Diagnose repeated GPL shader-cache misses, prewarm default dynamic multisample
and blend variants, and persist render and compute Metal pipelines. Deliver
independent patches through the winecx-gptk KosmicKrisp series.

## Baseline

- Portal 2 GPL warm launch: 475 shader groups and 81 draw-time PSOs compiled.
- Portal 2 non-GPL warm launch: 2 shader groups and 85 draw-time PSOs compiled.
- Existing regression suite: 227 passing cases.
- Expanded batch: 67 passing checks and two grouping timeouts (9/6 and 14/1).
- Preserve existing edits and the shared Metal compiler workaround.

## Ownership and dependencies

| Owner | Work | Handoff | Dependency |
| --- | --- | --- | --- |
| Coordinator | Runtime tracing contract, device lifetime, integration, validation, packaging | Build identities, integrated tests, checked patch series | All workers |
| Agent A | Shader keys, component tracing, root-cause diagnosis, deterministic hashing, shader call sites | Two-run comparison and key regression evidence | Runtime tracing contract |
| Agent B | Dynamic-state prewarm, exact-key deduplication, lifetime safety | Default/non-default rendering and prewarm coverage | Existing PSO linking path |
| Agent C | Metal 4 archive bridge, persistence, render/compute recovery | Restart cache hits and failure handling | Existing shared compiler lifetime |

Workers use isolated worktrees. Agent A owns shader call sites; Agent B owns
PSO prewarming; Agent C owns archive bridge/storage. The coordinator owns
shared runtime and device interfaces and merges worker changes.

## Work checklist

- [x] Capture the initial dirty tree and existing result identities.
- [x] Freeze tracing and persistence interfaces.
- [x] Add opt-in MESA_KK_CACHE_LOG JSONL tracing without changing compile CSV.
- [x] Associate shader events with precompiled keys, flags, layout, state,
      final keys, namespace, and lookup/deserialization outcomes.
- [x] Compare equivalent shader content and stages across identical launches.
- [x] Identify changing keys separately from stable-key misses and rejected blobs.
- [x] Correct the demonstrated cause and canonicalize unsafe state hashing.
- [x] Allow dynamic multisample/blend predictions using explicit defaults after fill.
- [x] Preserve static values and unknown topology/attachment-map exclusions.
- [x] Match predictions and draws through the same exact state key.
- [x] Persist render and compute pipelines with Metal 4 archives and dataset capture.
- [x] Use content-addressed blobs/references in Mesa's disk cache.
- [x] Namespace by schema, driver, GPU, OS build, shader/compiler inputs, and descriptor.
- [x] Flush captures in the background every second or after 64 new pipelines,
      and drain during teardown.
- [x] Recover from missing, corrupt, incompatible, or evicted entries by compilation.
- [x] Honor cache disable controls and add MESA_KK_PSO_CACHE_DISABLE.
- [x] Record archive hits, compiler fallback, prediction coverage, and waits.
- [x] Run correctness, concurrency, persistence, and game validation.
- [x] Package independent patches and verify the complete checksum manifest.

## Defaults

Predict one sample, a full sample mask, disabled alpha coverage/alpha-to-one,
disabled blending and logic operations, ONE/ZERO ADD equations, and RGBA writes.
Only replace dynamic fields. Retain static topology and attachment mapping
requirements. Predictions cannot change Vulkan command-buffer state and do not
guarantee coverage of every dynamic draw variant.

## Validation gates

1. Stable keys across processes and different padding; meaningful inputs change keys.
2. Correct default/non-default dynamic-state readbacks, mixed static/dynamic state,
   concurrent prewarm/draw requests, and source-library lifetime.
3. Restart hits for render/compute and GS/TES passes; multiple devices/processes,
   corruption, interrupted writes, eviction, and disabled caches.
4. Existing rendering regressions and GPL batch, retaining baseline grouping failures.
5. Portal 2 cold plus two warm launches in GPL and non-GPL modes, one unchanged
   build and separate cache directories. Explain misses and report first-draw
   waits and frame times separately.
6. Validate each patch and the complete series. Keep logs, reports, build
   identities, and patch checksums. No GitLab submissions or generated commits.

## Handoff status

Driver implementation, native/x86 builds, patch packaging, regression checks,
and six Portal 2 cold/warm launches are complete.

Evidence directory: `../kk-shader-build/gpl-cache-fix/`.

- `evidence/shader-key-padding.jsonl`: identical semantic depth/stencil state
  with different padding changes the old raw hash; canonical hashes match.
- `final-validation/report.json`: 184 passed checks, two existing grouping
  timeouts (9/6 and 14/1), one unsupported color-write extension skip. Includes
  108 performance runs; the original 227-case suite also passes.
- `metal-regression-fixed/report.json`: five passing capture-race,
  serialization-failure, concurrent-access, corrupted-archive, and disabled-cache
  scenarios. Negative controls reproduce both synchronization defects.
- `evidence/synthetic-warm-cache-summary.json`: 36 disk-warm benchmark runs,
  78 shader disk hits and 42 render archive hits, with zero shader misses or
  render compiler fallbacks.
- `smoke/`: separate-process shader and render archive hits; geometry and
  tessellation recover their compute pipelines from archives too.

Archive restoration still has file-loading and Metal object-creation costs.
Small synthetic PSOs can restore more slowly than compiling; compilation
avoidance alone is not evidence of better frame times. The game comparison
will report this separately.


## Packaged series

The existing 21 patches are preserved. Seven additional patches are recorded in
`runtime/kosmickrisp/patches/kosmickrisp-gpl/series.sha256`:

| Patch | Scope |
| --- | --- |
| 0022 | Compile timing and present logging dependencies |
| 0023 | Metal pipeline archive bridge |
| 0024 | Metal pipeline disk cache and background worker |
| 0025 | Shader cache key tracing and shared compiler cache lifetime |
| 0026 | Deterministic shader cache keys and schema bump |
| 0027 | Dynamic multisample/blend PSO predictions |
| 0028 | Native render/compute identity and cache integration |

Manifest SHA-256:
`ea64b2f8c283092625f3db3cb156f9f46f97ac10f41aaf03bebc6299e0f3869f`.

`packaging/verification.json` confirms atomic application of all 28 patches to
`fe554882e4f06cdd2579a77b37b04de605111a28`, idempotent reapplication, and
byte-for-byte agreement for all 45 packaged source paths. The 14 patch-harness
tests pass after the manifest update. All 83 KosmicKrisp tooling unit tests pass.
No commits or GitLab submissions were made.


## Review limits

A compiler-creation failure now returns before allocating an isolated cache.
Read-only review found no additional capture lock-order or archive lifetime
issue. Real-device coverage now includes two VkInstances on the same GPU, destroying
the first instance/device before rendering and GS/TES readbacks on the survivor.
Concurrent devices with different internal-cache settings remain untested. A device that disables its internal cache
still contributes unreferenced captures to a shared enabled compiler; it
performs no archive lookups or reference writes itself.

Portal runs use opt-in key tracing. High-volume draw cache-hit logging can affect
frame times, so those timings cannot establish an uninstrumented performance
improvement.


## Portal 2 GPL comparison

All three 240-second GPL runs render normally. The final bundle is held constant
across game runs; the later compiler-allocation failure guard affects only an
error path and is separately built and packaged.

| Run | Shader disk hits | Completed shader-stage compile records | Render archive hits | Compute archive hits | Render compiler fallbacks | Matching predictions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cold | 52 | 501 | 0 | 0 | 75 | 64 |
| Warm | 554 | 396 | 75 | 9 | 4 | 75 |
| Warm 2 | 950 | 429 | 78 | 9 | 0 | 68 |

Cold-to-warm has 471 stable matched keys; warm-to-warm-2 has 867. Both comparisons
have zero matched key changes and zero deserialization rejections. Each has
three stable-key misses. The first pair includes two incomplete cold compiles
and one compile near shutdown; all three hit in warm 2. The second pair's three
vertex shader entries had no completed compile before warm stopped.

Warm 2 introduces 429 new precompiled inputs (101 vertex, 328 fragment) and no
new flags, partition, layout, or state variants on shared inputs. No previous
input disappears. The precompiled hash also includes specialization and
robustness, so this does not prove new SPIR-V content by itself. Completed shared
inputs reuse their keys; newly encountered inputs still require compilation.

Warm and warm-2 traced frame medians are 14.74 and 14.98 ms, with p95 values
36.70 and 35.74 ms. These measurements include verbose trace overhead and
changing background compilation workload; they establish no overall speedup.
Non-GPL comparison completed; results follow below.


## Optimization follow-ups supported by measurements

- Archive hits avoid Metal compilation but still incur archive loading and
  pipeline object creation. In the first non-GPL warm run, archive prewarming
  totaled 208.22 ms versus 190.46 ms of cold prewarm compilation, with 119.10 ms
  versus 70.50 ms of recorded draw waits. These aggregate traced times do not
  establish a frame-time regression or improvement.
- Predict common non-default dynamic variants or retain variant histories to
  cover the ten GPL draw-time archive creations seen in warm 2. Default-state
  prediction already matched all 85 non-GPL render PSOs in warm 1.
- Reduce or sample high-volume draw cache-hit tracing before using the harness
  for uninstrumented performance claims.

These are measured follow-ups, not additional changes in this patch series.


## Completed game and lifetime validation

`evidence/portal-cache-validation.json` records six completed 240-second runs,
build identity, frame timings, compiler/archive counts, and trace comparison
paths. All six runs have zero DXVK errors.

| Non-GPL run | Shader disk hits | Shader compiles/misses | Render archive hits | Compute archive hits | Metal compiler fallbacks | Matching predictions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cold | 0 | 179/179 | 0 | 0 | 94 | 82 |
| Warm | 179 | 0/0 | 85 | 9 | 0 | 85 |
| Warm 2 | 173 | 0/0 | 82 | 9 | 0 | 81 |

Non-GPL comparisons match 179 and 173 stable shader keys, with zero key changes,
stable-key misses, or rejected blobs. Warm 2 has one draw-time archive creation;
warm 1 has none. Warm-2 traced frame median/p95 are 8.35/21.91 ms.

The GPL cold-to-warm comparison adds 394 new precompiled inputs and two
additional variants on shared inputs, including depth/stencil differences; the
original variants remain present. Warm-to-warm-2 adds 429 new precompiled
inputs. Logs cannot determine whether these new inputs arise from module
content, specialization, or robustness; the compilation source remains an
explicit diagnostic limit. No repeated miss is demonstrated for an input whose
previous compilation completed and persisted.

`evidence/multidevice-validation.json` records passing cold and warm actual-device
lifetime tests. After the first instance/device is destroyed, the survivor
passes rendering, geometry side-effect, adjacency, and tessellation/geometry
readbacks. The warm process records three render and six compute archive hits,
with zero shader compilation events.

Implementation and packaging are ready for local review. No commits or remote
publication were performed. Remaining measured optimization opportunities and
coverage limits are recorded above.


Next proposed work: [Draw variant stalls: plan toward zero](kosmickrisp-draw-variant-stalls-plan.md). This follow-up targets ready variants and
remaining draw waits; implementation has not started.
