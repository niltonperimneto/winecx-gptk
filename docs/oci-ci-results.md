# OCI pipeline test results — 2026-10-03

Tests ran on the `codex/oci-build-ci` branch. The branch guard prevented canary
release/catalog publication; GHCR build layers, Docker images, and Actions test
artifacts were published as part of the integration tests.

## Standard runtime: full first build passed

[Full Actions run](https://github.com/niltonperimneto/winecx-gptk/actions/runs/37143173913)
completed successfully. It exercised:

- Pinned Darwin Nix closure/toolchain export, GHCR publication, and import on
  fresh macOS runners.
- Native Wine tools build, publication, and restore on the core runner.
- SHA-verified external addons and graphics payloads.
- Wine configure, compilation, and `install-lib` staging.
- Assembly, GameModeProcessHost checks, Mach-O relocation, signing, and stamping.
- Relocatability, deployment floor, and symbol availability gates.
- Windows creation and media decoding probes.
- `dlopen` of **694 bundled libraries**, with **zero failures**.
- WSARecvMsg IPv4 TOS, IPv6 traffic class, and overlapped-receive verification.
- D3D12 interposer and all seven Relay12 routing cases.
- Runtime manifest generation, archive packaging, GHCR runtime artifact, and
  Actions runtime artifact.
- Dockerfile builds and GHCR pushes for sysroot, tools, payloads, core, and
  runtime transport images.

The Wine configure/compile/install step took **25 minutes 7 seconds**; assembly
work after restore took **2 minutes 16 seconds**. The complete first run took
about **55 minutes**. These measurements do not support the plan's estimated
12–15 minute cold Wine build on this hosted runner.

## Warm-cache/reusable-validation test

[Follow-up Actions run](https://github.com/niltonperimneto/winecx-gptk/actions/runs/37144484110)
tests cached sysroot/tools/payload restores, warmed ccache, the reusable
`validate.yml` workflow, and Dockerfile composition/export with envelope checks.
Foundation build, native-tools build, and payload fetching were all skipped
because their OCI layers were available. Foundation restore/setup took
**2 minutes 37 seconds**. The full follow-up run **passed**, including the
reusable validator and Docker composition/export with checksum verification of
all four exported input packages. Exported files totalled about 931 MB.

This follow-up's Wine compile/install step took **18 minutes 42 seconds**,
before the PE compiler-alias cache fix. It exposed that Wine selects the
`gcc`/`g++` llvm-mingw aliases while the inherited wrapper list only covered
`clang`/`clang++`. Those aliases are now covered, with Clang explicitly selected
as the [ccache compiler type](https://ccache.dev/manual/latest.html#_configuration).

[The targeted cache-fix Actions run](https://github.com/niltonperimneto/winecx-gptk/actions/runs/37156584664)
**passed** with the real pinned Darwin llvm-mingw toolchain: both C and C++,
both PE architectures, and all compiler aliases produced **16 cacheable calls**,
**8 first-call misses**, and **8 direct cache hits** on repetition. The full
pipeline was tested before this final wrapper-only fix; the fix was validated
separately in this real-compiler integration test. A full post-fix Wine timing
benchmark has not been run, so a 3–5 minute full compile is not claimed.

## Driver transport and contract tests passed

[Driver integration, compiler cache, and Linux unit tests](https://github.com/niltonperimneto/winecx-gptk/actions/runs/37156584664)
passed. All **23 Python tests** passed on an Ubuntu Actions runner, including
checksum/component verification, traversal/link protection, digest-only pulls,
cache-miss versus authentication-failure handling, Nix closure import, and
cache-key dependency isolation.

The KosmicKrisp compiler produced the x86_64 driver and loader on macOS, then
published the OCI layer. Repeated tests restored the same digest on fresh
runners, moved it into a path with spaces, and loaded all **three** bundled
libraries successfully. This included cache-hit runs that skipped compilation.

GPU validation was **blocked/skipped on hosted Actions**, rather than passed.
The runner reported `device=Apple Paravirtual device metal4=false`. The pinned
Mesa source selects devices supporting `MTLGPUFamilyMetal4`; a generic Metal
device is insufficient. The initial enumeration failure exposed this limitation.
Compiled layers are now retained independently of real GPU validation, while
experimental runtime assembly keeps the device probe strict.

## Same OCI driver: physical GPU test passed locally

The exact CI-produced layer, exported through an Actions artifact in
[the driver test run](https://github.com/niltonperimneto/winecx-gptk/actions/runs/37144958504),
was checksum-verified, extracted into a relocated directory, and probed locally:

```text
device=Apple A18 Pro driver=KosmicKrisp id=28
api=1.4.363 maxPushConstantsSize=256
geometryShader=1 tessellationShader=1 shaderInt64=1 fillModeNonSolid=1
KosmicKrisp device creation passed (no DXVK compatibility claim)
```

This establishes host enumeration and device creation on physical Metal 4
hardware. It does not establish DXVK game compatibility or claim hosted GPU
validation. Configure `MACOS_GPU_RUNNER` with a suitable macOS 26 runner label
for experimental assembly and GPU gates.

Local Actions syntax linting, ShellCheck, and whitespace checks passed as well.
