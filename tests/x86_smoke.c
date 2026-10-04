/* x86 smoke test for the arm64 lane: built as x86_64 (runs under ARM64EC)
 * and i686 (runs under WoW64), it reports how Windows sees the process and
 * checks arithmetic, SSE2 and an exception round trip against exact values.
 * Exits 0 only if every check matches.
 *
 *   x86_64-w64-mingw32-clang -O2 -o x86_64-smoke.exe tests/x86_smoke.c
 *   i686-w64-mingw32-clang -O2 -msse2 -o i686-smoke.exe tests/x86_smoke.c
 */
#include <windows.h>
#include <emmintrin.h>
#include <stdint.h>
#include <stdio.h>

typedef BOOL (WINAPI *is_wow64_process2_t)(HANDLE, USHORT *, USHORT *);

static int failures;

static void check(const char *what, uint64_t got, uint64_t want)
{
    printf("%-26s %016llx %s\n", what, (unsigned long long)got, got == want ? "ok" : "FAIL");
    if (got != want) failures++;
}

static uint64_t fnv1a(unsigned rounds)
{
    uint64_t hash = 0xcbf29ce484222325ull;
    for (unsigned i = 0; i < rounds; i++) hash = (hash ^ (i & 0xff)) * 0x100000001b3ull;
    return hash;
}

#define SMOKE_EXCEPTION 0xe0534d4bu

static volatile LONG handled;

static LONG WINAPI handler(EXCEPTION_POINTERS *info)
{
    if (info->ExceptionRecord->ExceptionCode != SMOKE_EXCEPTION) return EXCEPTION_CONTINUE_SEARCH;
    handled = (LONG)info->ExceptionRecord->ExceptionInformation[0];
    return EXCEPTION_CONTINUE_EXECUTION;
}

int main(void)
{
#ifdef _WIN64
    printf("built for x86_64\n");
#else
    printf("built for i686\n");
#endif
    USHORT process = 0, native = 0;
    is_wow64_process2_t is_wow64_process2 =
        (is_wow64_process2_t)GetProcAddress(GetModuleHandleA("kernel32.dll"), "IsWow64Process2");
    if (is_wow64_process2 && is_wow64_process2(GetCurrentProcess(), &process, &native))
        printf("IsWow64Process2: process %#06x native %#06x\n", process, native);
    SYSTEM_INFO info;
    GetNativeSystemInfo(&info);
    printf("native processor architecture %u, %lu CPUs\n", info.wProcessorArchitecture, info.dwNumberOfProcessors);

    check("fnv1a 1M rounds", fnv1a(1000000), 0x952176a3496f44e5ull);
    __m128i a = _mm_set_epi32(1, 2, 3, 4), b = _mm_set_epi32(10, 20, 30, 40);
    __m128i sum = _mm_add_epi32(a, b);
    uint32_t lanes[4];
    _mm_storeu_si128((__m128i *)lanes, sum);
    check("sse2 paddd", ((uint64_t)lanes[3] << 48) | ((uint64_t)lanes[2] << 32) | (lanes[1] << 16) | lanes[0],
          (11ull << 48) | (22ull << 32) | (33u << 16) | 44u);
    volatile double x = 2.0;
    union { double d; uint64_t u; } root = { .d = __builtin_sqrt(x) };
    check("sqrt(2) bits", root.u, 0x3ff6a09e667f3bcdull);
    PVOID vectored = AddVectoredExceptionHandler(1, handler);
    ULONG_PTR argument = 42;
    RaiseException(SMOKE_EXCEPTION, 0, 1, &argument);
    RemoveVectoredExceptionHandler(vectored);
    check("exception round trip", (uint64_t)handled, 42);

    printf("%s\n", failures ? "FAILED" : "x86 smoke passed");
    return failures != 0;
}
