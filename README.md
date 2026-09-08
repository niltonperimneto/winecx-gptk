# D3D11On12: Direct3D 11 on Direct3D 12 Translation Layer

> A translation layer and clean-room driver interface host that enables Direct3D 11 applications to execute on top of Direct3D 12 runtimes.

---

## Introduction: What is D3D11On12?

Direct3D (often called DirectX) is the graphics library used by many Windows applications and games to render 3D scenes. Over time, Microsoft released different major versions:
- **Direct3D 11 (D3D11):** A high-level graphics programming model where the graphics driver manages memory, resource synchronization, and command scheduling behind the scenes.
- **Direct3D 12 (D3D12):** A low-level graphics model where the application explicitly controls memory allocation, synchronization fences, and GPU command queues.

On platforms where Direct3D 12 is the primary or best-supported graphics pathway, applications that were written for Direct3D 11 cannot run directly without a translation mechanism.

**D3D11On12** provides this translation mechanism. It exposes the standard Direct3D 11 programming interfaces to the application, while internally converting all state changes, draw calls, and resource management into Direct3D 12 commands.

```text
 ┌──────────────────────────────────────────────────────────────┐
 │                Direct3D 11 Application / Game                │
 └──────────────────────────────┬───────────────────────────────┘
                                │ Calls D3D11CreateDevice /
                                │ D3D11On12CreateDevice
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │            Router: d3d11shim.dll (d3d11.dll)                 │
 │   Routes standard D3D11 to native driver or D3D11On12 core   │
 └──────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │          Core Validation Boundary: d3d11on12core.dll         │
 │   Validates D3D12 devices, command queues, and COM identity  │
 └──────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │          Clean-Room DDI Host (wine_d3d11ddi.h)               │
 │   Provides standard WDDM 2.6 / 2.7 driver callback interface │
 └──────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │           Microsoft D3D11On12 User-Mode Driver &             │
 │                   D3D12TranslationLayer                      │
 └──────────────────────────────┬───────────────────────────────┘
                                │ Submits commands
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                 Direct3D 12 Hardware / Driver                │
 └──────────────────────────────────────────────────────────────┘
```

---

## Purpose of this Project

This project implements the host environment and driver infrastructure required to run Microsoft's open-source D3D11On12 user-mode driver in Wine-based and compatible environments:

1. **PE Router (`d3d11shim.dll`):** A replacement for `d3d11.dll` that exports standard entry points (`D3D11CreateDevice`, `D3D11CreateDeviceAndSwapChain`, and `D3D11On12CreateDevice`). It forwards standard creation calls to native implementations (such as `d3d11mt.dll`) and routes `D3D11On12CreateDevice` to the core boundary.
2. **Core Validation Boundary (`d3d11on12core.dll`):** Validates caller-supplied `ID3D12Device` and `ID3D12CommandQueue` pointers, confirms command queue types, enforces two-tier COM identity checks, and initializes the DDI host.
3. **Clean-Room WDDM DDI Host (`relay12-d3d11/ddi/wine_d3d11ddi.h`):** Reconstructs the necessary Windows Driver Model (WDDM 2.6 and 2.7) structures and function tables from public specifications without copying proprietary Windows Driver Kit headers.
4. **Verification Framework:** Provides automated layout checks, mock-object unit tests, and static code audits to prevent interface mismatches and ABI drift.

---

## Architecture and Components

### 1. The PE Router (`relay12-d3d11/d3d11shim.cpp`)

Applications link against `d3d11.dll` to access Direct3D 11 functionality. The router fulfills this role while maintaining exact export compatibility:

| Export Ordinal | Function Name | Routing Behavior |
| ---: | :--- | :--- |
| 1 | `D3D11CreateDevice` | Forwards to `d3d11mt.dll` |
| 2 | `D3D11CreateDeviceAndSwapChain` | Forwards to `d3d11mt.dll` |
| 3 | `D3D11On12CreateDevice` | Validates inputs and routes to `d3d11on12core.dll` |
| 4 | `WineD3D11ShimGetStatus` | Reports component readiness and initialization state |

If dependencies (`d3d11mt.dll` or `d3d11on12core.dll`) are unavailable, the router returns `DXGI_ERROR_UNSUPPORTED` (`0x887a0004`) and clears all output pointers. This ensures calling applications can detect unsupported configurations and select alternative rendering paths.

### 2. The Core Boundary (`relay12-d3d11/d3d11on12core.cpp`)

The core module receives Direct3D 12 device pointers and configuration flags from the caller. Before initializing the translation driver, it applies several safety verifications:

- **Command Queue Verification:** Inspects the caller-supplied `ID3D12CommandQueue` description to confirm it is a direct queue (`D3D12_COMMAND_LIST_TYPE_DIRECT`). Compute or copy queues cannot serve as primary queues for Direct3D 11 presentation.
- **Two-Tier COM Identity:** Verifies that the command queue was created by the supplied device. It compares typed `ID3D12Device` pointers first, only querying `IUnknown` identity if the typed pointers differ.
- **Strict Acquisition Funnel:** All interface queries funnel through `strictResult()`. If a query returns `S_OK` but leaves the output pointer null, the call is treated as a failure to avoid subsequent null pointer dereferences.

### 3. The Clean-Room DDI Interface (`relay12-d3d11/ddi/wine_d3d11ddi.h`)

Microsoft's D3D11On12 driver communicates with the host through the user-mode driver interface (DDI). Because proprietary driver development headers cannot be used, all structures are clean-room declared from public documentation:

- **Version Negotiation:** The driver negotiates WDDM 2.7 while utilizing `D3DWDDM2_6DDI_DEVICEFUNCS` (178 function slots) and `D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS` (47 callback slots).
- **Dual-Source Cross-Validation:** Every structure is verified against Microsoft Learn documentation pages and corresponding GitHub markdown documentation mirrors to confirm field order, type sizes, and member counts.
- **Layout Model Verification:** Structure layouts are checked against an independent Python layout generator ([`scripts/gen_ddi_layout.py`](file:///Users/niltonperimneto/Whisky/relay12/scripts/gen_ddi_layout.py)) to ensure offsets and alignments match 64-bit Windows natural alignment rules (`/Zp8`).

---

## Directory Structure

| Path | Purpose |
| :--- | :--- |
| [`relay12-d3d11/`](file:///Users/niltonperimneto/Whisky/relay12/relay12-d3d11) | Implementation of the router (`d3d11shim.cpp`), core boundary (`d3d11on12core.cpp`), ABI header (`wine_d3d11on12.h`), diagnostic logging (`wine_d3d11_diag.h`), and clean-room DDI headers (`ddi/wine_d3d11ddi.h`). |
| [`scripts/`](file:///Users/niltonperimneto/Whisky/relay12/scripts) | Static verification tools and compliance gates: `check_ddi_header.py`, `gen_ddi_layout.py`, `check_pe_audit.py`, `check_interface_acquisition.py`. |
| [`tests/`](file:///Users/niltonperimneto/Whisky/relay12/tests) | Test suite: Python CI gate tests (`test_ci_gates.py`), mock core unit tests (`d3d11on12coretest.c`), DDI layout validation (`d3d11ddilayout.c`), and router status checks (`d3d11shimstatus.c`). |
| [`docs/`](file:///Users/niltonperimneto/Whisky/relay12/docs) | Technical specifications: [`D3D11ON12.md`](file:///Users/niltonperimneto/Whisky/relay12/docs/D3D11ON12.md) (system architecture and roadmap) and [`CLEANROOM-DDI.md`](file:///Users/niltonperimneto/Whisky/relay12/docs/CLEANROOM-DDI.md) (DDI authoring method and worklist). |
| [`third_party/`](file:///Users/niltonperimneto/Whisky/relay12/third_party) | Pinned submodules: `D3D11On12`, `D3D12TranslationLayer`, and `DirectX-Headers`. |

---

## Verification and Safety Gates

To maintain stability and prevent regression across compiler toolchains, four static audits and unit test harnesses are executed:

| Gate Command | Purpose |
| :--- | :--- |
| `python3 -m unittest discover -s tests -p "test_*.py"` | Verifies that all CI static gate scripts and verification rules function as expected. |
| `python3 scripts/gen_ddi_layout.py --check` | Compares clean-room DDI header field offsets against an independent layout calculation model. |
| `python3 scripts/check_ddi_header.py` | Validates documentation provenance blocks (URLs and retrieval dates) and verifies that `#pragma pack` is not used. |
| `python3 scripts/check_interface_acquisition.py relay12-d3d11` | Confirms that every `QueryInterface` and `GetDevice` call routes through `strictResult()`. |

---

## Further Reading

- **[docs/D3D11ON12.md](file:///Users/niltonperimneto/Whisky/relay12/docs/D3D11ON12.md):** Complete architectural design, component boundaries, failure modes, and rollout checklist.
- **[docs/CLEANROOM-DDI.md](file:///Users/niltonperimneto/Whisky/relay12/docs/CLEANROOM-DDI.md):** Clean-room WDDM DDI authoring guidelines, version negotiation proof, and implementation worklist.
- **[AGENTS.md](file:///Users/niltonperimneto/Whisky/relay12/AGENTS.md):** Architecture invariants, safety rules, and guidelines for automated coding agents.
- **[SKILLS.md](file:///Users/niltonperimneto/Whisky/relay12/SKILLS.md):** Step-by-step procedures for layout generation, compilation checks, and test execution.

---

## Licensing

- **Router, Core, Tests, and Tools:** Licensed under the [GNU General Public License v3.0](file:///Users/niltonperimneto/Whisky/relay12/LICENSE) (`GPL-3.0-only`).
- **Submodules (`D3D11On12`, `D3D12TranslationLayer`, `DirectX-Headers`):** Licensed under the [MIT License](file:///Users/niltonperimneto/Whisky/relay12/THIRD_PARTY_NOTICES.md).
