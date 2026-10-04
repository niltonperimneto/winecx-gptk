# DDI Concurrency & Memory Barrier Testing Strategy

## Overview
This document outlines the testing plan to harden the clean-room D3D11 DDI layer (`relay12-d3d11`) against race conditions, thread safety violations, and missing CPU/GPU memory barriers. 

Because `relay12` bridges the gap between Windows WDDM behavior, Wine's translation layers, and Apple Silicon's execution environment (via GPTK), synchronization bugs here will manifest as intermittent silent memory corruption, tearing, or deadlocks that are nearly impossible to trace in production. This plan specifies what must be tested and how those tests should be integrated.

## 1. Synchronization Object Conformance (Wait/Signal)
The core WDDM graphics dispatch model heavily relies on synchronization callbacks (e.g., `pfnWaitForSynchronizationObjectCb`, `pfnSignalSynchronizationObjectCb`).
**Tests must account for:**
- **Deadlock Avoidance:** Tests should mock the core layer callbacks and intentionally introduce blocking logic to ensure the translation layer handles wait/signal operations asynchronously where appropriate without locking up the entire D3D device lock.
- **Hardware vs. CPU Queues:** WDDM 2.6+ introduces granular sync objects (`pfnSubmitWaitForSyncObjectsToHwQueueCb`). Tests must distinguish between CPU waits and GPU hardware-queue waits. 
- **Deferred vs. Immediate Execution:** Ensure that submitting sync tokens on deferred contexts does not prematurely trigger signal calls on the immediate context.

## 2. Memory Barrier & Visibility Testing
Apple Silicon has deeply different memory barrier physics (ARM memory model vs. x86_64 TSO) and integrates differently with unified memory than a traditional discrete GPU.
**Tests must account for:**
- **Flush Conformance:** Write tests that simulate CPU modification of constant buffers or staging resources. An execution thread must wait on the corresponding DDI synchronization object; if the read happens before the "simulated GPU" completes, the test must catch the tearing.
- **Enhanced Barriers Guard:** Verify that applications using enhanced barriers (`D3D12_FEATURE_OPTIONS12.EnhancedBarriersSupported`) do not bypass older sync mechanisms inside the translation layer.
- **Cache Eviction and Fencing:** Emulate `pfnAcquireResourceCb` and `pfnReleaseResourceCb` (and cross-adapter sync if applicable) to ensure GPU caches are being asked to flush exactly when the DDI contract specifies. 

## 3. Deferred Contexts & Multi-threaded Command Lists
D3D11 allows applications to build command lists concurrently across multiple threads before submitting them.
**Tests must account for:**
- **Global State Pollution:** Tests should spawn multiple worker threads (using Win32 `CreateThread` or `pthreads`) that invoke the DDI simultaneously to generate command lists. They must ensure that internal states inside `d3d11shim.dll` are not clobbered (using thread-local storage/state isolation heavily and appropriately).
- **Interleaved Submission Traps:** Intentionally submit incomplete or fragmented command lists from concurrent threads to verify that the layer rejects them or sequences them flawlessly without crashing due to a torn linked list of commands.

## 4. Automation & Tooling (TSAN Integration)
Catching race conditions requires more than just functional tests—it requires dynamic instrumentation.
**The CI strategy must account for:**
- **ThreadSanitizer (TSAN) Builds:** Introduce a `-fsanitize=thread` test configuration for the CI runner.
- **Mock Callback Thread Injection:** Create a test suite (`tests/ddi_thread_stress.c`) that spins up 8–16 physical threads constantly hammering the `D3DWDDM2_6DDI_DEVICEFUNCS` router functions.
- **Atomic Verifications:** Validate that any shared reference counters (like `refcount` in `mock_device`) within the shim strictly use compiler intrinsics (e.g., `InterlockedIncrement` or `__atomic_fetch_add`) and never do unprotected `++` arithmetic.

## Implementation Phases
**Phase A: TSAN CI Setup.** Modify `relay12/.github/workflows/pull-request.yml` to compile a parallel `-fsanitize=thread` pass of the validation checks.
**Phase B: Multi-threaded Mock Injection.** Write `tests/ddi_thread_stress.c` to deliberately invoke device functions concurrently, measuring TSAN violations.
**Phase C: Sync Token Logic Guards.** Write specific unit tests targeting the behavior and parameter validation of `pfnSubmitSignalSyncObjectsToHwQueueCb`.
