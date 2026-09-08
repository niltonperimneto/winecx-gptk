# SKILLS.md — D3D11On12 Procedures, Recipes & Verification

> **Target Audience:** Autonomous Coding Agents, Subagents, and Systems Engineers  
> **Subsystem:** D3D11On12 (Translation Layer & DDI Host)  
> **Prerequisites:** Python 3.10+, MinGW-w64 GCC (`x86_64-w64-mingw32-gcc` / `g++`), Wine execution environment  

---

## 1. Skill Matrix Overview

This document provides operational procedures and diagnostic routines for developing and maintaining the D3D11On12 translation layer and clean-room DDI host.

| ID | Skill Name | Primary Components | Typical Scenarios |
| :--- | :--- | :--- | :--- |
| **SK-01** | [Clean-Room DDI Authoring & Provenance](#sk-01-clean-room-ddi-authoring--provenance) | `ddi/wine_d3d11ddi.h`, `check_ddi_header.py` | Adding DDI function tables, callback tables, handle types |
| **SK-02** | [DDI Layout Derivation & Drift Verification](#sk-02-ddi-layout-derivation--drift-verification) | `scripts/gen_ddi_layout.py`, `d3d11ddilayout.c` | Deriving field offsets, validating layout agreement |
| **SK-03** | [PE Exports & Interface Acquisition Audits](#sk-03-pe-exports--interface-acquisition-audits) | `check_pe_audit.py`, `check_interface_acquisition.py` | Auditing export ordinals, enforcing `strictResult()` funnel |
| **SK-04** | [Core Boundary Unit Testing](#sk-04-core-boundary-unit-testing) | `tests/d3d11on12coretest.c`, `d3d11shimstatus.c` | Testing mock COM vtables, fail-closed returns, pointer zeroing |
| **SK-05** | [CI Gates & Test Suite Execution](#sk-05-ci-gates--test-suite-execution) | `tests/test_ci_gates.py`, `package-d3d11on12-source.sh` | Pre-commit sanity checks, source tarball packaging |
| **SK-06** | [Diagnostic Logging & Sinks](#sk-06-diagnostic-logging--sinks) | `wine_d3d11_diag.h`, `ntdll.spec` | Verifying dynamic symbol resolution and error logging |
| **SK-07** | [Conformance Probing & Status Gating](#sk-07-conformance-probing--status-gating) | `tests/d3d11on12probe.c`, `WineD3D11ShimGetStatus` | Checking rendering pipeline flow, reading deployment state |

---

## SK-01: Clean-Room DDI Authoring & Provenance

### Context
All DDI structures in [`relay12-d3d11/ddi/wine_d3d11ddi.h`](file:///Users/niltonperimneto/Whisky/relay12/relay12-d3d11/ddi/wine_d3d11ddi.h) must be clean-room authored using public Microsoft documentation. Proprietary Windows Driver Kit headers are prohibited.

### Procedure

1. **Dual-Source Retrieval:**
   - Retrieve the rendered documentation page:
     `https://learn.microsoft.com/windows-hardware/drivers/ddi/d3d10umddi/<target_page>`
   - Retrieve the GitHub markdown documentation mirror:
     `https://raw.githubusercontent.com/MicrosoftDocs/windows-driver-docs-ddi/staging/wdk-ddi-src/content/d3d10umddi/<target_page>.md`
2. **Cross-Validation:**
   Confirm that member count, member types, and declaration order agree across both documentation sources.
3. **Format Provenance Comment Block:**
   Add a structured comment block with `Specification:` and `Retrieved:` tags to the header:
   ```c
   /*
    * Group: TargetStructureGroup
    * Specification: https://learn.microsoft.com/windows-hardware/drivers/ddi/d3d10umddi/ns-d3d10umddi-target_structure
    * Retrieved: 2026-09-07
    */
   ```
4. **Natural Alignment:**
   Do not include `#pragma pack`. Structures use natural Win64 8-byte alignment.
5. **Execute Gate:**
   ```bash
   python3 scripts/check_ddi_header.py
   ```

---

## SK-02: DDI Layout Derivation & Drift Verification

### Context
Field offsets must match the binary expectation of the D3D11On12 user-mode driver. Offsets and sizes are enforced at compile time using assertions and validated against an independent layout calculation model.

### Recipes

#### 1. Validate Header Offsets Against Python Layout Model
```bash
python3 scripts/gen_ddi_layout.py --check
```
*Expected Output:*
`ddi layout model: 12 structures and 37 fields agree with the header`

#### 2. Generate C Declarations and Compile-Time Assertions
```bash
python3 scripts/gen_ddi_layout.py --emit <GroupName>
```

#### 3. Run-time Layout Verification in C and C++
Compile and run [`tests/d3d11ddilayout.c`](file:///Users/niltonperimneto/Whisky/relay12/tests/d3d11ddilayout.c) to confirm that dynamically walked structure offsets match compile-time assertions across both C and C++ compilers.

---

## SK-03: PE Exports & Interface Acquisition Audits

### Context
The router (`d3d11shim.dll`) and core boundary (`d3d11on12core.dll`) must present specific export tables and follow safe COM acquisition patterns.

### Recipes

#### 1. Audit PE Export Tables and Runtime Dependencies
```bash
python3 scripts/check_pe_audit.py d3d11shim.dll d3d11on12core.dll
```
*Validation Rules:*
- `d3d11shim.dll` exports ordinals 1 to 4 (`D3D11CreateDevice`, `D3D11CreateDeviceAndSwapChain`, `D3D11On12CreateDevice`, `WineD3D11ShimGetStatus`).
- `d3d11on12core.dll` exports ordinals 1 to 3 (`WineD3D11On12GetABIVersion`, `WineD3D11On12CreateDeviceV1`, `WineD3D11On12GetInterface`).
- Imports are limited to `kernel32.dll` and `msvcrt.dll`. No dependency on `libstdc++` or `libgcc_s`.

#### 2. Audit COM Interface Acquisitions
```bash
python3 scripts/check_interface_acquisition.py relay12-d3d11
```
*Validation Rule:*
Every occurrence of `->QueryInterface(` or `->GetDevice(` must be wrapped in `strictResult()`.

---

## SK-04: Core Boundary Unit Testing

### Context
Unit testing the core validation boundary does not require an active physical GPU.

### Recipes

#### 1. Run Mock Core Unit Tests
[`tests/d3d11on12coretest.c`](file:///Users/niltonperimneto/Whisky/relay12/tests/d3d11on12coretest.c) constructs mock COM vtables with designated initializers, leaving unused slots null to verify that only expected interface methods are invoked.

Run via Wine:
```bash
wine d3d11on12coretest.exe
```

#### 2. Test Fail-Closed Router Behavior
[`tests/d3d11shimstatus.c`](file:///Users/niltonperimneto/Whisky/relay12/tests/d3d11shimstatus.c) loads `d3d11shim.dll` in an environment where `d3d11mt.dll` and `d3d11on12core.dll` are absent:
- Confirms creation functions return `DXGI_ERROR_UNSUPPORTED` (`0x887a0004`).
- Confirms all output pointers are cleared to `NULL`.
- Queries `WineD3D11ShimGetStatus` to confirm machine-readable state reporting.

---

## SK-05: CI Gates & Test Suite Execution

### Context
Static verification scripts are tested by a Python unit test suite in [`tests/test_ci_gates.py`](file:///Users/niltonperimneto/Whisky/relay12/tests/test_ci_gates.py).

### Execution Recipe
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

#### Source Package Generation
To create a clean-room source archive including submodule licenses:
```bash
./scripts/package-d3d11on12-source.sh
```

---

## SK-06: Diagnostic Logging & Sinks

### Context
Diagnostic logging in [`relay12-d3d11/wine_d3d11_diag.h`](file:///Users/niltonperimneto/Whisky/relay12/relay12-d3d11/wine_d3d11_diag.h) avoids static linking against internal Wine symbols.

### Operation
- **Dynamic Symbol Resolution:** Queries `__wine_dbg_output` from `ntdll.dll` via `GetProcAddress`. If unavailable, falls back to `OutputDebugStringA` and then to `stderr`.
- **Deduplication:** State latches ensure that recurring failure conditions log once per process, avoiding redundant messages during application polling loops.

---

## SK-07: Conformance Probing & Status Gating

### Context
When a compatible Direct3D 12 environment is available, end-to-end rendering validation is performed with [`tests/d3d11on12probe.c`](file:///Users/niltonperimneto/Whisky/relay12/tests/d3d11on12probe.c).

### Probe Steps
1. Creates a Direct3D 12 device and direct command queue.
2. Invokes `D3D11On12CreateDevice`.
3. Acquires the `ID3D11On12Device` interface.
4. Wraps a render target resource.
5. Acquires, clears, and releases the resource, flushing work to the command queue.
6. Waits for fence completion.

### Deployment Status Inspection
Callers inspect ordinal 4 (`WineD3D11ShimGetStatus`) to determine whether the D3D11On12 subsystem is ready before selecting a rendering backend.
