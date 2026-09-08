/* SPDX-License-Identifier: GPL-3.0-only
 *
 * Layered diagnostics for the router and the core.
 *
 * OutputDebugStringA alone is not sufficient.  Under Wine it is delivered as
 * a DBG_PRINTEXCEPTION_C raise, so an application with a debugger attached or
 * a handler for that exception code consumes the string before Wine's own
 * output sees it, and a deployment error disappears exactly when someone is
 * trying to diagnose it.  Replacing it is not sufficient either: it is the
 * only sink on a real Windows host and the one a winedbg session reads.
 *
 * So the sinks are layered.  __wine_dbg_output is Wine's own unconditional
 * stderr sink and cannot be intercepted through the exception path; it is
 * Wine-internal and unversioned, so it is resolved at run time, never linked,
 * and its absence is not an error here.  A CI gate checks the pinned WineCX
 * ntdll.spec for it, so losing it fails a pull request rather than silently
 * losing diagnostics.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>

#include "wine_d3d11_diag.h"

namespace
{
/* int __cdecl __wine_dbg_output(const char *).  On x86_64 there is only one
 * calling convention, so the cdecl declaration cannot mismatch here. */
using WineDbgOutputFn = int (*)(const char *);

INIT_ONCE sinkOnce = INIT_ONCE_STATIC_INIT;
WineDbgOutputFn wineDbgOutput = nullptr;

BOOL CALLBACK resolveSinks(PINIT_ONCE, PVOID, PVOID *) noexcept
{
    /* GetModuleHandleW, not LoadLibraryW: ntdll is always already mapped, and
     * this must not add a module reference or run loader work.  Resolving
     * rather than importing also keeps these modules' import table at
     * kernel32 and msvcrt, which CI asserts exactly. */
    const HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");

    if (!ntdll)
        return TRUE;

    const FARPROC address = GetProcAddress(ntdll, "__wine_dbg_output");

    static_assert(sizeof(wineDbgOutput) == sizeof(address),
            "Win32 function and FARPROC pointers must have equal size");
    __builtin_memcpy(&wineDbgOutput, &address, sizeof(wineDbgOutput));
    return TRUE;
}
}

extern "C" void wineD3D11DiagReport(const char *message) noexcept
{
    if (!message || !*message)
        return;

    InitOnceExecuteOnce(&sinkOnce, resolveSinks, nullptr, nullptr);

    /* Wine's sink first, and it reports how much it wrote. */
    const bool reachedWine = wineDbgOutput && wineDbgOutput(message) >= 0;

    /* Still emit to the debugger channel.  A developer with winedbg or a
     * Windows debugger attached looks here, and on a real Windows host this is
     * the only sink there is.  With WINEDEBUG=+debugstr and no application
     * handler this duplicates the line above, which is the right trade against
     * losing the message entirely. */
    OutputDebugStringA(message);

    /* Last resort when this is not a Wine process, or when the internal export
     * is gone.  msvcrt is already an import, and a process under Wine inherits
     * the launching terminal's stderr. */
    if (!reachedWine)
    {
        std::fputs(message, stderr);
        std::fflush(stderr);
    }
}

extern "C" void wineD3D11DiagReportOnce(volatile LONG *guard,
        const char *message) noexcept
{
    if (!guard)
    {
        wineD3D11DiagReport(message);
        return;
    }

    /* Losing a race here would report twice, never zero times. */
    if (InterlockedCompareExchange(guard, 1, 0) != 0)
        return;

    wineD3D11DiagReport(message);
}
