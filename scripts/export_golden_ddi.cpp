// DDI Golden Layout Exporter (Run on Windows with MSVC and WDK)
// Compile: cl /EHsc /I<WDK_Include_Path> export_golden_ddi.cpp
// Note: Requires WDK headers for D3D10/D3D11 UM DDI

#include <windows.h>
#include <stdio.h>
#include <stddef.h>

// To compile this natively on Windows, these WDK headers are required:
// #include <d3dumddi.h>
// #include <d3d10umddi.h>
// #include <d3d12umddi.h>

// For the sake of the template, we redefine macro helpers.
#define DUMP_SIZE(type) \
    printf("    \"%s\": { \"sizeof\": %zu, \"alignof\": %zu },\n", #type, sizeof(type), __alignof(type))

#define DUMP_OFFSET(type, field) \
    printf("    \"%s.%s\": %zu,\n", #type, #field, offsetof(type, field))

int main() {
    printf("{\n");
    printf("  \"structs\": {\n");
    
    // Uncomment and compile on Windows WDK environment
    /*
    DUMP_SIZE(D3D10DDI_HADAPTER);
    DUMP_SIZE(D3D10DDI_HRTADAPTER);
    DUMP_SIZE(D3D10DDI_HRESOURCE);
    DUMP_SIZE(D3D10DDIARG_CREATEDEVICE);
    DUMP_SIZE(D3DDDI_DEVICECALLBACKS);
    DUMP_SIZE(D3DWDDM2_6DDI_DEVICEFUNCS);
    DUMP_SIZE(DXGI_DDI_BASE_ARGS);
    DUMP_SIZE(D3DDDICB_ESCAPE);
    DUMP_SIZE(D3DDDICB_SYNCTOKEN);

    // Offsets
    DUMP_OFFSET(D3D10DDIARG_CREATEDEVICE, hDrvDevice);
    DUMP_OFFSET(D3D10DDIARG_CREATEDEVICE, hUserInterface);
    DUMP_OFFSET(D3D10DDIARG_CREATEDEVICE, pUMCallbacks);
    DUMP_OFFSET(D3D10DDIARG_CREATEDEVICE, DXGIBaseDDI);
    */

    printf("    \"_end\": {}\n");
    printf("  }\n");
    printf("}\n");

    return 0;
}
