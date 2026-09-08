/* D3DMetal D3D11-on-12 conformance probe.
 *
 * Build: x86_64-w64-mingw32-gcc -O2 -Wall -Werror -o d3d11on12probe.exe \
 *            d3d11on12probe.c -ld3d11 -ld3d12 -ldxgi -ldxguid -luuid
 */
#define COBJMACROS
#include <windows.h>
#include <initguid.h>
#include <d3d11.h>
#include <d3d11on12.h>
#include <d3d12.h>
#include <dxgi1_4.h>
#include <stdio.h>

static void report_hresult(const char *operation, HRESULT hr)
{
    printf("[%s] %s: 0x%08lx\n", SUCCEEDED(hr) ? " ok " : "fail",
            operation, (unsigned long)hr);
}

int main(void)
{
    ID3D12Device *device12 = NULL;
    ID3D12CommandQueue *queue = NULL;
    ID3D12Resource *resource12 = NULL;
    ID3D12Fence *fence = NULL;
    ID3D11Device *device11 = NULL;
    ID3D11DeviceContext *context11 = NULL;
    ID3D11On12Device *device11on12 = NULL;
    ID3D11Resource *resource11 = NULL;
    ID3D11RenderTargetView *rtv = NULL;
    HANDLE event = NULL;
    D3D12_COMMAND_QUEUE_DESC queue_desc = {0};
    D3D12_HEAP_PROPERTIES heap_properties = {0};
    D3D12_RESOURCE_DESC resource_desc = {0};
    D3D11_RESOURCE_FLAGS flags11 = {0};
    D3D_FEATURE_LEVEL feature_level = 0;
    IUnknown *queues[1];
    FLOAT clear_color[4] = {0.125f, 0.25f, 0.5f, 1.0f};
    HRESULT hr;
    int result = 1;

    hr = D3D12CreateDevice(NULL, D3D_FEATURE_LEVEL_11_0,
            &IID_ID3D12Device, (void **)&device12);
    report_hresult("D3D12CreateDevice", hr);
    if (FAILED(hr))
        goto done;

    queue_desc.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
    hr = ID3D12Device_CreateCommandQueue(device12, &queue_desc,
            &IID_ID3D12CommandQueue, (void **)&queue);
    report_hresult("CreateCommandQueue", hr);
    if (FAILED(hr))
        goto done;

    queues[0] = (IUnknown *)queue;
    hr = D3D11On12CreateDevice((IUnknown *)device12,
            D3D11_CREATE_DEVICE_BGRA_SUPPORT, NULL, 0, queues, 1, 0,
            &device11, &context11, &feature_level);
    report_hresult("D3D11On12CreateDevice", hr);
    if (FAILED(hr))
        goto done;
    printf("[info] selected feature level: 0x%04x\n", feature_level);

    hr = ID3D11Device_QueryInterface(device11, &IID_ID3D11On12Device,
            (void **)&device11on12);
    report_hresult("QueryInterface(ID3D11On12Device)", hr);
    if (FAILED(hr))
        goto done;

    heap_properties.Type = D3D12_HEAP_TYPE_DEFAULT;
    heap_properties.CreationNodeMask = 1;
    heap_properties.VisibleNodeMask = 1;
    resource_desc.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
    resource_desc.Width = 64;
    resource_desc.Height = 64;
    resource_desc.DepthOrArraySize = 1;
    resource_desc.MipLevels = 1;
    resource_desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
    resource_desc.SampleDesc.Count = 1;
    resource_desc.Layout = D3D12_TEXTURE_LAYOUT_UNKNOWN;
    resource_desc.Flags = D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET;
    hr = ID3D12Device_CreateCommittedResource(device12, &heap_properties,
            D3D12_HEAP_FLAG_NONE, &resource_desc, D3D12_RESOURCE_STATE_RENDER_TARGET,
            NULL, &IID_ID3D12Resource, (void **)&resource12);
    report_hresult("CreateCommittedResource", hr);
    if (FAILED(hr))
        goto done;

    flags11.BindFlags = D3D11_BIND_RENDER_TARGET;
    hr = ID3D11On12Device_CreateWrappedResource(device11on12,
            (IUnknown *)resource12, &flags11, D3D12_RESOURCE_STATE_RENDER_TARGET,
            D3D12_RESOURCE_STATE_COMMON, &IID_ID3D11Resource, (void **)&resource11);
    report_hresult("CreateWrappedResource", hr);
    if (FAILED(hr))
        goto done;

    hr = ID3D11Device_CreateRenderTargetView(device11, resource11, NULL, &rtv);
    report_hresult("CreateRenderTargetView", hr);
    if (FAILED(hr))
        goto done;

    ID3D11On12Device_AcquireWrappedResources(device11on12, &resource11, 1);
    ID3D11DeviceContext_ClearRenderTargetView(context11, rtv, clear_color);
    ID3D11On12Device_ReleaseWrappedResources(device11on12, &resource11, 1);
    ID3D11DeviceContext_Flush(context11);
    printf("[ ok ] acquire, clear, release, and flush completed\n");

    hr = ID3D12Device_CreateFence(device12, 0, D3D12_FENCE_FLAG_NONE,
            &IID_ID3D12Fence, (void **)&fence);
    report_hresult("CreateFence", hr);
    if (FAILED(hr))
        goto done;
    hr = ID3D12CommandQueue_Signal(queue, fence, 1);
    report_hresult("Signal", hr);
    if (FAILED(hr))
        goto done;
    if (ID3D12Fence_GetCompletedValue(fence) < 1)
    {
        event = CreateEventW(NULL, FALSE, FALSE, NULL);
        if (!event)
        {
            printf("[fail] CreateEventW: %lu\n", GetLastError());
            goto done;
        }
        hr = ID3D12Fence_SetEventOnCompletion(fence, 1, event);
        report_hresult("SetEventOnCompletion", hr);
        if (FAILED(hr) || WaitForSingleObject(event, 30000) != WAIT_OBJECT_0)
        {
            printf("[fail] queue fence did not complete\n");
            goto done;
        }
    }

    printf("RESULT: D3D11-on-12 wrapped-resource path verified\n");
    result = 0;

done:
    if (event) CloseHandle(event);
    if (fence) ID3D12Fence_Release(fence);
    if (rtv) ID3D11RenderTargetView_Release(rtv);
    if (resource11) ID3D11Resource_Release(resource11);
    if (device11on12) ID3D11On12Device_Release(device11on12);
    if (context11) ID3D11DeviceContext_Release(context11);
    if (device11) ID3D11Device_Release(device11);
    if (resource12) ID3D12Resource_Release(resource12);
    if (queue) ID3D12CommandQueue_Release(queue);
    if (device12) ID3D12Device_Release(device12);
    return result;
}
