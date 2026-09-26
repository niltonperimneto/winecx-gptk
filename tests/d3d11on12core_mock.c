/* A stand-in for Relay12's d3d11on12core.dll: the entry point the d3d12
 * interposer routes D3D11On12CreateDevice to. It answers with a device and
 * context no real call could produce, so the test knows the call arrived here
 * and that all ten arguments survived the jump. */
#include <windows.h>

#define MOCK_DEVICE ((void *)(UINT_PTR)0xd3d11012)
#define MOCK_CONTEXT ((void *)(UINT_PTR)0xc0de0012)

HRESULT WINAPI WineD3D11On12CreateDeviceV1(IUnknown *device12, UINT flags, const void *levels,
        UINT level_count, IUnknown *const *queues, UINT queue_count, UINT node_mask,
        void **device11, void **context11, UINT *chosen_level)
{
    /* the arguments the test passes, one per register and stack slot */
    if (device12 != (IUnknown *)(UINT_PTR)0x1212 || flags != 0x7 || levels != (void *)(UINT_PTR)0x4c4c
            || level_count != 3 || queues != (IUnknown *const *)(UINT_PTR)0x5151 || queue_count != 1
            || node_mask != 0x10)
        return E_INVALIDARG;
    *device11 = MOCK_DEVICE;
    *context11 = MOCK_CONTEXT;
    *chosen_level = 0xb100;
    return S_OK;
}
