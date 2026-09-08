/* SPDX-License-Identifier: GPL-3.0-only */
#pragma once

#include <windows.h>
#include <d3d11.h>
#include <d3d11on12.h>

/* The router and the core are C++, but the validation tests are C so they can
 * build mock COM objects from the widl C vtable declarations.  Both languages
 * must see one set of declarations, or the tests would validate a copy of the
 * ABI instead of the ABI itself. */
#ifdef __cplusplus
# include <cstddef>
# include <type_traits>
# define WINE_D3D11ON12_LINKAGE extern "C"
# define WINE_D3D11ON12_NOEXCEPT noexcept
# define WINE_D3D11ON12_ASSERT(condition) static_assert(condition, #condition)
#else
# include <stddef.h>
# define WINE_D3D11ON12_LINKAGE extern
# define WINE_D3D11ON12_NOEXCEPT
# define WINE_D3D11ON12_ASSERT(condition) _Static_assert(condition, #condition)
#endif

#define WINE_D3D11ON12_ABI_VERSION 1u
#define WINE_D3D11ON12_CAP_VALIDATION 0x0000000000000001ull

typedef UINT (WINAPI *WineD3D11On12GetABIVersionFn)(void);
typedef HRESULT (WINAPI *WineD3D11On12CreateDeviceFn)(IUnknown *, UINT,
        const D3D_FEATURE_LEVEL *, UINT, IUnknown *const *, UINT, UINT,
        ID3D11Device **, ID3D11DeviceContext **, D3D_FEATURE_LEVEL *);

struct WineD3D11On12Interface
{
    UINT size;
    UINT version;
    UINT64 capabilities;
    WineD3D11On12CreateDeviceFn createDevice;
    void *reserved[8];
};

#ifndef __cplusplus
typedef struct WineD3D11On12Interface WineD3D11On12Interface;
#endif

#ifdef __cplusplus
WINE_D3D11ON12_ASSERT(std::is_standard_layout_v<WineD3D11On12Interface>);
#endif
WINE_D3D11ON12_ASSERT(sizeof(void *) != 8 || sizeof(WineD3D11On12Interface) == 88);
WINE_D3D11ON12_ASSERT(offsetof(WineD3D11On12Interface, capabilities) == 8);
WINE_D3D11ON12_ASSERT(offsetof(WineD3D11On12Interface, createDevice) == 16);
WINE_D3D11ON12_ASSERT(offsetof(WineD3D11On12Interface, reserved) == 24);

typedef HRESULT (WINAPI *WineD3D11On12GetInterfaceFn)(UINT, UINT,
        WineD3D11On12Interface *);

WINE_D3D11ON12_LINKAGE UINT WINAPI WineD3D11On12GetABIVersion(void)
        WINE_D3D11ON12_NOEXCEPT;
WINE_D3D11ON12_LINKAGE HRESULT WINAPI WineD3D11On12GetInterface(UINT, UINT,
        WineD3D11On12Interface *) WINE_D3D11ON12_NOEXCEPT;
WINE_D3D11ON12_LINKAGE HRESULT WINAPI WineD3D11On12CreateDeviceV1(IUnknown *,
        UINT, const D3D_FEATURE_LEVEL *, UINT, IUnknown *const *, UINT, UINT,
        ID3D11Device **, ID3D11DeviceContext **, D3D_FEATURE_LEVEL *)
        WINE_D3D11ON12_NOEXCEPT;
