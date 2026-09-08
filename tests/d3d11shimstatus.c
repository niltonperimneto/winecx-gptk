/* SPDX-License-Identifier: GPL-3.0-only
 *
 * Fail-closed tests for the D3D11 router.
 *
 * The router is loaded in a prefix that has neither d3d11mt.dll nor
 * d3d11on12core.dll, which is the deployment failure it has to survive: it is
 * what an application sees if Apple's forwarder was never renamed.  Every
 * entry point must answer with a documented D3D11 return code, and the cause
 * that code cannot carry must be readable from WineD3D11ShimGetStatus.
 *
 * These paths all report, so this also exercises the diagnostic sinks.
 *
 * Build: x86_64-w64-mingw32-gcc -std=gnu11 -O2 -Wall -Wextra -Werror \
 *            -Irelay12-d3d11 -o d3d11shimstatus.exe tests/d3d11shimstatus.c
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>

#include "d3d11shim.h"

typedef HRESULT (WINAPI *CreateDeviceFn)(IDXGIAdapter *, D3D_DRIVER_TYPE,
        HMODULE, UINT, const D3D_FEATURE_LEVEL *, UINT, UINT, ID3D11Device **,
        D3D_FEATURE_LEVEL *, ID3D11DeviceContext **);
typedef HRESULT (WINAPI *CreateDeviceAndSwapChainFn)(IDXGIAdapter *,
        D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL *, UINT, UINT,
        const DXGI_SWAP_CHAIN_DESC *, IDXGISwapChain **, ID3D11Device **,
        D3D_FEATURE_LEVEL *, ID3D11DeviceContext **);

static int failures;

static void fail(const char *test, const char *detail)
{
    printf("[fail] %s: %s\n", test, detail);
    ++failures;
}

static void check_hr(const char *test, HRESULT got, HRESULT expected)
{
    if (got == expected)
    {
        printf("[ ok ] %s\n", test);
        return;
    }
    printf("[fail] %s: got 0x%08lx, expected 0x%08lx\n", test,
            (unsigned long)got, (unsigned long)expected);
    ++failures;
}

/* The router must not touch the objects it was handed when it cannot route,
 * so every method here is a failure. */
static HRESULT STDMETHODCALLTYPE untouched_QueryInterface(IUnknown *iface,
        REFIID riid, void **out)
{
    (void)iface;
    (void)riid;
    if (out)
        *out = NULL;
    fail("On12 routing", "the router queried an object it could not route");
    return E_NOINTERFACE;
}

static ULONG STDMETHODCALLTYPE untouched_AddRef(IUnknown *iface)
{
    (void)iface;
    fail("On12 routing", "the router referenced an object it could not route");
    return 2;
}

static ULONG STDMETHODCALLTYPE untouched_Release(IUnknown *iface)
{
    (void)iface;
    fail("On12 routing", "the router released an object it could not route");
    return 1;
}

/* Not const: the widl C interface declares lpVtbl as a pointer to
 * non-const. */
static IUnknownVtbl untouched_vtbl =
{
    .QueryInterface = untouched_QueryInterface,
    .AddRef = untouched_AddRef,
    .Release = untouched_Release,
};

static void test_status(HMODULE shim)
{
    WineD3D11ShimGetStatusFn get_status;
    WineD3D11ShimStatus status;
    HRESULT hr;

    get_status = (void *)GetProcAddress(shim, "WineD3D11ShimGetStatus");
    if (!get_status)
    {
        fail("status export", "WineD3D11ShimGetStatus is not exported");
        return;
    }

    hr = get_status(WINE_D3D11SHIM_STATUS_VERSION, sizeof(status), NULL);
    check_hr("status rejects a null structure", hr, E_INVALIDARG);

    hr = get_status(WINE_D3D11SHIM_STATUS_VERSION, sizeof(status) - 1, &status);
    check_hr("status rejects a short structure", hr, E_INVALIDARG);

    hr = get_status(WINE_D3D11SHIM_STATUS_VERSION, sizeof(status) + 1, &status);
    check_hr("status rejects an over-long structure", hr, E_INVALIDARG);

    memset(&status, 0xcd, sizeof(status));
    hr = get_status(WINE_D3D11SHIM_STATUS_VERSION + 1, sizeof(status), &status);
    check_hr("status rejects an unknown version", hr, E_NOINTERFACE);
    if (status.size != sizeof(status)
            || status.version != WINE_D3D11SHIM_STATUS_VERSION)
        fail("status rejects an unknown version",
                "a rejected structure must still report its size and version");
    if (status.flags || status.creationResult || status.on12Result)
        fail("status rejects an unknown version",
                "a rejected structure must not report state");

    memset(&status, 0xcd, sizeof(status));
    hr = get_status(WINE_D3D11SHIM_STATUS_VERSION, sizeof(status), &status);
    check_hr("status reports the current version", hr, S_OK);
    if (status.size != sizeof(status)
            || status.version != WINE_D3D11SHIM_STATUS_VERSION)
        fail("status reports the current version", "size or version is wrong");
    if (status.flags)
        fail("status reports the current version",
                "no module is deployed beside the router, so no flag is set");
    check_hr("status reports the creation result", status.creationResult,
            DXGI_ERROR_UNSUPPORTED);
    check_hr("status reports the On12 result", status.on12Result,
            DXGI_ERROR_UNSUPPORTED);
    if (!status.forwarderLoadError)
        fail("status reports the forwarder load error",
                "the failed LoadLibraryW error was not recorded");
    if (status.coreAbiVersion || status.coreCapabilities)
        fail("status reports the current version",
                "no core was accepted, so it must publish no core ABI");
}

static void test_creation_paths(HMODULE shim)
{
    CreateDeviceFn create_device;
    CreateDeviceAndSwapChainFn create_swapchain;
    ID3D11Device *device = NULL;
    ID3D11DeviceContext *context = NULL;
    D3D_FEATURE_LEVEL level = (D3D_FEATURE_LEVEL)0;
    HRESULT hr;

    create_device = (void *)GetProcAddress(shim, "D3D11CreateDevice");
    create_swapchain = (void *)GetProcAddress(shim,
            "D3D11CreateDeviceAndSwapChain");
    if (!create_device || !create_swapchain)
    {
        fail("creation exports", "an ordinary D3D11 creation export is missing");
        return;
    }

    /* DXGI_ERROR_UNSUPPORTED, not HRESULT_FROM_WIN32(ERROR_PROC_NOT_FOUND):
     * an application orchestrating an API downgrade switches on the documented
     * D3D11 codes, and 0x8007007f is not one of them. */
    hr = create_device(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL, 0, NULL, 0,
            D3D11_SDK_VERSION, &device, &level, &context);
    check_hr("D3D11CreateDevice without the forwarder", hr,
            DXGI_ERROR_UNSUPPORTED);

    hr = create_swapchain(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL, 0, NULL, 0,
            D3D11_SDK_VERSION, NULL, NULL, &device, &level, &context);
    check_hr("D3D11CreateDeviceAndSwapChain without the forwarder", hr,
            DXGI_ERROR_UNSUPPORTED);
}

static void test_on12_path(HMODULE shim)
{
    WineD3D11On12CreateDeviceFn create_on12;
    IUnknown untouched;
    IUnknown *queues[1];
    ID3D11Device *device = (ID3D11Device *)(ULONG_PTR)0xdeadbeefdeadbeefull;
    ID3D11DeviceContext *context =
            (ID3D11DeviceContext *)(ULONG_PTR)0xfeedfacefeedfaceull;
    D3D_FEATURE_LEVEL level = (D3D_FEATURE_LEVEL)0x9999;
    HRESULT hr;

    create_on12 = (void *)GetProcAddress(shim, "D3D11On12CreateDevice");
    if (!create_on12)
    {
        fail("On12 export", "D3D11On12CreateDevice is not exported");
        return;
    }
    untouched.lpVtbl = &untouched_vtbl;

    hr = create_on12(NULL, 0, NULL, 0, NULL, 0, 0, &device, &context, &level);
    check_hr("D3D11On12CreateDevice rejects a null device", hr, E_INVALIDARG);
    if (device || context || level)
        fail("D3D11On12CreateDevice rejects a null device",
                "an output parameter survived the call uninitialized");

    device = (ID3D11Device *)(ULONG_PTR)0xdeadbeefdeadbeefull;
    context = (ID3D11DeviceContext *)(ULONG_PTR)0xfeedfacefeedfaceull;
    level = (D3D_FEATURE_LEVEL)0x9999;
    queues[0] = &untouched;
    hr = create_on12(&untouched, 0, NULL, 0, queues, 1, 0, &device, &context,
            &level);
    check_hr("D3D11On12CreateDevice without a core", hr,
            DXGI_ERROR_UNSUPPORTED);
    if (device || context || level)
        fail("D3D11On12CreateDevice without a core",
                "an output parameter survived the call uninitialized");
}

int main(void)
{
    /* By name, from the application directory: this must be the router built
     * in this job and not whatever d3d11.dll the prefix has. */
    HMODULE shim = LoadLibraryW(L"d3d11shim.dll");

    if (!shim)
    {
        printf("[fail] router: LoadLibraryW(d3d11shim.dll) failed with %lu\n",
                GetLastError());
        return 1;
    }

    test_status(shim);
    test_creation_paths(shim);
    test_on12_path(shim);

    if (failures)
    {
        printf("RESULT: %d D3D11 router failure(s)\n", failures);
        return 1;
    }
    printf("RESULT: the D3D11 router fails closed with documented codes\n");
    return 0;
}
