/* Stand-ins for Apple's unsupported D3D11On12 entry points: the legacy
 * immediate refusal and GPTK 4.0b3's DXGI initialization followed by refusal.
 * Assembly preserves the instruction sequences the interposer recognizes.
 * MockMakeStubForeign changes legacy padding or the new HRESULT to check
 * that near matches retain their original behavior. */
#include <windows.h>

#ifdef INITIALIZED_STUB
HRESULT WINAPI MockFactory(UINT flags, const void *iid, void **factory)
{
    (void)flags;
    (void)iid;
    (void)factory;
    return E_INVALIDARG;
}

/* The 4.0b3 instruction sequence, with real relocations so an unpatched
 * call still executes safely and returns Apple's refusal. */
__asm__(
    ".text\n"
    ".p2align 4, 0xcc\n"
    ".globl D3D11On12CreateDevice\n"
    "D3D11On12CreateDevice:\n"
    "    subq $0x28, %rsp\n"
    "    movq mock_factory(%rip), %rax\n"
    "    testq %rax, %rax\n"
    "    jne 1f\n"
    "    leaq mock_dxgi(%rip), %rcx\n"
    "    call *__imp_GetModuleHandleA(%rip)\n"
    "    leaq mock_factory_name(%rip), %rdx\n"
    "    movq %rax, %rcx\n"
    "    call *__imp_GetProcAddress(%rip)\n"
    "    movq %rax, mock_factory(%rip)\n"
    "    testq %rax, %rax\n"
    "    je 2f\n"
    "1:  leaq mock_iid(%rip), %rdx\n"
    "    xorl %ecx, %ecx\n"
    "    xorl %r8d, %r8d\n"
    "    call *%rax\n"
    "2:  movl $0x887a0004, %eax\n"
    "    addq $0x28, %rsp\n"
    "    ret\n"
    "    .fill 15, 1, 0xcc\n"
    ".data\n"
    "mock_factory: .quad MockFactory\n"
    ".section .rdata,\"dr\"\n"
    "mock_dxgi: .asciz \"dxgi.dll\"\n"
    "mock_factory_name: .asciz \"CreateDXGIFactory2\"\n"
    "mock_iid: .zero 16\n"
    ".text\n");
#else
__asm__(
    ".text\n"
    ".p2align 4, 0xcc\n"
    ".globl D3D11On12CreateDevice\n"
    "D3D11On12CreateDevice:\n"
    "    movl $0x887a0004, %eax\n"
    "    ret\n"
    "    .fill 10, 1, 0xcc\n");
#endif

extern BYTE D3D11On12CreateDevice[];

BYTE *WINAPI MockStubAddress(void)
{
    return D3D11On12CreateDevice;
}

BOOL WINAPI MockMakeStubForeign(void)
{
    DWORD protect;

    if (!VirtualProtect(D3D11On12CreateDevice, 81, PAGE_EXECUTE_READWRITE, &protect))
        return FALSE;
#ifdef INITIALIZED_STUB
    D3D11On12CreateDevice[72] = 0x05;
#else
    D3D11On12CreateDevice[6] = 0x90;
#endif
    VirtualProtect(D3D11On12CreateDevice, 81, protect, &protect);
    FlushInstructionCache(GetCurrentProcess(), D3D11On12CreateDevice, 81);
    return TRUE;
}
