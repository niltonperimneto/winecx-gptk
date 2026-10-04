# winecx-gptk

CI build of a Game Porting Toolkit (GPTK / D3DMetal) capable Wine runtime for the [frankea/Whisky](https://github.com/frankea/Whisky) ecosystem: CodeWeavers' CrossOver 26.3 Wine changes, rebased onto upstream Wine 11.16/11.17, carrying series 4.7 up through **canary 4.7.51**.

> [!NOTE]
> For a comprehensive, detailed breakdown of all features, architecture shifts, and optimizations introduced since this repository was forked from `dappermint`, see the [Evolution & Changes Guide](docs/FORK-CHANGES.md).

## Why This Runtime Exists

Apple's Game Porting Toolkit / `D3DMetal` payload only executes on CrossOver-derived Wine builds because it patches their internal Unix call dispatch at load time (details in [frankea/Whisky#163](https://github.com/frankea/Whisky/issues/163), client-side loader in [frankea/Whisky#164](https://github.com/frankea/Whisky/pull/164)).

The source tree is based on the `wine1116` / `wine1117` branch of [niltonperimneto/winecx](https://github.com/niltonperimneto/winecx): CrossOver 26.3's diff merged onto upstream Wine via synthetic three-way rebasing, with platform patches committed directly in the tree. The workflow pins exact, immutable commits so branch movement cannot silently alter build outputs.

**What runs on it:** Steam UI end-to-end (Chromium CEF embedded views), D3D12 through D3DMetal at Feature Level 12_2 (binding tier 3, SM 6.6), D3D11 via Relay12 or DXVK/DXMT, msync, and the full Media Foundation / Quartz decoding stack.

---

## Key Subsystems & Major Advancements

### 1. Relay12 D3D11On12 Subsystem
Direct3D 11 can now execute on top of D3DMetal via [niltonperimneto/relay12](https://github.com/niltonperimneto/relay12). Process-selective routing rules (`RELAY12_EXPERIMENTAL_FRAME`, `RELAY12_EXPERIMENTAL_FRAME_APPS`, `RELAY12_EXPERIMENTAL_FRAME_SKIP`) ensure game binaries route D3D11On12 to D3DMetal while shielding Steam WebHelper and CEF processes from illegal interposition.

### 2. High-Performance GPTK Video & D3D12 Shim
* **Tight Alignment Reporting**: Resolves resource allocation alignment in [gptk-video/d3d12shim.c](gptk-video/d3d12shim.c), preventing D3DMetal crashes on strict memory boundaries.
* **Zero-Copy Barriers**: Preserves and passes through barrier batches over 32 elements without copying or latency overhead.
* **Per-Device YUV Blit PSOs**: Tracks pipeline state objects and color-conversion buffers per `ID3D12Device` in [gptk-video/yuvblit.h](gptk-video/yuvblit.h), eliminating texture leaks across video device recreation.

### 3. Dual Vulkan Tracks: MoltenVK + Experimental KosmicKrisp
* **Default Stack**: Ships MoltenVK 1.4.2 alongside `dxvk-macOS-async` and DXMT 0.80.
* **Experimental Track ([docs/kosmickrisp-experimental.md](docs/kosmickrisp-experimental.md))**: Ingests Mesa's KosmicKrisp Vulkan 1.4 driver over Metal via the Khronos Vulkan Loader.
  - **Rosetta 16 KiB Memory Budget Fix**: Carries [runtime/kosmickrisp/patches/0002-...](runtime/kosmickrisp/patches/0002-util-use-the-host-page-size-for-available-memory-on-.patch) to report true host memory to `VK_EXT_memory_budget`.
  - **fillModeNonSolid Polygon Emulation**: Maps `VkPolygonMode` to Metal triangle fill modes, enabling stock upstream DXVK 3.1.1 to initialize D3D9 and D3D11 (FL 11_1) devices.
  - **Geometry Shaders via Poly**: Lowers geometry pipeline stages into NIR compute passes.

### 4. Overhauled Modular Build & OCI Layer Caching
Replaced the monolithic build workflow with a 4-tier lifecycle pipeline and standalone tools in [tools/](tools/):
* **Layered OCI Caching ([docs/oci-build-system.md](docs/oci-build-system.md))**: Caches `sysroot` (Nixpkgs x86_64), `tools` (native Wine build tools), `payloads` (DXVK/DXMT/Mono/Gecko), and `driver` (KosmicKrisp Mesa).
* **Fast Developer Iteration**: Incremental Wine core compilation with `ccache` drops turnaround times from 50+ minutes to **3–5 minutes**.

### 5. Native ARM64 & FEX Research Lane ([arm64/](arm64/))
Provides scripts and patches preparing for life after Rosetta 2: native `arm64-apple-darwin` Wine Unix half, FEX-Emu JIT execution, and Apple Silicon virtual address space (low 4GB pagezero) analysis.

---

## Quality Gates & Verification

Every runtime build is gated against strict automated validation:

* **Relocatability Sweep**: Every Mach-O binary is swept for absolute store references; install names are rewritten to `@loader_path`.
* **dlopen Closure Validation**: Every bundled dylib is loaded with store paths masked via [tests/dlopenall.c](tests/dlopenall.c).
* **Window Creation & Media Probes**: Headless probes confirm the runtime can open a hosted Cocoa window and Media Foundation decoders function.
* **Architecture Integrity**: Verifies non-empty i386 WoW64 slices and stripped PE binaries.
* **Hardware & GPU Probes**: Synthetic Vulkan compute readbacks ([tests/kosmickrisp_probe.c](tests/kosmickrisp_probe.c)) and recording D3D12 interposer checks ([tests/d3d12shim.c](tests/d3d12shim.c)).

---

## Reproducibility & Pins

All inputs are strictly pinned in-tree:

| Input | Pin Location |
| :--- | :--- |
| **WineCX Sources** | `WINECX_COMMIT` in [tools/build/pins.env](tools/build/pins.env) |
| **Nixpkgs x86_64-darwin** | `NIXPKGS_REV` in [tools/build/pins.env](tools/build/pins.env) |
| **MoltenVK & DXVK** | Version + SHA-256 in [tools/build/pins.env](tools/build/pins.env) |
| **DXMT Canary** | Commit + Release Tag + SHA-256 in [tools/build/pins.env](tools/build/pins.env) |
| **Relay12** | Commit + Release Tag + SHA-256 in [tools/build/pins.env](tools/build/pins.env) |
| **KosmicKrisp & Mesa** | Revisions & patch digests in [runtime/kosmickrisp/pins.env](runtime/kosmickrisp/pins.env) |
| **Wine-Mono & Gecko** | Verified against WineCX `dlls/appwiz.cpl/addons.c` |

---

## Documentation Index

* **Fork Evolution**: [docs/FORK-CHANGES.md](docs/FORK-CHANGES.md)
* **Build Architecture**:
  - [Build System Overhaul Plan](docs/build-system-plan.md)
  - [OCI Layer Caching Guide](docs/oci-build-system.md)
  - [CI Execution Benchmarks](docs/oci-ci-results.md)
* **KosmicKrisp & Vulkan**:
  - [KosmicKrisp Migration Plan](docs/kosmickrisp-plan.md)
  - [Experimental Driver Architecture](docs/kosmickrisp-experimental.md)
  - [Performance & Memory Budget Analysis](docs/kosmickrisp-performance.md)
  - [Validation Results & Hades Testing](docs/kosmickrisp-test-results.md)
  - [Rosetta Deployment Guide](docs/kosmickrisp.md)
* **Direct3D & DDI Testing**: [docs/DDI-CONCURRENCY-TESTING.md](docs/DDI-CONCURRENCY-TESTING.md)
* **Native ARM64 / FEX Track**: [arm64/README.md](arm64/README.md)
