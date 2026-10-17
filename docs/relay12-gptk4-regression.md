# Relay12 routing with GPTK 4.0b3 and D3D12 shim hot-path bypass

Investigation date: 2026-10-17.

## Failure and fixes

1. **GPTK 4.0b3 `D3D11On12CreateDevice` stub recognition (`gptk-video/d3d12shim.c`):**
   Whisky Preview 2026.8.46, runtime 4.8.22 (WineCX
   `feda99e3831bc4cdf37a8d57a01d319b7acd5920`, Relay12
   `c3a3147f1db48f8d8f2c39b456a6a7f735b2c8e4`) enabled Relay12, but PEAK's
   Unity 6000.3.15f1 renderer reported:

   ```text
   d3d12: failed to create D3D11On12 device (0x887a0004).
   Version: Direct3D 11.0 [level 11.1]
   ```

   GPTK 4.0b3 adds DXGI initialization before the unconditional
   `DXGI_ERROR_UNSUPPORTED` return. The previous matcher recognized only the
   16-byte immediate-return stub. The fix recognizes the complete 81-byte
   instruction sequence, ignoring only its seven RIP-relative address
   displacements, while preserving the legacy 16-byte match and process
   opt-in/scoping rules.

2. **Direct D3DMetal hot-path vtable slots when no video is active (`gptk-video/d3d12shim.c`):**
   Previously, wrapping a D3D12 device unconditionally routed every
   `ID3D12GraphicsCommandList::ResourceBarrier`, `CopyTextureRegion`,
   `ID3D12CommandQueue::ExecuteCommandLists`, `CreateShaderResourceView`,
   `CreatePlacedResource` and `GetCopyableFootprints` call through the shim even
   in games that never use D3D12 video decode/process or `NV12`/`AYUV` resources.
   `sync_hot_vtables()` now keeps those vtable slots pointing directly at
   D3DMetal's own entry points until video is activated, hot-switching existing
   wrapped objects on demand and restoring `CopyTextureRegion`,
   `CreateShaderResourceView` and `ExecuteCommandLists` to D3DMetal once the
   last `NV12` texture or video command list is released.

## Local evidence

Host: macOS 27.2, Apple A18 Pro (8 GiB), x86_64 Wine through Rosetta.

- Both stub variants (`legacy` and `initialized`) exercise activation, opt-out,
  foreign implementation, allowlist inclusion/exclusion, explicit skip and
  launcher exclusion (`14/14` pass).
- The recording `tests/d3d12shim.c` suite (`23/23` checks pass) verifies that
  with no video active, hot-path device and command list slots point directly at
  D3DMetal, bind when `NV12` format support or textures are used, and revert to
  D3DMetal when the last `NV12` texture is destroyed.
- Builtin-stamped `d3d12shim.dll` SHA-256:
  `be1b170056ea464a31a1be7a42f874d6032913744a40dfdd02e0f590fe12a23c`.
- Controlled 6-trial counterbalanced PEAK benchmarks (`1920x1080` windowed,
  authenticated headless Steam reaching the rendered 3D main menu,
  `MTL_HUD_LOG_ENABLED=1`) combining the `d3d12shim.dll` hot-vtable bypass and
  Relay12 lazy DTL initialization (`relay12` commit `261fdec`):
  - `d3d11on12.dll` (DTL) remains unloaded throughout PEAK's DX12 session
    (`loaded_d3d11on12_dtl: false`), reducing GPU memory in DX12 mode from
    `941.25 MB` to `850.33–850.36 MB` (`-90.9 MB`, matching the no-op stub's
    `850.34–850.39 MB`) and process memory from `2347.6–2354.5 MB` to
    `2238.6–2321.4 MB`.
  - Steady-state first-6s 3D main menu median FPS in `dx12_relay12` improved from
    `40.48–40.84 FPS` (baseline) to `42.00–43.34 FPS`, and 1-second minimum FPS
    in the 3D menu improved from `26.55 FPS` to `30.03–30.45 FPS`.
