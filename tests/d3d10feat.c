#define COBJMACROS
#include <windows.h>
#include <d3d10.h>
#include <stdio.h>

int main(void)
{
    ID3D10Device *device = NULL;
    HRESULT hr = D3D10CreateDevice(NULL, D3D10_DRIVER_TYPE_HARDWARE, NULL, 0,
                                  D3D10_SDK_VERSION, &device);
    if (FAILED(hr)) {
        fprintf(stderr, "D3D10CreateDevice failed: %#lx\n", (unsigned long)hr);
        return 1;
    }
    ID3D10Device_Release(device);
    puts("D3D10 device creation passed");
    return 0;
}
