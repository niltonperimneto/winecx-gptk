/* SPDX-License-Identifier: GPL-3.0-only
 *
 * Diagnostics for the D3DMetal D3D11 router and the D3D11On12 core.
 *
 * Neither module is a Wine builtin, so Wine's ERR and TRACE macros are not
 * available to them.  These entry points layer the sinks that are, so a
 * deployment error cannot be swallowed by the application it is about.  See
 * wine_d3d11_diag.cpp for why one sink is not enough.
 *
 * Declared for C as well as C++: the core's validation tests are C and link
 * the core object directly, so they link this object too.
 */
#ifndef WINE_D3D11_DIAG_H
#define WINE_D3D11_DIAG_H

#include <windows.h>

#ifdef __cplusplus
# define WINE_D3D11_DIAG_LINKAGE extern "C"
# define WINE_D3D11_DIAG_NOEXCEPT noexcept
#else
# define WINE_D3D11_DIAG_LINKAGE extern
# define WINE_D3D11_DIAG_NOEXCEPT
#endif

/* Report a complete, newline-terminated message to every available sink. */
WINE_D3D11_DIAG_LINKAGE void wineD3D11DiagReport(const char *message)
        WINE_D3D11_DIAG_NOEXCEPT;

/* Report once per process.  A condition on a path an application can call
 * repeatedly must use this: an application that probes D3D11On12CreateDevice
 * in its initialization loop would otherwise flood the log and bury the
 * messages this exists to surface.  The guard must be static storage
 * initialized to zero, one guard per condition. */
WINE_D3D11_DIAG_LINKAGE void wineD3D11DiagReportOnce(volatile LONG *guard,
        const char *message) WINE_D3D11_DIAG_NOEXCEPT;

#endif /* WINE_D3D11_DIAG_H */
