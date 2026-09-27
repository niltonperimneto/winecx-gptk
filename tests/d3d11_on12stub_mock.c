/* A stand-in for Apple's d3d11.dll as far as the d3d12 interposer's Relay12
 * route cares: D3D11On12CreateDevice is Apple's exact 16-byte stub,
 *     mov eax, 0x887a0004 ; ret ; int3 x10
 * written in assembly so the bytes are what the interposer compares against.
 *
 * MockMakeStubForeign alters one padding byte, which is how a D3DMetal that
 * implements D3D11On12 itself looks to the interposer: not the stub, so left
 * alone. The function still returns the same code, since ret comes first. */
#include <windows.h>

__asm__(
    ".text\n"
    ".p2align 4, 0xcc\n"
    ".globl D3D11On12CreateDevice\n"
    "D3D11On12CreateDevice:\n"
    "    movl $0x887a0004, %eax\n"
    "    ret\n"
    "    .fill 10, 1, 0xcc\n");

extern BYTE D3D11On12CreateDevice[];

BYTE *WINAPI MockStubAddress(void)
{
    return D3D11On12CreateDevice;
}

BOOL WINAPI MockMakeStubForeign(void)
{
    DWORD protect;

    if (!VirtualProtect(D3D11On12CreateDevice, 16, PAGE_EXECUTE_READWRITE, &protect))
        return FALSE;
    D3D11On12CreateDevice[6] = 0x90;
    VirtualProtect(D3D11On12CreateDevice, 16, protect, &protect);
    FlushInstructionCache(GetCurrentProcess(), D3D11On12CreateDevice, 16);
    return TRUE;
}
