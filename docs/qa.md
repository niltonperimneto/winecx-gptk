# QA and release readiness

The hub's primary responsibility is delivering a runtime that preserves working
behavior. Faster compilation, a new feature, or a green component build does not
justify a regression in the assembled product. [AGENTS.md](../AGENTS.md) states
the rules; this guide explains what the evidence means.

## Acceptance before implementation

Choose an observable acceptance condition and the scope of possible regression
before editing. Capture a baseline where practical. For a bug, prefer a test
that fails on the original behavior and passes on the fix. Cover relevant error
paths as well as success, especially for archive validation, checksums, process
ownership, concurrency, DLL setup and recovery.

Keep tests proportional. Documentation-only changes require review of claims,
links, examples and whitespace, not a complete runtime rebuild. Shared helpers,
pins and packaging changes need broader integration coverage. Use the
[change-to-QA matrix](../SKILLS.md#select-the-required-qa) to select the scope.

## Layers of evidence

| Layer | What it establishes | What it does not establish |
| --- | --- | --- |
| Static QA | Checked syntax, shell pitfalls, selected Python errors, workflow validity and whitespace | A working compiled runtime |
| Python/unit/contract tests | Specific helper behavior, cache invalidation and represented consumer requirements | All native ABI or GPU behavior |
| Component or module build | The selected sources compile with that toolchain | A complete, relocatable package |
| Assembled runtime checks | Required payloads, loader/dependency and platform checks on that artifact | Every graphics route and game |
| GPU readback/presentation | The tested device, architecture and operation produce the expected result | Broad shader correctness or gameplay |
| Focused game test | The observed title, backend, settings and progression work for that run | Unrelated games, configurations or steady-state performance |
| Controlled benchmark | Repeatable performance within the measured scene and conditions | Correctness in untested paths or proof of a proposed cause |

### Static and Python checks

The shared [qa-common.yml](../.github/workflows/qa-common.yml) defines actionlint,
ShellCheck severity, Ruff rules and PR whitespace checks. Use its current tool
versions and exclusions. The main workflow runs:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

For a focused layout regression, for example:

```sh
python3 -m unittest discover -s tests -p 'test_runtime_layout.py' -v
```

Keep these suites useful without GPU access where possible. Hardware-independent
tests should not pretend to exercise a real Metal device. Platform skips must
be specific and explained; they are not passes for the skipped behavior.

### Build, assembly and consumer validation

[run_probes.sh](../tools/run_probes.sh) checks the packaged tree for relocation,
deployment floor, symbol availability, architecture integrity and runtime
behavior, including window, media, bundled-library and network probes. Relevant
interposer tests must also remain intact. Exact checks are defined by the script
and [validate.yml](../.github/workflows/validate.yml).

Use the intended SDK and deployment floor. A clean symbol audit against a newer
SDK alone does not prove availability on the minimum OS. Do not suppress an API
availability warning or widen a symbol allowlist merely to pass the audit.
Optional weak Vulkan imports have a source-derived allowlist with constrained
scope; unresolved strong or unrelated symbols remain errors.

[package_runtime.sh](../tools/package_runtime.sh) creates the file inventory,
checks the consumer layout and emits the archive and checksum. The layout test
checks paths, so keep the architecture, signature, link, hash and runtime checks
as independent requirements. Coordinate contract changes with Whisky's consumer
tests. Validate a relocated artifact, including paths containing spaces.

### GPU and game validation

Hosted macOS availability does not imply a compatible Metal 4 GPU. Driver
compilation, physical-device enumeration, shader readback, presentation and
packaged-runtime readiness are separate results. The workflows require physical runner labels `MACOS_GPU_RUNNER_26` and
`MACOS_GPU_RUNNER_NEWER` for deployment-floor and newer-OS validation. Missing
configuration fails readiness; hosted compilation cannot satisfy these gates.
See [layout v2 promotion](runtime-layout-v2.md) for the exact game/performance contract.

Check the actual backend, driver revision and 32/64-bit coverage in logs. Keep
experimental driver readiness and migration checks distinct from the base
runtime build. Do not treat skipped or optional jobs as a green result for the
behavior they did not test. See [CI integration](ci-integration.md) for the
current job/permission boundaries; requirements for a particular PR may be
stricter than the repository's configured required-check list.

Use disposable prefixes and owned processes. Record startup, menu interaction,
level loading and playable rendering separately. Attribute a user's manual
gameplay confirmation as manual evidence. A missing automation observation,
locked desktop, lost focus or normal process exit does not prove a game defect.

For performance, hold scene, resolution, graphics settings, driver, runtime and
cache state constant; repeat runs and report variability. Separate cold startup,
loading and shader compilation from steady gameplay. A stall coinciding with a
compile is correlation, not proof that compilation caused it. Exclude or flag
sleep, interruptions and invalid visibility rather than silently averaging them.

## Evidence to attach

A reviewer should be able to identify and reproduce the tested result from:

- Hub commit, component revisions and artifact/OCI digest.
- OS, SDK, host and Windows architecture, relevant hardware and backend.
- Reproduction steps, fixture or scene, settings and cache state.
- Commands and final outcomes: passed, failed, skipped, blocked or not run.
- Relevant CI run/job links and retained logs or screenshots; no credentials,
  user saves, account tokens or private game data.
- Baseline comparison, known limits and attribution of manual confirmations.

Keep concise findings in maintained documentation and larger artifacts in CI
storage or a verified ignored local location. Correct reports when new evidence
supersedes an earlier conclusion; preserve enough provenance to explain why.

## Ready for review versus ready to release

A draft can be reviewable while required hardware evidence is pending, provided
that gap is explicit. Release readiness requires the applicable final-commit
checks, assembled-artifact validation, supported-platform evidence and consumer
compatibility. All relevant new failures must be resolved. A locally successful
fast build or a queued CI run is not release evidence.

GitHub required checks, protected branches and auto-merge are configured outside
these documents. The current publish job consumes the base validation output;
do not assume every separate experimental readiness job gates that job. Inspect
the live workflow conditions and the artifact selected for publication.

If validation fails, keep the failing evidence, determine the owning component,
add regression coverage and rerun affected checks after the fix. Do not weaken
the assertion, relabel a failure, publish an unverified artifact or assert that
an unavailable check passed. If required validation cannot be completed, report
the blocker and leave release readiness unconfirmed.
