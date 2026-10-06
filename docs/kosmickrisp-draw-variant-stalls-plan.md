# Draw variant stalls: plan toward zero

Private implementation scaffold: biblioklept.

Status: patches 29–35 implemented and verified; selected fixed replay zero-work gates pass after readiness. The final six-run uninstrumented game comparison is complete. Strict automatic first-demand zero remains unmet.
Predecessor: [GPL cache and Metal PSO plan](kosmickrisp-gpl-cache-fix-plan.md).

## Objective and zero-stall contract

For a fixed, previously observed workload on a compatible warm cache, every
required FS/raster variant and native render/compute PSO must be resident before
its first draw. Target zero draw-path compilation, archive reads, Metal pipeline
creation, and waits for unfinished variant jobs. Ordinary lookup/encoding time
is measured separately and is not claimed to be zero.

Arbitrary first-ever dynamic state cannot be guaranteed ready by prediction.
Strict readiness is possible only after the required state is known and its
exact pipeline is prepared, or with an already prepared fallback proven to
implement the same Vulkan semantics for that attachment/sample configuration.
Never substitute a default PSO for a different requested state, drop a draw, or
claim success by relocating a wait into another command on the same frame.

The initial shipping target is warm replay of observed variants. Cold/new-state
behavior remains correctness-first with explicit misses and synchronous fallback
when necessary. A loading-phase readiness integration is a separate opt-in step;
it must distinguish waiting earlier from eliminating work.

## Measured baseline

Source: `../kk-shader-build/gpl-cache-fix/evidence/portal-cache-validation.json`.
All game runs used verbose tracing; these figures are diagnostic baselines,
not an uninstrumented performance comparison.

| Workload | Remaining work |
| --- | --- |
| GPL warm 2 | 78 render archive hits, 68 prediction matches, 10 draw-time archive creations, 43 draw PSO wait events |
| Non-GPL warm | 85 prediction matches, no draw-time archive creation, 41 draw PSO waits totaling 119.10 ms |
| Non-GPL warm 2 | 82 render archive hits, 81 prediction matches, one draw-time archive creation, 44 draw PSO waits |

Zero Metal compilation has already been demonstrated in these warm runs.
Archive reuse alone therefore cannot meet the new zero-wait target.
FS variant waits, point-raster preparation, and GS/TES compute preparation must
be attributed independently before deciding which work dominates.

## Ordered implementation and patch boundaries

The six numbered sections below describe implementation phases. The final raw
patch series adds 29 (the approved source prerequisite), 30 (trace and stable
identities), 31 (history storage), 32 (exact replay and resident results),
33 (early command hooks), 34 (test readiness exposure), and 35 (avoid recipe
hashing for aggregate-only tracing). Test tooling lives
in winecx-gptk alongside the series. Each phase has separate evidence.

### 29: Attribute variant readiness and draw blocking

- Assign stable request IDs to pipeline families, FS link variants, raster
  variants, and exact PSO keys. Log parent/dependency IDs without addresses.
- Record enqueue, worker start, archive lookup/load, FS/MSL preparation,
  native object creation, completion, first demand, and wait intervals.
- Separate wrong prediction, missing history, incomplete state, queue delay,
  dependency delay, archive loading, compiler work, and lock contention.
- Distinguish ready hits from hits on entries still being prepared. A prewarm
  match does not imply readiness.
- Use aggregated counters by default. Detailed timelines are opt-in and avoid
  logging every ready hit. Keep the existing four-column compile CSV compatible.
- Report union of blocking intervals per command-recording thread, plus exclusive
  phase times; do not sum nested waits into an inflated total.

Gate: deterministic fixtures attribute a deliberately delayed FS dependency,
archive load, and queued PSO correctly. Capture a low-overhead baseline for the
same fixed replay before introducing scheduling changes.

### 30: Persist exact observed variant recipes

- Record the actual successful draw recipe, not just the default prediction or
  archive reference. Include the FS link key and normalized state needed to
  reconstruct the exact PSO, topology/raster variant, attachment formats/maps,
  view mask, sample state, and blend/output state.
- Build a stable pipeline-family identity from base pre-raster/FS identities and
  static compilation/link constraints. Do not require the generated FS variant
  hash to discover its own recipe.
- Reapply current static state and only replay compatible dynamic fields.
  Reject incompatible shader interfaces, static states, formats, sample counts,
  attachment mappings, and unavailable features.
- Track first-use order and frequency. Retain observed non-default variants;
  do not enumerate every combination of dynamic states.
- Use a versioned, bounded manifest under the existing driver/GPU/OS/settings
  namespace, with checked lengths/enums and safe corruption handling.
- Queue persistence off the command thread, merge/deduplicate records, and honor
  cache disable controls. Interrupted writes or eviction cause a safe miss.

Gate: same family across processes recovers exact recipes; changed static state
and incompatible/corrupt records cannot select an incorrect pipeline. Recording
history causes no draw-thread disk I/O.

### 31: Replay history and build dependency chains before first use

- On executable pipeline creation/link, schedule compatible observed recipes
  alongside the current default prediction. Prepare FS variants and point-raster
  functions before their native PSOs; include required GS/TES compute pipelines.
- Load archives and create retained native pipeline objects in workers. A loaded
  archive is not considered a ready PSO.
- Keep shader/library references until jobs complete, and preserve shared compiler
  and cache ownership across devices and instances.
- Deduplicate pending work by exact key. Publish success/failure atomically and
  wake all requesters without holding a global cache lock during Metal work.
- Schedule chains as one worker operation or dependency continuations. Do not
  let every worker wait on dependencies queued behind itself in the same pool.
- Bound speculative concurrency and memory, prioritizing first-use history.
  Publish every required observed variant before declaring replay ready.

Gate: delayed workers and concurrent duplicate requests neither deadlock nor
create duplicate variants. After an explicit test readiness barrier, all replayed
variants are ready hits with no Metal creation or FS compilation on draw.

### 32: Advance exact preparation when dynamic state becomes known

- Inspect pipeline/shader binding, rendering attachment setup, and relevant
  dynamic-state updates to find the earliest point with a complete valid recipe.
- Enqueue exact preparation only when all required state is known. Track state
  validity and coalesce superseded snapshots to avoid one speculative compile per
  setter. Do not change Vulkan command-buffer state.
- Give known upcoming exact requests precedence over default speculation and
  unused history, with bounded fairness and retained job lifetimes.
- Keep command-recording hooks nonblocking. Early scheduling improves available
  lead time but does not guarantee completion before an immediately following draw.
- Measure queue latency and available lead time before changing worker counts.
  For unknown topology or attachment mappings, prepare only dependencies that
  are independent of those fields.

Gate: frequent state changes and immediate draws remain correct; unused work is
bounded. Moving a wait from draw into bind/setter is a test failure.

### 33: Readiness integration and a fast path for ready variants

- Provide an internal/test readiness query and scoped drain for the observed
  recipe set, including FS, raster, render, and compute dependencies.
- Integrate a loading-phase drain only where the caller explicitly controls a
  loading phase. Do not silently block every vkCreateGraphicsPipelines or frame.
  If DXVK integration is needed, keep it a separate Wine/DXVK patch and contract.
- The draw path retrieves the exact resident result without disk access or Metal
  creation. On a miss, preserve the existing correct fallback and emit its reason.
- Pin the active replay working set for the zero-stall test. Under a memory budget
  too small to retain it, report the target as unmet rather than hiding eviction.
- Measure loading readiness time and whole-frame latency, including binds,
  dynamic setters, command recording, and submission. Waiting at submission is
  not counted as eliminating a frame stall.

Gate: known warm recipes achieve zero variant work/waits after readiness, and
loading costs are reported. Real-game automatic scheduling must pass without
an artificial sleep. A generic shader fallback is outside the initial series;
any later fallback requires a separate correctness design.

### 34: Correctness, zero-stall regression, and packaging

- Fixed trace replay: cold record, warm replay, and second warm replay with the
  exact same variant sequence. Track recipe discovery separately from cache miss.
- Read back default/non-default blend and multisample state, advanced programmable
  blend, integer outputs, sample masks, point raster, attachment remapping,
  multiview, and GS/TES cases where supported.
- Exercise immediate first draw, delayed workers, saturated queues, duplicate
  requests, library destruction, multi-instance lifetime, cache disable, corrupt
  manifests/archives, eviction, and insufficient memory budget.
- Test that new unseen state uses a correct fallback and is not mislabeled as a
  ready hit. Test that all exhausted/failed jobs unblock waiters with valid errors.
- Repeat Portal 2 GPL/non-GPL cold plus two warm runs on one unchanged build;
  compare variants shared across runs and separately report new precomp inputs.
- Use aggregate counters for performance runs; use full tracing separately for
  diagnosis. Compare first-draw and whole-frame median/p95/p99/max against the
  same workload/build configuration and report loading-time tradeoffs.
- Build native/x86, retain existing rendering regressions and baseline exceptions,
  and verify patch checksums, atomic application, idempotence, and source bytes.
  No generated commits or GitLab publication.

## Acceptance criteria

For fixed replay after readiness and for previously observed real-game variants:

1. Zero draw FS/raster variant compilation, archive I/O, and Metal PSO creation.
2. Zero draw waits for variant preparation, plus zero relocated waits on the
   frame-critical bind/setter/submission paths.
3. Exact readbacks match the existing synchronous implementation.
4. No regressions in device/library lifetime, concurrency, error handling,
   cache disable behavior, or bounded resource usage.
5. No artificial sleep or workload alteration used to achieve the result.

If automatic real-game scheduling cannot prepare everything by first demand,
report residual counts and their reasons. A readiness-barrier test passing alone
is insufficient to claim that game draw stalls reached zero. No absolute
zero-stall claim covers an unseen variant or an evicted required pipeline.

## Scaffold ownership and handoffs

| Role | Scope | Dependency |
| --- | --- | --- |
| Coordinator | Trace contract, cache/device lifetime, acceptance reports, integration, packaging | All workstreams |
| Variant-history worker | Family identity, recipe schema, history recording/replay | 29 before 30 |
| Shader/raster worker | FS/raster/GS/TES dependency preparation and lifetime | 29 and 30 before 31 |
| Scheduling worker | Early exact requests, priority/dedup, readiness and draw lookup | 31 before 32–33 |

The approved scaffold was executed with separate history, dependency/scheduling,
and trace workstreams. Frozen source is now under read-only audit; final game
measurements use one unchanged binary. Further driver edits require a new
validation build and cache namespace.

## Checklist

- [x] Inspect completed game measurements and current variant/prewarm paths.
- [x] Define the zero-stall scope and distinguish readiness from prediction.
- [x] Implement attribution and capture a low-overhead baseline.
- [x] Persist and validate exact observed recipes.
- [x] Replay scheduled dependency chains and retain resident results.
- [x] Schedule exact state as early as it is valid.
- [x] Add device-wide test readiness and resident fast lookup.
- [ ] Add scoped application loading integration.
- [x] Pass fixed replay correctness and zero-work gates after readiness.
- [ ] Pass automatic real-game first-demand zero-stall acceptance.
- [x] Package manageable patches and record remaining limits.
- [x] Complete the final six-run uninstrumented game comparison.


## Implementation evidence and limits

Private implementation record: biblioklept.

- Native replay v2: 46 passed, zero failed or skipped. All 24 warm checks after
  the explicit readiness drain recorded zero draw compilation, archive work,
  native creation, and variant waits. Drain times ranged from 0.107 to 5.048 ms.
- The newly observed-state test found an immutable-key persistence bug. The
  background history worker now drains pending cache writes, removes the old
  manifest, and writes the replacement. Ten ASAN and ten TSAN cases pass;
  omitting removal reproduces the lost update. An interrupted replacement
  safely produces a cache miss.
- Concurrent VS and GS links, cache disable, immediate draw, selective history
  corruption/recovery, and recipe-budget exhaustion passed exact readbacks.
  Budget exhaustion reports VK_NOT_READY and ready:false, rather than claiming
  zero work.
- Final tooling suite: 120 tests passed, one existing test skipped. Native and
  x86 driver builds passed. Frozen GPU checks are complete; the final game
  comparison is complete.

History updates support Mesa multi-file and database backends. Unsupported
backends disable history and report limited readiness. Concurrent processes
updating the same manifest can lose observations; this affects preparation
coverage and cannot select a wrong PSO. History retains at most 32 recipes
per family and 256 resident manifest families. A device retains at most the
configured recipe limit (default 4096, maximum 8192); background and exact work
are bounded separately. These bounds cover new replay preparation, not a
byte budget for the existing native shader/PSO caches.

Readiness is a device-wide drain of scheduled compatible recipes, rather than
a public Vulkan extension or application loading integration. Dynamic topology
and attachment mapping are excluded from creation-time history replay; complete
command snapshots can still schedule exact preparation. An immediate draw may
wait for that work. Automatic real-game scheduling must be judged separately
from the explicit-drain tests. Final frozen fixtures add point raster, integer
outputs, static attachment remapping, and multiview below. Validation layers and
explicit delayed/saturated-worker GPU fixtures remain uncovered.


### Frozen build validation

- The frozen main replay suite passed 46/46 checks on native and 46/46 on x86.
  Cache-disabled checks now explicitly require limited readiness and verify the
  subsequent correct fallback draw.
- Dedicated point raster passed 6/6 per architecture; integer output passed
  9/9 per architecture, including exact uint32 values beyond float precision.
- Multiview application raster passed cold/warm/warm2 on both architectures,
  with zero warm work after readiness. Separate layered-clear checks passed
  readbacks but did not meet zero: Mesa creates a meta clear pipeline during
  rendering setup. This is a remaining frame-critical preparation gap; the
  raster result must not be presented as a full multiview zero-stall result.
- Patches 29–35 are integrated into the 35-patch winecx series. All checksums,
  fresh atomic application, idempotence, and 50 touched source files match.
  Manifest SHA256: 8ff47a05f5e2a8cc9c67f7705fa8d6910348654351b09bc92f46347db08e266f.
  Source tree: 18674b50caa574ba53285ecbbcccc7fea15942d4.
- Static attachment-location mapping passed six checks per architecture, using
  dynamic rendering and matching pipeline/command mappings before or after bind.
  This does not test arbitrary incompatible mappings or local-read inputs.
- The final frozen driver passed 73 checks per architecture, plus three native
  aggregate-only checks: 149 GPU correctness passes, zero failures. Eighty warm
  gates in the architecture suites and two aggregate-only warm gates had zero
  draw variant work after an explicit loading drain. Aggregate-only drain times
  were 3.072 and 3.233 ms.
- Six baseline29 Portal 2 runs completed. The final35 runs use one frozen x86
  binary, separate GPL/non-GPL caches, compile CSV and frame timestamps, with
  aggregate and detailed logging disabled. They use no readiness drain or
  artificial delay. Detailed tracing is captured separately.
- Forced game termination does not flush DestroyDevice aggregate statistics;
  empty aggregate files cannot prove zero. Final game counts come from flushed
  compile CSV. The detailed JSONL capture has 650 complete events, and its
  buffered tail may be missing; CSV independently confirms blocking counts.
- Patch 35 avoids hashing entire recipe identities when only aggregate counters
  are enabled. Prior 34-patch measurements remain diagnostic records, rather
  than the final performance comparison. Changing the binary also changes its
  cache namespace, so final35 starts with new cold caches.

Private validation record: biblioklept.

### Automatic startup readiness gap

The separate GPL warm diagnostic found 14 draw waits and three direct draw
archive restores. All 17 requested recipes were independently matched to the
previous warm-run history using Mesa BLAKE3. These are known variants becoming
available too late, rather than missing recipe persistence. No draw FS or raster
compilation occurred in that capture.

The captured blocking interval union is 106.370 ms; independent compile CSV
reports 97.384 ms of waits and 8.542 ms of direct restores. These are different
instrumentation scopes and must not be summed together. The largest wait was
71.793 ms, including a 48.250 ms archive load and 21.885 ms native creation.
Three direct restores began before family history loading registered their
recipes. Most relevant scheduling leads were approximately 0.03–1.95 ms.
An earlier opportunity for the same family does not establish compatibility
with the static pipeline context needed later.

All blocking events in that diagnostic occurred before 60 seconds. The earlier
34-patch GPL/non-GPL warm runs also recorded zero draw variant events after the
fixed 60-second cutoff. This is evidence for steady gameplay, not first-demand
zero. Final35 startup and post-cutoff counts will be reported separately.

The remaining architecture work is a bounded device-start catalog containing
observed family recipes and base shader asset cache keys. Workers must import
those assets with initialized Vulkan cache ownership, restore dependencies and
native PSOs before application pipeline-family creation, and retain the working
set. Current family-keyed history cannot enumerate unseen-in-this-process
families at device creation. Monolithic and meta pipelines need coverage too.
A scoped loading readiness contract must include enumeration and all dependent
jobs, and report missing assets, errors, and budget exhaustion. DXVK worker
completion alone does not establish Mesa PSO readiness. Automatically waiting
at bind, draw, present, or submission would relocate the frame stall and fail
the acceptance criteria.

The device-start catalog and an application-controlled loading integration are
follow-on work, not implemented by patches 29–35. Driver-only automatic
first-demand zero remains unproven. Layered meta clears remain an independent
measured gap even after the current test readiness drain.

Private diagnostic and follow-on design record: biblioklept.

### Final35 workload-expansion audit

The clean final35 GPL second warm run retained all 65 previous recipes and added
69 recipes across 63 new families. It restored 106 archives and compiled 94 new
native PSOs. All earlier Metal references remained present, and the new native
keys produced 94 additional valid reference records in the same namespace.
This is not evidence of a general archive-persistence failure.

The shader inventory decoded 1,871 version-7 blobs with no parser failures.
Warm2 added 72 blobs, comprising 36 VS and 36 FS. Sixty-two have previously
unseen MSL, representing 47 distinct sources that remain different after
normalizing generated temporary names. Thirty-one FS have new retained NIR;
the other five match previous NIR exactly. Twenty-six VS have new named
metadata after excluding padding. Representative source changes include a
descriptor offset from 32 to 48, additional varyings and constant-buffer loads,
and alpha-test discard. These establish substantive shader/compile-layout
expansion, rather than a blanket identity/deserialization drift.

Map, launch arguments, and cache paths matched, but player input and scene
traversal were not recorded. Equal arguments therefore do not prove an identical
shader workload. Forty-seven new recipes have already seen draw-state tails
combined with different family identities. Exact attribution of every new
family to original SPIR-V is unavailable without per-key logs for those runs.
The second warm run's post-cutoff work must remain in the results; the first
warm run cannot stand in for both. A deterministic game demo or recorded input
sequence would be needed for a stronger repeated-workload performance claim.

Private shader and Metal inventory record: biblioklept.

### Completed final35 game comparison

All six 240-second GPL/non-GPL cold, warm, and second warm runs completed with
exit status zero on one unchanged final35 binary. Aggregate and detailed logs
were disabled. No loading drain, artificial delay, or concurrent GPU fixtures
were used. Compile CSV totals below sum events, rather than defining a union
of nested blocking intervals.

| Mode/pass | Whole-run draw waits | Whole-run draw archive restores | Whole-run draw native compiles | Draw events after 60 seconds |
| --- | --- | --- | --- | --- |
| GPL warm | 15 / 77.82 ms | 3 / 9.49 ms | 0 | 0 |
| GPL warm2 | 86 / 951.46 ms | 3 / 10.68 ms | 1 / 1.06 ms | 66 waits / 825.25 ms; one compile / 1.06 ms |
| Non-GPL warm | 35 / 167.57 ms | 4 / 6.12 ms | 0 | 22 waits / 97.92 ms; one restore / 0.78 ms |
| Non-GPL warm2 | 38 / 440.02 ms | 4 / 3.91 ms | 0 | 18 waits / 381.33 ms; one restore / 0.76 ms |

Non-GPL history grew from 79 cold recipes to 79 after warm and 81 after warm2;
no recipes were removed. Its first warm run therefore demonstrates residual
late readiness within a previously observed set, independent of the larger
GPL warm2 shader expansion. GPL history grew from 62 to 65 to 134 recipes.

Frame-time results vary. GPL warm post-cutoff p95/p99/max were
20.63/30.68/120.03 ms versus baseline29 26.78/39.56/457.05 ms, but its median
worsened from 11.84 to 14.79 ms. GPL warm2 had a 750.26 ms maximum. These
sequential, non-deterministic scene exposures do not support a general FPS
or isolated causal improvement claim.

The measured result is 149 passing GPU correctness checks and 82 selected warm
zero-work gates after readiness, with a verified 35-patch series. Automatic
real-game first-demand zero and universal post-cutoff zero remain unmet.
Layered meta clears and application-scoped loading readiness also remain open.
No assertion that all workloads are zero is made.

Private final acceptance record: biblioklept.
