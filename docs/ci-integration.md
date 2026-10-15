# Cross-repository CI

Five repositories build one product. winecx-gptk is the hub: it pins every
component, assembles the runtime and publishes it for Whisky.

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
   bump of the same component closes the older one.
4. `build.yml` builds the pull request. Every OCI layer is keyed by
   `tools/build/cache_key.py` over only its own inputs:

   | Change | Rebuilt layers |
   |---|---|
   | winecx pin | tools, core |
   | relay12 / DXMT / DXVK pin | payloads |
   | Mesa pin | kosmickrisp |
   | nixpkgs pin | sysroot, tools, core |
   | `OPT_LEVEL` | core |

   Every other layer is restored from GHCR. `tests/test_oci_build.py` asserts
   this table. Assembly and validation always run because they combine all
   layers.
5. On `main`, `publish` cuts the canary release, updates
   `runtime-catalog.json` and sends `runtime-published` to Whisky. Whisky's
   `RuntimeIntegration.yml` downloads the archive and checks it against
   `contracts/runtime-layout.json`.

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
| `HUB_DISPATCH_TOKEN` | winecx, relay12, mesa, winecx-gptk | Fine-grained PAT with Contents and Actions write on the five repositories. It sends the dispatches, opens bump pull requests and, as an admin of the protected `main`, pushes the canary catalog. GITHUB_TOKEN cannot, because pull requests it opens do not start workflows. |
| `MACOS_GPU_RUNNER` (variable) | winecx-gptk | Optional runner label for physical-GPU KosmicKrisp validation. Unset means the hosted runner. It is never a required check. |

Without the token, every notify step only warns, and pins can still be bumped
by dispatching `bump-pins.yml` by hand.
