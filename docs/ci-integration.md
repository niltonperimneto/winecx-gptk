# Cross-repository CI

winecx-gptk is the hub connecting WineCX, Relay12, Mesa, DXMT, external payloads
and the Whisky consumer. It pins components, assembles and validates the runtime,
then publishes eligible builds. The current automated `component-updated` flow
covers WineCX, Mesa and Relay12; it does not automatically update every payload.
See [architecture and ownership](architecture.md) for code boundaries and
[QA and release readiness](qa.md) for what the checks establish.

```
winecx ──┐                      ┌── core (Wine)        ┐
relay12 ─┼─ component-updated ─▶│   payloads (DXVK,    ├─▶ assemble ─▶ validate ─▶ publish ─▶ Whisky
mesa ────┘   (repository_       │   DXMT, relay12)     │                            canary +     (runtime-published
             dispatch)          └── kosmickrisp (Mesa) ┘                            catalog      → RuntimeIntegration)
```

## Flow

1. Each component repository runs its own CI on pull requests:
   - **winecx:** compiles ntdll, win32u, winemac, mountmgr and the d3d11 PE modules for x86_64.
   - **relay12:** runs the D3D11On12 validation suite.
   - **mesa:** runs the KosmicKrisp build and its meson tests.
2. After a merge to `main` passes, the component sends
   `repository_dispatch: component-updated` to this repository. relay12 first
   publishes its `runtime-<sha7>` release.
3. `bump-pins.yml` runs `tools/build/bump_pin.py`, which moves the matching
   pin and verifies it (relay12's archive digest, Wine's vendored FAudio
   version). It then opens `bump/<component>-<sha7>` with auto-merge. A newer
   bump of the same component closes the older one. Auto-merge remains subject
   to the repository's configured checks and permissions; it is not a substitute
   for reviewing integration evidence. DXMT and other payload updates need
   separate verified pin changes because this dispatcher does not cover them.
4. `build.yml` builds the pull request. Every OCI layer is keyed by
   `tools/build/cache_key.py` over only its own inputs:

   | Change | Rebuilt layers |
   |---|---|
   | winecx pin | tools, core |
   | relay12 / DXMT / DXVK pin | payloads |
   | Mesa pin | kosmickrisp |
   | nixpkgs pin | sysroot, tools, core |
   | `OPT_LEVEL` | core |

   A Wine update can also change payload keys when its `addons.c` changes the
   Mono/Gecko inputs. Recipe, SDK and toolchain changes have their own effects;
   inspect the key implementation and tests rather than treating this table as
   an exhaustive dependency graph.

   Every other layer is restored from GHCR. `tests/test_oci_build.py` asserts
   this table. Assembly and validation always run because they combine all
   layers.
5. For eligible validated non-fast builds on `main`, `publish` cuts the canary
   release, updates `runtime-catalog.json` and sends `runtime-published` to Whisky.
   Whisky's `RuntimeIntegration.yml` downloads the archive and checks it against
   `contracts/runtime-layout.json`.

The base validation output and separate experimental KosmicKrisp validation and
readiness jobs are distinct. The current `publish` job depends on base `build`,
not every experimental job. Inspect its conditions and selected artifact before
claiming a graphics readiness result gates publication.

## Contract

`contracts/runtime-layout.json` lists the paths under `Libraries/` that
Whisky relies on. `tools/package_runtime.sh` refuses to package a tree that
breaks it, and Whisky's contract tests check every published archive against
the same file. Change both sides together.

## QA baseline

`.github/workflows/qa-common.yml` is called by every repository. It runs:

- actionlint;
- shellcheck at warning severity;
- ruff for syntax errors and undefined names;
- `git diff --check` on pull requests.

Each caller excludes its vendored or upstream trees. Dependabot keeps the
actions current.

## Secrets and variables

| Name | Where | Purpose |
|---|---|---|
| `HUB_DISPATCH_TOKEN` | winecx, relay12, mesa, winecx-gptk | Token scoped to participating repositories for cross-repository dispatches and bump PR creation. The bump workflow uses it so the PR can trigger normal CI. |
| `MACOS_GPU_RUNNER` (variable) | winecx-gptk | Runner label for experimental assembly and GPU validation. Unset means hosted macOS; hardware capability must still be verified. |

`MACOS_GPU_RUNNER` also selects experimental assembly and reusable validation
hosts. A hosted macOS runner may lack a Metal 4 device; selecting a runner does
not make unavailable hardware checks pass or change branch-protection rules.

Notification steps can warn and continue without `HUB_DISPATCH_TOKEN`, but
`bump-pins.yml` explicitly requires it, including for a manual workflow dispatch.
The pin helper can also be run locally with appropriate source/artifact access;
submitting that change still requires normal review and validation.
