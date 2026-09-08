# AGENTS.md — D3D11On12 Architecture, Invariants & Agent Guidelines

> **Target Audience:** Autonomous Coding Agents, Subagents, and Systems Engineers  
> **Subsystem:** D3D11On12 (Direct3D 11 on Direct3D 12 Translation Layer & DDI Host)  
> **Components:** PE Router (`d3d11shim`), Core Boundary (`d3d11on12core`), Clean-Room DDI Host (`relay12-d3d11/ddi`)  

---

## 1. Mission and Subsystem Overview

This subsystem implements the host environment and driver boundary required to execute Microsoft's open-source D3D11On12 user-mode driver in Wine-compatible environments.

### Core Objectives
1. **PE Router (`d3d11shim.cpp`):** Presents the standard `d3d11.dll` export surface. It forwards standard device creation calls (`D3D11CreateDevice` and `D3D11CreateDeviceAndSwapChain`) to the platform's native D3D11 driver (`d3d11mt.dll`), while routing `D3D11On12CreateDevice` to the core boundary (`d3d11on12core.dll`).
2. **Core Boundary (`d3d11on12core.cpp`):** Validates caller-supplied `ID3D12Device` and `ID3D12CommandQueue` instances, confirms command queue types, enforces two-tier COM identity, and prepares the translation layer context.
3. **Clean-Room WDDM DDI Host (`relay12-d3d11/ddi/wine_d3d11ddi.h`):** Declares the driver callback interfaces (`D3DWDDM2_6DDI_DEVICEFUNCS`, `D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS`, `D3D10DDIARG_CREATEDEVICE`) from public documentation without copying proprietary Windows Driver Kit headers.
4. **Standalone Modularity:** Designed to operate as an independent component with its own compilation rules, static audits, test harnesses, and documentation.

---

## 2. Invariants and Constraints

All modifications to this codebase must preserve the following architectural invariants:

### 2.1 Natural 8-Byte Alignment (`/Zp8`)
- Direct3D DDI structures assume standard 64-bit Windows 8-byte natural alignment.
- **`#pragma pack` is strictly prohibited** under [`relay12-d3d11/ddi`](file:///Users/niltonperimneto/Whisky/relay12/relay12-d3d11/ddi). The presence of packing pragmas is actively checked by [`scripts/check_ddi_header.py`](file:///Users/niltonperimneto/Whisky/relay12/scripts/check_ddi_header.py).

### 2.2 Fail-Closed Routing Semantics
- **No Mock Success:** The router and core boundary must never return `S_OK` with mock, uninitialized, or partial COM interface pointers.
- **Documented Error Codes:** If dependencies (`d3d11mt.dll`, `d3d11on12core.dll`) or inputs are invalid, entry points must return documented Direct3D error codes (specifically `DXGI_ERROR_UNSUPPORTED`, `0x887a0004`). Non-standard Win32 or NT status codes must be avoided to ensure caller fallback logic functions properly.
- **Output Pointer Zeroing:** On any failure path, all caller-supplied output pointers (`ppDevice`, `ppImmediateContext`) must be set to `NULL` before returning.
- **Device Ownership:** D3D11On12 must submit rendering commands through the caller's supplied `ID3D12Device` and direct `ID3D12CommandQueue`. It must not create an independent or unmanaged device instance.

### 2.3 Strict Interface Acquisition and Identity
- **The `strictResult()` Funnel:** Every `QueryInterface` and `GetDevice` call in [`relay12-d3d11`](file:///Users/niltonperimneto/Whisky/relay12/relay12-d3d11) must be wrapped in `strictResult()`. If an interface query returns `S_OK` but leaves the output pointer null, `strictResult()` treats the acquisition as failed, preventing subsequent null pointer dereferences. Direct calls that bypass this funnel are rejected by [`scripts/check_interface_acquisition.py`](file:///Users/niltonperimneto/Whisky/relay12/scripts/check_interface_acquisition.py).
- **Two-Tier Identity Comparison:** To verify that a command queue was created by the provided device, typed `ID3D12Device` pointers are compared first. An `IUnknown` identity query is performed only if typed pointers differ.

### 2.4 Clean-Room Boundary and Licensing
- **No Proprietary WDK Headers:** Proprietary Windows Driver Kit headers (`d3d10umddi.h`, `d3d11umddi.h`, `dxgiddi.h`, `d3dkmthk.h`) must not be added to or vendored in this repository.
- **Dual-Source Documentation Validation:** All DDI structures declared in [`relay12-d3d11/ddi/wine_d3d11ddi.h`](file:///Users/niltonperimneto/Whisky/relay12/relay12-d3d11/ddi/wine_d3d11ddi.h) must be authored from public Microsoft documentation, cross-validated against the GitHub markdown documentation mirror, and documented with provenance comment blocks.
- **License Isolation:**
  - Router, Core, Tests, and Scripts: **GPL-3.0-only**
  - Submodules (`third_party/D3D11On12`, `third_party/D3D12TranslationLayer`, `third_party/DirectX-Headers`): **MIT**

---

## 3. Subsystem Architecture

```text
 ┌──────────────────────────────────────────────────────────────┐
 │                        Application                           │
 └──────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                     Router: d3d11shim.dll                    │
 │                                                              │
 │  Ordinal 1 & 2 (D3D11):           Ordinal 3 (D3D11On12):     │
 │  Forwards to d3d11mt.dll          Routes to d3d11on12core    │
 └──────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                Core Boundary: d3d11on12core.dll              │
 │  Validates ID3D12Device and direct ID3D12CommandQueue        │
 └──────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │             Clean-Room DDI Host (wine_d3d11ddi.h)            │
 │  WDDM 2.6 / 2.7 DeviceFuncs (178 slots) & Callbacks (47 slots│
 └──────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │     Microsoft D3D11On12 Driver & D3D12TranslationLayer       │
 └──────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                   Caller's ID3D12Device                      │
 └──────────────────────────────────────────────────────────────┘
```

### Component Breakdown

| Directory | Responsibilities |
| :--- | :--- |
| [`relay12-d3d11/`](file:///Users/niltonperimneto/Whisky/relay12/relay12-d3d11) | Implementation of `d3d11shim.cpp`, `d3d11on12core.cpp`, `wine_d3d11on12.h`, `wine_d3d11_diag.h`, and `ddi/wine_d3d11ddi.h`. |
| [`scripts/`](file:///Users/niltonperimneto/Whisky/relay12/scripts) | Static verification tools: `check_ddi_header.py`, `gen_ddi_layout.py`, `check_pe_audit.py`, `check_interface_acquisition.py`. |
| [`tests/`](file:///Users/niltonperimneto/Whisky/relay12/tests) | Verification tests: Python CI gate tests (`test_ci_gates.py`), mock core unit tests (`d3d11on12coretest.c`), DDI layout validation (`d3d11ddilayout.c`), and router status checks (`d3d11shimstatus.c`). |
| [`docs/`](file:///Users/niltonperimneto/Whisky/relay12/docs) | Architectural reference documents: [`D3D11ON12.md`](file:///Users/niltonperimneto/Whisky/relay12/docs/D3D11ON12.md) and [`CLEANROOM-DDI.md`](file:///Users/niltonperimneto/Whisky/relay12/docs/CLEANROOM-DDI.md). |
| [`third_party/`](file:///Users/niltonperimneto/Whisky/relay12/third_party) | Pinned submodules: `D3D11On12`, `D3D12TranslationLayer`, `DirectX-Headers`. |

---

## 4. Compilation and Toolchain Rules

### 4.1 MinGW-w64 GCC Configuration
- PE binaries are compiled with `x86_64-w64-mingw32-g++` in C++17 mode.
- Linkage against `libstdc++` and `libgcc_s` is prohibited to ensure runtime independence; PE binaries must import only `kernel32.dll` and `msvcrt.dll`.
- Code must be compiled with `-fno-exceptions -fno-rtti`.

### 4.2 PE Export Tables
[`scripts/check_pe_audit.py`](file:///Users/niltonperimneto/Whisky/relay12/scripts/check_pe_audit.py) enforces exact export tables and ordinals:

#### `d3d11shim.dll` (Router)
| Ordinal | Symbol | Purpose |
| ---: | :--- | :--- |
| 1 | `D3D11CreateDevice` | Forwards to `d3d11mt.dll` |
| 2 | `D3D11CreateDeviceAndSwapChain` | Forwards to `d3d11mt.dll` |
| 3 | `D3D11On12CreateDevice` | Routes to `d3d11on12core.dll` |
| 4 | `WineD3D11ShimGetStatus` | Reports module status |

#### `d3d11on12core.dll` (Core Boundary)
| Ordinal | Symbol | Purpose |
| ---: | :--- | :--- |
| 1 | `WineD3D11On12GetABIVersion` | Returns `WINE_D3D11ON12_ABI_VERSION` |
| 2 | `WineD3D11On12CreateDeviceV1` | Validated device creation entry point |
| 3 | `WineD3D11On12GetInterface` | Returns interface function table |

### 4.3 Diagnostic Logging
Diagnostic logging is handled via [`relay12-d3d11/wine_d3d11_diag.h`](file:///Users/niltonperimneto/Whisky/relay12/relay12-d3d11/wine_d3d11_diag.h):
1. Dynamically queries `__wine_dbg_output` from `ntdll.dll` via `GetProcAddress`.
2. Falls back to `OutputDebugStringA`.
3. Falls back to standard error via `msvcrt.dll`.

Deduplication latches ensure repeated failure conditions log only once per process.

---

## 5. Agent Verification Protocol

Before submitting code modifications, verify that all four static gates pass:

```bash
# 1. Run Python CI gate unit tests
python3 -m unittest discover -s tests -p "test_*.py"

# 2. Check DDI layout model against header declarations
python3 scripts/gen_ddi_layout.py --check

# 3. Check DDI header provenance and verify absence of #pragma pack
python3 scripts/check_ddi_header.py

# 4. Verify that interface acquisitions use strictResult()
python3 scripts/check_interface_acquisition.py relay12-d3d11
```

All commands must exit with code `0`.
