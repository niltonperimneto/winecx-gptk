# Runtime layout v2: one Vulkan provider

New runtimes bundle the Khronos Vulkan Loader, Mesa KosmicKrisp and upstream
DXVK. They contain no MoltenVK binary, dependency or legacy `DXVK/` directory.
`DXVK3/{x64,x32}` is the canonical DXVK payload. D3DMetal, DXMT and Wine's
non-Vulkan paths remain independent choices. Installing a runtime does not
require a usable Vulkan device.

## Component ownership

The Wine source change is based on the previously tested hub pin; unrelated
Wine main-branch features remain separate from this migration.

WineCX owns runtime-relative discovery in `dlls/win32u/vulkan.c`. On macOS,
Wine locates `Wine/lib/kosmickrisp` from its loaded `win32u.so`, rather than the
working directory or a developer's home. `WINE_VULKAN_LIBRARY` and the legacy
`CX_LIBVULKAN` override remain available for explicit development/testing.
Failure to load the selected library fails Vulkan initialization; it cannot
fall back to MoltenVK. Generic presentation handling remains intact.

The hub owns immutable pins, payload acquisition, cache keys, fresh assembly,
relocation, dependency closure and archive validation. DXVK belongs to the
payload cache, Mesa/loader to the graphics cache, and Wine to the tools/core
caches. The superseded out-of-tree Wine loader patch is removed. Assembly
copies and compiles probes; physical GPU execution happens after packaging.
The native ARM64 research script explicitly configures without Vulkan until
that architecture has a validated matching provider.

Whisky owns catalog decoding, runtime installation, device usability and
explicit bottle migration. It accepts layout/catalog versions 1 and 2. Layout
v2 installs require complete payloads and `capabilities.vulkanProvider` equal
to `kosmickrisp`. A bounded native device probe determines whether DXVK is
usable; its cache follows runtime/driver/OS identity and expires. A failed
probe does not prevent D3DMetal, DXMT or supported Wine paths from launching.
The Vulkan environment no longer changes the Direct3D backend identity on v2.
Steam retains its helper-local DXVK route, GPU compositing and launcher fixes.
An unsupported Steam configuration is not certified by a software fallback.

## Versioned consumer contract

`WhiskyWineVersion.plist` adds `runtimeLayoutVersion: 2` and the optional
`capabilities.vulkanProvider`. `manifestVersion` keeps its existing meaning;
`RuntimeManifest.json` remains inventory format 1. Layout validation rejects
MoltenVK filenames, symlink targets and Mach-O load commands after cache
restoration and before packaging. Consumer tests validate the exact archive.

`runtime-catalog-v2.json` is the endpoint for compatible Whisky clients. Its
initial entries identify validated legacy runtimes; a new entry is added only
after promotion gates pass. `runtime-catalog.json`, the frozen `contracts/runtime-layout-v1.json`, old release assets and
installed runtimes are preserved for older clients. This branch does not
publish a new runtime merely by compiling it.

## Explicit, recoverable bottle switching

Installation stays side by side and does not rewrite bottle pins or graphics
choices. The runtime picker validates a selected destination before changing
the pin. It rejects unrecognized native graphics DLLs rather than overwriting
custom DLLs. It takes a durable clone of the bottle, identifies/removes old
owned backend/helper DLLs using the old payload, updates Wine, and verifies
the selected available backend. Registry and settings data are included in
the clone. Launches through Whisky are blocked during a switch.

Archive installation still verifies the complete producer manifest and rejects
undeclared files. An installed tree is mutable: GPTK deployment replaces graphics
files, and removal can remove the original `external/README`. Applying the archive
inventory again when selecting that tree would reject supported installations.
Switch preflight instead checks the installed layout and producer hashes of the
Wine loader, server, Unix ntdll/win32u and both Windows core/Vulkan DLL lanes.
Executable links must resolve inside the runtime to a verified manifest entry.
Backend availability, staging verification and the transactional Wine refresh
remain separate checks. Regression tests preserve strict archive rejection and
reject altered Wine core files, missing manifests and escaping executable links.

A failed refresh restores the clone and old settings. An interrupted switch
leaves a sibling `.<bottle>-runtime-rollback` directory and blocks normal
launches. The picker offers **Restore interrupted runtime switch** once the
bottle is idle. Never delete that backup to force a launch. A successful
switch removes the rollback clone. Old runtime installations remain available
for a later explicit switch back. No hidden provider fallback participates in
rollback.

## Validation and promotion

The build must pass static/unit checks, compiled subsystem checks, complete
assembly, relocation and base Wine/media/network/dependency/floor probes.
The packaged archive also runs through the pinned Whisky consumer tests.
`consumer-runtime.yml` is the same full-suite check used by the build and can
be dispatched with `source_run_id` to recheck an existing immutable archive
after a consumer-only change. Its run records the archive digest and uses the
current immutable consumer pin; retain both source revisions with the results.
Before that workflow reaches the default branch, dispatch the existing build
entry point with `consumer_source_run_id`. This runs static/unit QA and the same
consumer check against the chosen archive. A normal build retains the complete
producer and publication dependency chain.
Physical validation runs the same archive on macOS 26 and on a newer supported
OS. It checks real device creation, missing/corrupt/invalid-override loader
failures, Wine operation with Vulkan absent, 32/64-bit compute and geometry /
tessellation readback, presentation transitions, D3D9/10/11 and constant-array
readback. Each claim requires its own successful probe.

Configure trusted physical runner labels with `MACOS_GPU_RUNNER_26` and
`MACOS_GPU_RUNNER_NEWER`. Hosted runners build artifacts; they cannot substitute
for physical Metal 4 validation. Missing runner configuration fails the GPU
gate explicitly. The physical job has a separate, longer campaign timeout.

Provision licensed Hades Vulkan and DXVK, Portal 2 32-bit D3D9, Skywalker and
Steam CEF fixtures on each physical host. The existing game/stutter/gameplay
harnesses are starting points, not passing migration evidence. A frozen campaign
adapter is supplied by `MACOS_GPU_CAMPAIGN` and its exact file digest by
`MACOS_GPU_CAMPAIGN_SHA256`. Its interface is:

```text
python3 HARNESS --libraries RELOCATED_LIBRARIES --output RESULTS \
  --archive-sha256 VERIFIED_ARCHIVE_DIGEST
```

The adapter must provision disposable prefixes/copies, verify licensed game
builds and scene/settings hashes, execute the fixed scenes with actual backend
verification and collect visual evidence plus frame-time samples. It must not
write into live user bottles. It writes `RESULTS/campaign.json` and referenced
evidence beneath `RESULTS`; the upload excludes game payloads. Provisioning and
qualifying this adapter on both physical hosts remains necessary before any
promotion. An external script returning zero is insufficient: `promotion.py`
validates its evidence and attaches the game result only when complete.

The campaign envelope contains `schema: 1`, the validated `manifest_sha256`,
`os`, `hardware`, and exactly five `cases` with IDs `hades-vulkan`, `hades-dxvk`,
`portal2-d3d9`, `skywalker`, `steam-cef`. Every case supplies:

- `resolution: [1280, 720]`, `vsync: false`, `gameplay_confirmed: true`;
- hashed file records for `settings`, `scene`, `harness`, `game_build`,
  `visual_evidence` and `candidate_backend_log`;
- game cases: `baseline` and `candidate`, each with `runtime_sha256`, two
  `warmups` and three `measured` repetitions;
- warmups: `completed: true` and a hashed `log`;
- measured repetitions: `focused`, `awake`, `capture_valid`,
  `rendering_correct`, a hashed `visual_evidence` and hashed `frame_times`;
- CEF: `gpu_compositing: true` and `game_backend_preserved: true`.

A hashed file record is `{"path":"relative/file","sha256":"64 hex digits"}`.
Frame-time files contain a JSON array of positive finite milliseconds, at least
100 samples and 30 seconds. Candidate runtime digests must match the verified
archive. Backend logs must identify KosmicKrisp and, for DXVK paths, DXVK.
Keep the per-title settings/scene/game build identical between baseline and
candidate. Freeze the previous validated runtime as the baseline. Two untimed
warmups precede three measured repetitions. Median per-run means and p99 frame
times determine parity: losses exceeding 5% mean FPS or increases exceeding
10% p99 frame time block promotion. Reject sleep, focus loss or invalid capture.
The Python fixture tests exercise the gate; they are not game evidence.

Publication explicitly depends on build, consumer and both physical readiness
results, and additionally requires `WHISKY_LAYOUT_V2_AVAILABLE=true` after a
compatible Whisky has shipped. It advertises only the opt-in v2 canary catalog.
Missing licensed fixtures, physical OS coverage, consumer compatibility or
performance evidence must keep publication blocked. Withdraw a bad v2 catalog
entry and explicitly restore the previous runtime/pin to roll back.

## Review and evidence

Keep the coordinated WineCX, Whisky and hub commits focused and owner-signed.
Record exact commits, archive digest, host OS/hardware, commands and results.
A previous runtime's manually confirmed gameplay is useful baseline history;
it is not validation of the new artifact. Do not rewrite historical reports,
old catalogs or user data to make the migration appear complete.

Published runtime versions are immutable. Retrying an identical archive preserves
all existing assets; a different archive needs a new runtime version. The
publisher rejects collisions instead of replacing an older runtime.
