/* SPDX-License-Identifier: GPL-3.0-only
 *
 * Router status ABI.
 *
 * Every failure the router reports to an application has to be a documented
 * D3D11 return code, and DXGI_ERROR_UNSUPPORTED is the only documented answer
 * for "this cannot create a device here".  That code therefore cannot
 * distinguish a bottle with no D3D11On12 support from a deployment where
 * Apple's forwarder was not renamed to d3d11mt.dll.  This structure carries
 * the cause instead.
 *
 * It is what deployment must gate supportsD3D11On12 on.  Debug output is for a
 * person reading a log; a capability flag must never be derived from scraped
 * text.
 */
#ifndef WINE_D3D11SHIM_H
#define WINE_D3D11SHIM_H

/* The router's two ABIs are C declarations shared with a C++ implementation
 * and C tests, and this reuses that header's spelling of the linkage,
 * noexcept, and static-assert macros rather than defining a second set. */
#include "d3d11on12core.h"

#define WINE_D3D11SHIM_STATUS_VERSION 1u

/* d3d11mt.dll loaded, so Apple's forwarder is present under its deployed
 * name. */
#define WINE_D3D11SHIM_FORWARDER_LOADED 0x00000001u
/* Both ordinary D3D11 creation exports resolved in it. */
#define WINE_D3D11SHIM_FORWARDER_COMPLETE 0x00000002u
/* d3d11on12core.dll loaded. */
#define WINE_D3D11SHIM_CORE_LOADED 0x00000004u
/* It published a WineD3D11On12Interface this router can call. */
#define WINE_D3D11SHIM_CORE_COMPATIBLE 0x00000008u

struct WineD3D11ShimStatus
{
    UINT size;
    UINT version;
    UINT flags;
    /* The ABI version and capabilities the core published, or zero when no
     * compatible core was accepted. */
    UINT coreAbiVersion;
    UINT64 coreCapabilities;
    /* What D3D11CreateDevice and D3D11CreateDeviceAndSwapChain will return
     * without reaching Apple's forwarder, S_OK when they route to it. */
    HRESULT creationResult;
    /* What D3D11On12CreateDevice will return without reaching the core, S_OK
     * when it routes to it. */
    HRESULT on12Result;
    /* GetLastError from the failed LoadLibraryW(d3d11mt.dll), or zero. */
    DWORD forwarderLoadError;
    /* Explicit, so the layout below has no implicit padding to reason about. */
    UINT padding;
    UINT64 reserved[4];
};

#ifndef __cplusplus
typedef struct WineD3D11ShimStatus WineD3D11ShimStatus;
#endif

#ifdef __cplusplus
WINE_D3D11ON12_ASSERT(std::is_standard_layout_v<WineD3D11ShimStatus>);
#endif
WINE_D3D11ON12_ASSERT(sizeof(void *) != 8 || sizeof(WineD3D11ShimStatus) == 72);
WINE_D3D11ON12_ASSERT(offsetof(WineD3D11ShimStatus, size) == 0);
WINE_D3D11ON12_ASSERT(offsetof(WineD3D11ShimStatus, version) == 4);
WINE_D3D11ON12_ASSERT(offsetof(WineD3D11ShimStatus, flags) == 8);
WINE_D3D11ON12_ASSERT(offsetof(WineD3D11ShimStatus, coreAbiVersion) == 12);
WINE_D3D11ON12_ASSERT(offsetof(WineD3D11ShimStatus, coreCapabilities) == 16);
WINE_D3D11ON12_ASSERT(offsetof(WineD3D11ShimStatus, creationResult) == 24);
WINE_D3D11ON12_ASSERT(offsetof(WineD3D11ShimStatus, on12Result) == 28);
WINE_D3D11ON12_ASSERT(offsetof(WineD3D11ShimStatus, forwarderLoadError) == 32);
WINE_D3D11ON12_ASSERT(offsetof(WineD3D11ShimStatus, reserved) == 40);

typedef HRESULT (WINAPI *WineD3D11ShimGetStatusFn)(UINT, UINT,
        WineD3D11ShimStatus *);

WINE_D3D11ON12_LINKAGE HRESULT WINAPI WineD3D11ShimGetStatus(UINT, UINT,
        WineD3D11ShimStatus *) WINE_D3D11ON12_NOEXCEPT;

#endif /* WINE_D3D11SHIM_H */
