# Experimental KosmicKrisp & Upstream DXVK Migration Plan

This document outlines the evaluation and integration path for migrating from the `MoltenVK + Gcenx/DXVK-macOS` stack to an `Vulkan Loader + KosmicKrisp ICD + Upstream DXVK` architecture within the `winecx-gptk` runtime. 

Unlike the MoltenVK model, replacing the stack with upstream DXVK is not guaranteed by Vulkan conformance. Success is strictly conditional on feature availability (such as geometry shaders and transform feedback), correctness under Rosetta x86_64, and performance validation against the current stack.

The current default stack (`MoltenVK + Gcenx/DXVK-macOS`) will be preserved until the KosmicKrisp backend is proven stable and performant enough to replace it.

## 1. Context and Goals

KosmicKrisp is a Vulkan 1.4 conformant Vulkan-on-Metal implementation built within Mesa. While conformance guarantees base capabilities, DXVK 2.x and 3.x explicitly require optional features like geometry shaders and transform feedback, which are not uniformly exposed in all KosmicKrisp feature sets.

Therefore, the objective is to build an experimental track parallel to the existing implementation, moving through strict validation gates to test feasibility and performance.

### Key Architectural Shifts:
1. **Loader Delegation**: KosmicKrisp does **not** support the direct library loading approach used by MoltenVK. The macOS Vulkan loader is strictly required to route calls through an ICD manifest JSON to the driver.
2. **Rosetta Match**: The Unix half of the Wine runtime runs strictly as `x86_64` under Rosetta. KosmicKrisp and the Vulkan loader must therefore be compiled and bundled as `x86_64` libraries in order to be dynamically linked by this process, even if the driver executes on Apple Silicon GPUs.

---

## 2. Integration Gates

### Gate 1: Toolchain, Bundling, and X86_64 Compilation
- Prepare cross-build machinery (e.g., using `shadexternals/mesa-kosmickrisp` concepts) to compile an **x86_64** slice of Mesa (KosmicKrisp), the Vulkan loader (`libvulkan.1.dylib`), and their dependencies (like SPIRV-Tools) on a macOS ARM64/x86_64 host.
- Package the Vulkan loader, the KosmicKrisp driver, the ICD JSON manifest, and required dependencies into a discrete runtime bundle. 
- Ensure `VK_DRIVER_FILES` resolution allows deterministic driver discovery from Whisky or Wine at launch, with relocatable paths for the JSON manifest and dylibs.
- **Outcome:** A shippable `x86_64` slice of KosmicKrisp usable via the Vulkan loader interface.

### Gate 2: Wine Loader & Presentation Validation
- Configure Wine to prefer the Vulkan loader over MoltenVK via `ac_cv_lib_soname_vulkan="libvulkan.1.dylib"`.
- Verify Wine correctly resolves the ICD through the Vulkan loader and identifies the KosmicKrisp physical device string.
- The KosmicKrisp macOS driver uses `VK_EXT_metal_surface` via `CAMetalLayer` under the hood. Render a basic 3D instance (e.g., passing `vkfeat.c` under `winvulkan.dll`).
- Validate standard presentation lifecycle: Swapchains, resizing, and fullscreen switching within a hosted macOS window under Wine.

### Gate 3: Upstream DXVK Feature Audit
- Establish a pinned upstream DXVK release (e.g., DXVK 2.4 or 3.x) intended for evaluation.
- Extend `tests/vkfeat.c` and internal probes to inspect `VkPhysicalDeviceFeatures2`, extension feature chains (e.g., Geometry Shaders, Transform Feedback), and device limits. Exclude existing shim feature-masking to enforce honesty.
- Match KosmicKrisp's exposed feature set directly against the D3D11 device configuration requirements from the pinned DXVK release.
- **Outcome**: A definitive answer to whether KosmicKrisp implements all mandatory and optional features upstream DXVK considers strictly necessary in its device creation pass.

### Gate 4: Execution Validation
- Verify D3D9, D3D10, and D3D11 rendering with upstream DXVK over KosmicKrisp. Validate both x86_64 and i386 PE architectures under macOS Rosetta.
- Ascertain that the Steam UI successfully loads and maps UI swapchains through chromium.
- Profile and benchmark representative titles against the `MoltenVK + Gcenx/DXVK-macOS` stack baseline. Ensure visual correctness matches or exceeds the legacy layer.

---

## 3. Retaining the Baseline

Throughout this implementation cycle, the existing `.github/workflows/build.yml` fetching logic (for MoltenVK dynamically downloaded from Khronos and `dxvk-macOS-async` from Gcenx) must remain structurally intact.

The release process will not substitute standard MoltenVK builds until the performance metrics and feature compatibility thresholds verified in Gate 4 meet production requirements.
