/* SPDX-License-Identifier: GPL-3.0-only
 *
 * Clean-room D3D11 DDI declarations for the D3D11On12 host.
 *
 * Microsoft's D3D11On12 is a D3D11 user-mode DDI driver, so hosting it needs
 * the D3D11 DDI declarations.  Those live in the proprietary WDK headers
 * (d3d10umddi.h, d3d11umddi.h), which must never be copied into or vendored by
 * this repository.  Every declaration here is authored from public Microsoft
 * documentation and validated by layout tests.
 *
 * Rules for adding a declaration group:
 *
 *   1. Author it from the public specification.  Do not transcribe a WDK
 *      header, and do not reconstruct one from a binary.
 *   2. Precede the group with a provenance block in exactly this form:
 *
 *          /###
 *           * Group: <name>
 *           * Specification: <public URL>
 *           * Retrieved: <YYYY-MM-DD>
 *           ###/
 *
 *      (with real comment delimiters).  CI requires a Specification line for
 *      every group marker.
 *   3. Assert the size, alignment, and every field offset with the
 *      WINE_DDI_ASSERT_* macros below.  An unasserted field is not accepted:
 *      a wrong offset in a DDI structure is a silent memory-corruption bug,
 *      not a compile error.
 *   4. Declare only the single DDI interface version this project selects and
 *      freezes.  Do not add speculative versions.
 *   5. Do not change the packing.  See the frozen binary contract below.
 *
 * A privately authorized WDK job may compare generated metadata against these
 * declarations, but it must never upload or echo WDK content.
 */
#ifndef WINE_D3D11DDI_H
#define WINE_D3D11DDI_H

#include <windows.h>

/*
 * The frozen binary contract.
 *
 * Every offset asserted in this header is the Win64 x86_64 ABI at natural
 * alignment, which is what MSVC's default /Zp8 produces for this DDI: no
 * field here has an alignment above 8, so MinGW-w64 GCC and MSVC agree
 * already.
 *
 * #pragma pack is prohibited in this header, and CI rejects it.  These
 * structures are not packed.  pack(1) would break every offset below, and
 * pack(8) would change nothing while hiding the real alignment from
 * WINE_DDI_ASSERT_ALIGN, whose job is to record it.  The assertions are the
 * mitigation: they are compile-time and fail the build under any ABI where a
 * layout diverges, which a pragma forcing one answer cannot do.
 *
 * An ABI other than this one must re-derive its offsets from the
 * specification and assert them.  It must not inherit these, so building for
 * one is an error rather than a silent reinterpretation.  For ARM in
 * particular, note that packing is not what differs: the offsets of integer,
 * enum, handle, and pointer fields are the same under the ARM64 Windows ABI,
 * and the real exposure is calling convention and ARM64EC thunking at the
 * exported boundary.
 */
#if !defined(_WIN64) || !(defined(__x86_64__) || defined(_M_X64))
# error "the D3D11 DDI declarations are frozen for the Win64 x86_64 ABI"
#endif

#ifdef __cplusplus
# include <cstddef>
# define WINE_DDI_STATIC_ASSERT(condition, message) \
    static_assert(condition, message)
# define WINE_DDI_ALIGNOF(type) alignof(type)
#else
# include <stddef.h>
# define WINE_DDI_STATIC_ASSERT(condition, message) \
    _Static_assert(condition, message)
# define WINE_DDI_ALIGNOF(type) _Alignof(type)
#endif

/* Layout harness.  These are the only sanctioned way to record a DDI
 * structure's binary contract. */
#define WINE_DDI_ASSERT_SIZE(type, expected) \
    WINE_DDI_STATIC_ASSERT(sizeof(type) == (expected), \
            #type " has an unexpected size")

#define WINE_DDI_ASSERT_ALIGN(type, expected) \
    WINE_DDI_STATIC_ASSERT(WINE_DDI_ALIGNOF(type) == (expected), \
            #type " has an unexpected alignment")

#define WINE_DDI_ASSERT_FIELD(type, field, expected) \
    WINE_DDI_STATIC_ASSERT(offsetof(type, field) == (expected), \
            #type "." #field " has an unexpected offset")

#define WINE_DDI_ASSERT_FIELD_SIZE(type, field, expected) \
    WINE_DDI_STATIC_ASSERT(sizeof(((type *)0)->field) == (expected), \
            #type "." #field " has an unexpected size")

/* The DDI is a C ABI shared with a C++ implementation; a group that is not
 * standard-layout cannot have a stable offset contract. */
#ifdef __cplusplus
# include <type_traits>
# define WINE_DDI_ASSERT_STANDARD_LAYOUT(type) \
    WINE_DDI_STATIC_ASSERT(std::is_standard_layout<type>::value, \
            #type " must be standard-layout")
#else
/* Every C structure is standard-layout; keep the macro a declaration in both
 * languages so call sites read the same and still take a semicolon. */
# define WINE_DDI_ASSERT_STANDARD_LAYOUT(type) \
    WINE_DDI_STATIC_ASSERT(sizeof(type) > 0, #type " must be a complete type")
#endif

/*
 * Declaration groups.
 *
 * Authored here so far:
 *
 *   - driver and runtime object handles (adapter, resource, device, and core
 *     layer);
 *   - adapter function tables and the OpenAdapter argument structure;
 *   - the version negotiation arithmetic;
 *   - the CreateDevice argument structure, its embedded DXGI base arguments,
 *     and the create-device flags;
 *   - the core-layer device callback table, signature-complete except for the
 *     two slots the public set does not document;
 *   - the kernel device callback table, with the three slots the pinned driver
 *     invokes promoted and the rest holding their offsets only, and the two
 *     argument structures those three take.
 *
 * Still required by docs/D3D11ON12.md, each to land with its own provenance
 * block and layout assertions:
 *
 *   - context handle types;
 *   - device function tables;
 *   - resource, view, shader, state, query, and command structures;
 *   - the literal DDI version numbers, which the public specification elides;
 *   - DXGI DDI interoperability structures.
 *
 * Until those land the D3D11On12 host cannot be compiled, and the core must
 * keep returning DXGI_ERROR_UNSUPPORTED.
 */

/*
 * Group: driver and runtime object handles
 * Specification: https://learn.microsoft.com/en-us/windows-hardware/drivers/display/direct3d-version-10-runtime-and-driver-handles
 * Retrieved: 2026-09-06
 *
 * The specification gives the resource pair verbatim and states the rule the
 * rest follow: these handles "are essentially pointers that are wrapped with a
 * strong type to identify the object that is being operated on".  A driver
 * handle points at the runtime-allocated private block whose size the driver
 * returned from CalcPrivate<ObjType>Size, so its member is pDrvPrivate; a
 * runtime handle carries an opaque runtime value, so its member is handle.
 *
 * D3D10DDI_HRESOURCE and D3D10DDI_HRTRESOURCE are the page's own code block.
 * The adapter pair's type names come from the D3D10DDIARG_OPENADAPTER syntax
 * block cited in the group below; their contents follow the documented
 * convention.  That is a clean-room derivation, not a quotation, and it is
 * recorded as such.  What the host actually depends on is the binary
 * contract, and that the specification does determine: one pointer, asserted
 * below.
 *
 * Context handles are deliberately absent.  They belong to the deferred
 * context group, which is not authored yet; naming their members from
 * recollection would put an unverified declaration behind a provenance block,
 * which is the one thing this header exists to prevent.  The device and
 * core-layer handles are declared with the device-creation group below, whose
 * argument structure is what names them.
 */
typedef struct D3D10DDI_HADAPTER
{
    void *pDrvPrivate;
} D3D10DDI_HADAPTER;

typedef struct D3D10DDI_HRTADAPTER
{
    void *handle;
} D3D10DDI_HRTADAPTER;

typedef struct D3D10DDI_HRESOURCE
{
    void *pDrvPrivate;
} D3D10DDI_HRESOURCE;

typedef struct D3D10DDI_HRTRESOURCE
{
    void *handle;
} D3D10DDI_HRTRESOURCE;

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3D10DDI_HADAPTER);
WINE_DDI_ASSERT_SIZE(D3D10DDI_HADAPTER, 8);
WINE_DDI_ASSERT_ALIGN(D3D10DDI_HADAPTER, 8);
WINE_DDI_ASSERT_FIELD(D3D10DDI_HADAPTER, pDrvPrivate, 0);
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDI_HADAPTER, pDrvPrivate, 8);

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3D10DDI_HRTADAPTER);
WINE_DDI_ASSERT_SIZE(D3D10DDI_HRTADAPTER, 8);
WINE_DDI_ASSERT_ALIGN(D3D10DDI_HRTADAPTER, 8);
WINE_DDI_ASSERT_FIELD(D3D10DDI_HRTADAPTER, handle, 0);
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDI_HRTADAPTER, handle, 8);

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3D10DDI_HRESOURCE);
WINE_DDI_ASSERT_SIZE(D3D10DDI_HRESOURCE, 8);
WINE_DDI_ASSERT_ALIGN(D3D10DDI_HRESOURCE, 8);
WINE_DDI_ASSERT_FIELD(D3D10DDI_HRESOURCE, pDrvPrivate, 0);
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDI_HRESOURCE, pDrvPrivate, 8);

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3D10DDI_HRTRESOURCE);
WINE_DDI_ASSERT_SIZE(D3D10DDI_HRTRESOURCE, 8);
WINE_DDI_ASSERT_ALIGN(D3D10DDI_HRTRESOURCE, 8);
WINE_DDI_ASSERT_FIELD(D3D10DDI_HRTRESOURCE, handle, 0);
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDI_HRTRESOURCE, handle, 8);

/*
 * Argument structures belonging to groups that are not authored yet.
 *
 * These stay incomplete on purpose.  Every use below is behind a pointer, so
 * an incomplete type carries the correct size and alignment and keeps the
 * function signatures honest, while making it a compile error to touch a
 * field nobody has derived from a specification yet.  Each completes in place
 * when its own group lands, under its own provenance block.
 */
typedef struct D3D10DDIARG_CALCPRIVATEDEVICESIZE D3D10DDIARG_CALCPRIVATEDEVICESIZE;
typedef struct D3D10_2DDIARG_GETCAPS D3D10_2DDIARG_GETCAPS;
typedef struct _D3DDDI_ADAPTERCALLBACKS D3DDDI_ADAPTERCALLBACKS;

/* D3D10DDIARG_CREATEDEVICE is completed by the device-creation group below,
 * and D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS by the core-layer group at the
 * end of this header; the adapter table below needs only their names.  The
 * remaining tables its members point at stay incomplete, and each is the
 * subject of a group of its own. */
typedef struct D3D10DDIARG_CREATEDEVICE D3D10DDIARG_CREATEDEVICE;
typedef struct _D3DDDI_DEVICECALLBACKS D3DDDI_DEVICECALLBACKS;
typedef struct D3DWDDM2_6DDI_DEVICEFUNCS D3DWDDM2_6DDI_DEVICEFUNCS;
typedef struct D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS;
typedef struct DXGI_DDI_BASE_CALLBACKS DXGI_DDI_BASE_CALLBACKS;
typedef struct DXGI1_6_1_DDI_BASE_FUNCTIONS DXGI1_6_1_DDI_BASE_FUNCTIONS;

/*
 * Group: adapter function tables and OpenAdapter arguments
 * Specification: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/ns-d3d10umddi-d3d10ddiarg_openadapter
 * Retrieved: 2026-09-06
 *
 * Companion specifications, all retrieved 2026-09-06:
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/ns-d3d10umddi-d3d10ddi_adapterfuncs
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/ns-d3d10umddi-d3d10_2ddi_adapterfuncs
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/nc-d3d10umddi-pfnd3d10ddi_openadapter
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/nc-d3d10umddi-pfnd3d10ddi_calcprivatedevicesize
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/nc-d3d10umddi-pfnd3d10ddi_createdevice
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/nc-d3d10umddi-pfnd3d10ddi_closeadapter
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/nc-d3d10umddi-pfnd3d10_2ddi_getsupportedversions
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/nc-d3d10umddi-pfnd3d10_2ddi_getcaps
 *
 * D3D11 is why both tables are here: a version 11 driver must implement
 * OpenAdapter10_2, which returns D3D10_2DDI_ADAPTERFUNCS through the
 * pAdapterFuncs_2 arm of the union, while OpenAdapter10 returns
 * D3D10DDI_ADAPTERFUNCS through pAdapterFuncs.  The union is what makes the
 * two entry points share one argument structure, so its offset matters as
 * much as any field's.
 *
 * No calling convention is written on these pointers.  The specification's
 * syntax blocks show none, and this header is frozen to Win64 x86_64, which
 * has a single calling convention, so APIENTRY would be a no-op that implied
 * a contract this group has not verified.  An ABI that does distinguish
 * conventions must re-derive these, as the frozen contract above requires.
 */
typedef SIZE_T (*PFND3D10DDI_CALCPRIVATEDEVICESIZE)(
        D3D10DDI_HADAPTER hAdapter,
        const D3D10DDIARG_CALCPRIVATEDEVICESIZE *pData);

typedef HRESULT (*PFND3D10DDI_CREATEDEVICE)(
        D3D10DDI_HADAPTER hAdapter,
        D3D10DDIARG_CREATEDEVICE *pCreateData);

typedef HRESULT (*PFND3D10DDI_CLOSEADAPTER)(
        D3D10DDI_HADAPTER hAdapter);

typedef HRESULT (*PFND3D10_2DDI_GETSUPPORTEDVERSIONS)(
        D3D10DDI_HADAPTER hAdapter,
        UINT32 *puEntries,
        UINT64 *pSupportedDDIInterfaceVersions);

typedef HRESULT (*PFND3D10_2DDI_GETCAPS)(
        D3D10DDI_HADAPTER hAdapter,
        const D3D10_2DDIARG_GETCAPS *pData);

typedef struct D3D10DDI_ADAPTERFUNCS
{
    PFND3D10DDI_CALCPRIVATEDEVICESIZE pfnCalcPrivateDeviceSize;
    PFND3D10DDI_CREATEDEVICE          pfnCreateDevice;
    PFND3D10DDI_CLOSEADAPTER          pfnCloseAdapter;
} D3D10DDI_ADAPTERFUNCS;

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3D10DDI_ADAPTERFUNCS);
WINE_DDI_ASSERT_SIZE(D3D10DDI_ADAPTERFUNCS, 24);
WINE_DDI_ASSERT_ALIGN(D3D10DDI_ADAPTERFUNCS, 8);
WINE_DDI_ASSERT_FIELD(D3D10DDI_ADAPTERFUNCS, pfnCalcPrivateDeviceSize, 0);
WINE_DDI_ASSERT_FIELD(D3D10DDI_ADAPTERFUNCS, pfnCreateDevice, 8);
WINE_DDI_ASSERT_FIELD(D3D10DDI_ADAPTERFUNCS, pfnCloseAdapter, 16);

typedef struct D3D10_2DDI_ADAPTERFUNCS
{
    PFND3D10DDI_CALCPRIVATEDEVICESIZE  pfnCalcPrivateDeviceSize;
    PFND3D10DDI_CREATEDEVICE           pfnCreateDevice;
    PFND3D10DDI_CLOSEADAPTER           pfnCloseAdapter;
    PFND3D10_2DDI_GETSUPPORTEDVERSIONS pfnGetSupportedVersions;
    PFND3D10_2DDI_GETCAPS              pfnGetCaps;
} D3D10_2DDI_ADAPTERFUNCS;

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3D10_2DDI_ADAPTERFUNCS);
WINE_DDI_ASSERT_SIZE(D3D10_2DDI_ADAPTERFUNCS, 40);
WINE_DDI_ASSERT_ALIGN(D3D10_2DDI_ADAPTERFUNCS, 8);
WINE_DDI_ASSERT_FIELD(D3D10_2DDI_ADAPTERFUNCS, pfnCalcPrivateDeviceSize, 0);
WINE_DDI_ASSERT_FIELD(D3D10_2DDI_ADAPTERFUNCS, pfnCreateDevice, 8);
WINE_DDI_ASSERT_FIELD(D3D10_2DDI_ADAPTERFUNCS, pfnCloseAdapter, 16);
WINE_DDI_ASSERT_FIELD(D3D10_2DDI_ADAPTERFUNCS, pfnGetSupportedVersions, 24);
WINE_DDI_ASSERT_FIELD(D3D10_2DDI_ADAPTERFUNCS, pfnGetCaps, 32);

/* The first three entries are the same functions in the same order in both
 * tables.  OpenAdapter10_2 is the entry point a D3D11 driver must implement,
 * so the host will fill the _2 table; asserting the shared prefix keeps a
 * future edit from reordering one table and silently changing the other's
 * meaning. */
WINE_DDI_STATIC_ASSERT(
        offsetof(D3D10DDI_ADAPTERFUNCS, pfnCalcPrivateDeviceSize)
        == offsetof(D3D10_2DDI_ADAPTERFUNCS, pfnCalcPrivateDeviceSize)
        && offsetof(D3D10DDI_ADAPTERFUNCS, pfnCreateDevice)
        == offsetof(D3D10_2DDI_ADAPTERFUNCS, pfnCreateDevice)
        && offsetof(D3D10DDI_ADAPTERFUNCS, pfnCloseAdapter)
        == offsetof(D3D10_2DDI_ADAPTERFUNCS, pfnCloseAdapter),
        "the adapter tables must share their leading three entries");

typedef struct D3D10DDIARG_OPENADAPTER
{
    D3D10DDI_HRTADAPTER           hRTAdapter;
    D3D10DDI_HADAPTER             hAdapter;
    UINT                          Interface;
    UINT                          Version;
    const D3DDDI_ADAPTERCALLBACKS *pAdapterCallbacks;
    union
    {
        D3D10DDI_ADAPTERFUNCS   *pAdapterFuncs;
        D3D10_2DDI_ADAPTERFUNCS *pAdapterFuncs_2;
    };
} D3D10DDIARG_OPENADAPTER;

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3D10DDIARG_OPENADAPTER);
WINE_DDI_ASSERT_SIZE(D3D10DDIARG_OPENADAPTER, 40);
WINE_DDI_ASSERT_ALIGN(D3D10DDIARG_OPENADAPTER, 8);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_OPENADAPTER, hRTAdapter, 0);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_OPENADAPTER, hAdapter, 8);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_OPENADAPTER, Interface, 16);
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDIARG_OPENADAPTER, Interface, 4);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_OPENADAPTER, Version, 20);
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDIARG_OPENADAPTER, Version, 4);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_OPENADAPTER, pAdapterCallbacks, 24);
/* Both arms are the same storage; a divergence here would mean the union had
 * been turned into a structure, which changes the size of every argument
 * block the runtime passes. */
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_OPENADAPTER, pAdapterFuncs, 32);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_OPENADAPTER, pAdapterFuncs_2, 32);

typedef HRESULT (*PFND3D10DDI_OPENADAPTER)(
        D3D10DDIARG_OPENADAPTER *pOpenData);

/*
 * Group: version negotiation arithmetic
 * Specification: https://learn.microsoft.com/en-us/windows-hardware/drivers/display/initializing-communication-with-the-direct3d-version-11-ddi
 * Retrieved: 2026-09-06
 *
 * The specification gives the major version as a literal and the composition
 * of an interface version and a supported-version word as code.  It does not
 * give the minor and build numbers: D3D11_0_DDI_MINOR_VERSION,
 * D3D11_0_DDI_BUILD_VERSION, D3D11_0_7_DDI_MINOR_VERSION and
 * D3D11_0_7_DDI_BUILD_VERSION all appear as literal ellipses on the page.
 *
 * So the literals are not publicly specified, and this header does not
 * define them.  They exist only in the WDK header, and rule 1 forbids both
 * transcribing that header and reconstructing one from a binary; writing the
 * numbers from recollection would be exactly that, dressed in a provenance
 * block that cites a page which does not contain them.  Whoever supplies them
 * must record where they came from, under a group of their own, and the
 * repository's authorized-WDK-comparison rule above is the only sanctioned
 * route.  A wrong version number here does not corrupt memory; it makes the
 * runtime negotiate a DDI the host does not implement, which is worse,
 * because it fails inside the driver rather than at the boundary.
 *
 * What is publicly specified is the arithmetic, so that is what is captured,
 * parameterised.  These carry the WINE_ prefix deliberately: they are not the
 * WDK's fixed-name object-like macros, and must not be mistaken for them.
 *
 * The decomposition below is the inverse of the published composition rather
 * than a quotation from it, and is recorded as derived.  It is needed because
 * the host is the runtime: it reads supported-version words out of the
 * driver's GetSupportedVersions as data and passes the high 32 bits of its
 * selection back as D3D10DDIARG_CREATEDEVICE.Interface.  Without these, every
 * call site would open-code that shift, and a shift open-coded in several
 * places is a shift that will eventually disagree with itself.
 */
#define D3D11_DDI_MAJOR_VERSION 11

#define WINE_D3D11_DDI_INTERFACE_VERSION(minor) \
    (((D3D11_DDI_MAJOR_VERSION) << 16) | (minor))

#define WINE_D3D11_DDI_SUPPORTED(interface_version, build_version) \
    ((((UINT64)(interface_version)) << 32) | (((UINT64)(build_version)) << 16))

#define WINE_D3D11_DDI_INTERFACE_FROM_SUPPORTED(supported) \
    ((UINT)(((UINT64)(supported)) >> 32))

#define WINE_D3D11_DDI_BUILD_FROM_SUPPORTED(supported) \
    ((UINT)((((UINT64)(supported)) >> 16) & 0xffffu))

#define WINE_D3D11_DDI_MAJOR_FROM_INTERFACE(interface_version) \
    ((UINT)((((UINT)(interface_version)) >> 16) & 0xffffu))

#define WINE_D3D11_DDI_MINOR_FROM_INTERFACE(interface_version) \
    ((UINT)(((UINT)(interface_version)) & 0xffffu))

/* The arithmetic is the whole content of this group, so it is asserted rather
 * than trusted.  The operands are arbitrary and carry no claim about any real
 * DDI version. */
WINE_DDI_STATIC_ASSERT(D3D11_DDI_MAJOR_VERSION == 11,
        "the D3D11 DDI major version is 11");
WINE_DDI_STATIC_ASSERT(WINE_D3D11_DDI_INTERFACE_VERSION(3) == 0x000b0003,
        "an interface version is the major version in the high 16 bits");
WINE_DDI_STATIC_ASSERT(
        WINE_D3D11_DDI_SUPPORTED(0x000b0003, 0x0007) == 0x000b000300070000ULL,
        "a supported-version word is the interface version in the high 32 "
        "bits and the build version in the next 16");

/* Decomposition, asserted against the composition at the ends of each field's
 * range rather than in the middle.  A mask that is one bit too wide or a shift
 * that is one bit off reads correctly for a small minor and build number,
 * which is exactly what a real DDI version looks like, so the interesting
 * operands are 0 and 0xffff. */
WINE_DDI_STATIC_ASSERT(
        WINE_D3D11_DDI_MAJOR_FROM_INTERFACE(WINE_D3D11_DDI_INTERFACE_VERSION(0))
        == D3D11_DDI_MAJOR_VERSION
        && WINE_D3D11_DDI_MINOR_FROM_INTERFACE(
                WINE_D3D11_DDI_INTERFACE_VERSION(0)) == 0,
        "an interface version with no minor number round-trips");
WINE_DDI_STATIC_ASSERT(
        WINE_D3D11_DDI_MAJOR_FROM_INTERFACE(
                WINE_D3D11_DDI_INTERFACE_VERSION(0xffff))
        == D3D11_DDI_MAJOR_VERSION
        && WINE_D3D11_DDI_MINOR_FROM_INTERFACE(
                WINE_D3D11_DDI_INTERFACE_VERSION(0xffff)) == 0xffff,
        "the largest minor number does not reach the major number's field");
WINE_DDI_STATIC_ASSERT(
        WINE_D3D11_DDI_INTERFACE_FROM_SUPPORTED(
                WINE_D3D11_DDI_SUPPORTED(0x000b0003, 0)) == 0x000b0003
        && WINE_D3D11_DDI_BUILD_FROM_SUPPORTED(
                WINE_D3D11_DDI_SUPPORTED(0x000b0003, 0)) == 0,
        "a supported-version word with no build number round-trips");
WINE_DDI_STATIC_ASSERT(
        WINE_D3D11_DDI_INTERFACE_FROM_SUPPORTED(
                WINE_D3D11_DDI_SUPPORTED(0x000b0003, 0xffff)) == 0x000b0003
        && WINE_D3D11_DDI_BUILD_FROM_SUPPORTED(
                WINE_D3D11_DDI_SUPPORTED(0x000b0003, 0xffff)) == 0xffff,
        "the largest build number does not reach the interface version");
/* The interface version occupies the high half of a 64-bit word, so a
 * decomposition that went through a signed type would sign-extend a version
 * whose top bit is set.  No real D3D11 version does, and relying on that is
 * how the bug would survive to the day one does. */
WINE_DDI_STATIC_ASSERT(
        WINE_D3D11_DDI_INTERFACE_FROM_SUPPORTED(0xffffffff00000000ULL)
        == 0xffffffffu,
        "decomposing a supported-version word must not sign-extend");
/* The low 16 bits are the runtime's revision number.  Neither accessor claims
 * them, and neither may quietly fold them into the build number. */
WINE_DDI_STATIC_ASSERT(
        WINE_D3D11_DDI_BUILD_FROM_SUPPORTED(
                WINE_D3D11_DDI_SUPPORTED(0x000b0003, 0x0007) | 0xffffULL)
        == 0x0007,
        "the revision bits are not part of the build number");

/*
 * Group: device creation
 * Specification: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/ns-d3d10umddi-d3d10ddiarg_createdevice
 * Retrieved: 2026-09-07
 *
 * Companion specifications, all retrieved 2026-09-07:
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/dxgiddi/ns-dxgiddi-dxgi_ddi_base_args
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/nc-d3d10umddi-pfnd3d10ddi_retrievesubobject
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/display/direct3d-version-10-runtime-and-driver-handles
 *
 * This is the structure the host fills and hands to the driver's CreateDevice,
 * so it is the whole device-level boundary in one declaration.  Both
 * documentation surfaces were cross-validated before it was written: the
 * rendered syntax block and the markdown mirror agree on 23 members in the
 * same order.
 *
 * Only the union arms the pinned D3D11On12 source reads are declared, as rule
 * 4 requires.  The specification prints nine device-function arms
 * (pDeviceFuncs, p10_1DeviceFuncs, p11DeviceFuncs, p11_1DeviceFuncs,
 * pWDDM1_3DeviceFuncs, pWDDM2_0DeviceFuncs, pWDDM2_1DeviceFuncs,
 * pWDDM2_2DeviceFuncs, pWDDM2_6DeviceFuncs) and five core-layer arms
 * (pUMCallbacks, p11UMCallbacks, pWDDM2_0UMCallbacks, pWDDM2_2UMCallbacks,
 * pWDDM2_6UMCallbacks).  The pinned driver's GetDeviceFuncsFromCreateArgs
 * returns pWDDM2_6DeviceFuncs and its DeviceBase constructor reads
 * pWDDM2_6UMCallbacks, unconditionally and for both versions it advertises, so
 * those are the two declared here.  The full arm lists are recorded above so
 * the omission is a declaration choice rather than a transcription loss; every
 * arm is a pointer at the same offset, and scripts/gen_ddi_layout.py models
 * both arm sets and checks they agree on every offset and on the size.
 *
 * The device handle's member name is quoted from the pinned MIT driver, which
 * constructs its device with "new (pArgs->hDrvDevice.pDrvPrivate) Device".
 * The two runtime handles' member names follow the documented convention, as
 * the adapter pair's do, and that is a derivation rather than a quotation.
 * What the host depends on is one wrapped pointer each, and that is asserted.
 *
 * DXGI_DDI_BASE_ARGS is embedded by value, so it is declared first.  Its
 * function-table union has seven published arms; the pinned driver reads
 * pDXGIDDIBaseFunctions6_1, so that is the one declared.  DXGI1_6_1_DDI_BASE_-
 * FUNCTIONS has no reference page of its own in the published set; the name is
 * quoted from the DXGI_DDI_BASE_ARGS syntax block and used only as an
 * incomplete type behind a pointer, which is all this group needs it for.
 *
 * ppfnRetrieveSubObject is a pointer to a function pointer: the runtime
 * supplies the storage and the driver writes its implementation into it, which
 * the pinned driver does as "*pArgs->ppfnRetrieveSubObject = RetrieveSubObject".
 * So the host must point it at a writable slot it owns, not at a null.
 */
typedef struct D3D10DDI_HDEVICE
{
    void *pDrvPrivate;
} D3D10DDI_HDEVICE;

typedef struct D3D10DDI_HRTDEVICE
{
    void *handle;
} D3D10DDI_HRTDEVICE;

typedef struct D3D10DDI_HRTCORELAYER
{
    void *handle;
} D3D10DDI_HRTCORELAYER;

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3D10DDI_HDEVICE);
WINE_DDI_ASSERT_SIZE(D3D10DDI_HDEVICE, 8);
WINE_DDI_ASSERT_ALIGN(D3D10DDI_HDEVICE, 8);
WINE_DDI_ASSERT_FIELD(D3D10DDI_HDEVICE, pDrvPrivate, 0);
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDI_HDEVICE, pDrvPrivate, 8);

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3D10DDI_HRTDEVICE);
WINE_DDI_ASSERT_SIZE(D3D10DDI_HRTDEVICE, 8);
WINE_DDI_ASSERT_ALIGN(D3D10DDI_HRTDEVICE, 8);
WINE_DDI_ASSERT_FIELD(D3D10DDI_HRTDEVICE, handle, 0);
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDI_HRTDEVICE, handle, 8);

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3D10DDI_HRTCORELAYER);
WINE_DDI_ASSERT_SIZE(D3D10DDI_HRTCORELAYER, 8);
WINE_DDI_ASSERT_ALIGN(D3D10DDI_HRTCORELAYER, 8);
WINE_DDI_ASSERT_FIELD(D3D10DDI_HRTCORELAYER, handle, 0);
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDI_HRTCORELAYER, handle, 8);

/* The runtime allocates the slot and the driver writes its function pointer
 * into it, so the host owns the storage this points at. */
typedef HRESULT (*PFND3D10DDI_RETRIEVESUBOBJECT)(
        D3D10DDI_HDEVICE hDevice,
        UINT32 SubDeviceID,
        SIZE_T ParamSize,
        void *pParams,
        SIZE_T OutputParamSize,
        void *pOutputParamsBuffer);

typedef struct DXGI_DDI_BASE_ARGS
{
    DXGI_DDI_BASE_CALLBACKS *pDXGIBaseCallbacks;
    union
    {
        DXGI1_6_1_DDI_BASE_FUNCTIONS *pDXGIDDIBaseFunctions6_1;
    };
} DXGI_DDI_BASE_ARGS;

WINE_DDI_ASSERT_STANDARD_LAYOUT(DXGI_DDI_BASE_ARGS);
WINE_DDI_ASSERT_SIZE(DXGI_DDI_BASE_ARGS, 16);
WINE_DDI_ASSERT_ALIGN(DXGI_DDI_BASE_ARGS, 8);
WINE_DDI_ASSERT_FIELD(DXGI_DDI_BASE_ARGS, pDXGIBaseCallbacks, 0);
WINE_DDI_ASSERT_FIELD(DXGI_DDI_BASE_ARGS, pDXGIDDIBaseFunctions6_1, 8);

struct D3D10DDIARG_CREATEDEVICE
{
    D3D10DDI_HRTDEVICE             hRTDevice;
    UINT                           Interface;
    UINT                           Version;
    const D3DDDI_DEVICECALLBACKS   *pKTCallbacks;
    union
    {
        D3DWDDM2_6DDI_DEVICEFUNCS *pWDDM2_6DeviceFuncs;
    };
    D3D10DDI_HDEVICE               hDrvDevice;
    DXGI_DDI_BASE_ARGS             DXGIBaseDDI;
    D3D10DDI_HRTCORELAYER          hRTCoreLayer;
    union
    {
        const D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS *pWDDM2_6UMCallbacks;
    };
    UINT                           Flags;
    PFND3D10DDI_RETRIEVESUBOBJECT  *ppfnRetrieveSubObject;
};

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3D10DDIARG_CREATEDEVICE);
WINE_DDI_ASSERT_SIZE(D3D10DDIARG_CREATEDEVICE, 88);
WINE_DDI_ASSERT_ALIGN(D3D10DDIARG_CREATEDEVICE, 8);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, hRTDevice, 0);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, Interface, 8);
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDIARG_CREATEDEVICE, Interface, 4);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, Version, 12);
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDIARG_CREATEDEVICE, Version, 4);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, pKTCallbacks, 16);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, pWDDM2_6DeviceFuncs, 24);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, hDrvDevice, 32);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, DXGIBaseDDI, 40);
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDIARG_CREATEDEVICE, DXGIBaseDDI, 16);
/* The embedded structure's own members, located from the enclosing
 * structure's base.  These are what stop DXGI_DDI_BASE_ARGS from being turned
 * into a pointer: that would keep its own assertions true and move every
 * member after it here. */
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE,
        DXGIBaseDDI.pDXGIBaseCallbacks, 40);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE,
        DXGIBaseDDI.pDXGIDDIBaseFunctions6_1, 48);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, hRTCoreLayer, 56);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, pWDDM2_6UMCallbacks, 64);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, Flags, 72);
/* Flags is four bytes at 72 and the next member is eight-byte aligned, so
 * there are four bytes of padding here that no member names.  The runtime
 * allocates this structure, and a driver reading uninitialized padding is a
 * bug the host cannot see, so the host must zero the whole structure rather
 * than assign member by member. */
WINE_DDI_ASSERT_FIELD_SIZE(D3D10DDIARG_CREATEDEVICE, Flags, 4);
WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, ppfnRetrieveSubObject, 80);

/*
 * The create-device flags.
 *
 * Quoted from the Flags member's table and remarks on the group's
 * specification page.  Only these are published: the pinned driver also tests
 * D3D11DDI_CREATEDEVICE_FLAG_IS_XBOX, whose value appears in no public
 * document, so it is not defined here.  Nothing is lost by that — the host
 * would never set it — but a host that needs to must record where the value
 * came from, under a group of its own.
 *
 * The 3-D pipeline level occupies the three bits the mask covers.  Extracting
 * it needs the D3D11DDI_3DPIPELINELEVEL enumeration, which belongs to the
 * GetCaps group and is not authored; the pinned driver never reads those bits
 * on this path, so the mask is declared and the extraction is not.  What the
 * mask is for here is knowing that bits 1 through 3 of Flags are not free.
 */
#define D3D10DDI_CREATEDEVICE_FLAG_DISABLE_EXTRA_THREAD_CREATION 0x1
#define D3D11DDI_CREATEDEVICE_FLAG_SINGLETHREADED 0x10

#define D3D11DDI_CREATEDEVICE_FLAG_3DPIPELINESUPPORT_SHIFT (0x1)
#define D3D11DDI_CREATEDEVICE_FLAG_3DPIPELINESUPPORT_MASK \
    (0x7 << D3D11DDI_CREATEDEVICE_FLAG_3DPIPELINESUPPORT_SHIFT)

/* The page states the pipeline level occupies the 0xE mask and separately
 * gives the shift and mask as code.  Asserting that the two agree, and that
 * neither named flag lands inside the mask, is the only check available
 * against a transcription error in a set of literals. */
WINE_DDI_STATIC_ASSERT(D3D11DDI_CREATEDEVICE_FLAG_3DPIPELINESUPPORT_MASK
        == 0xe, "the 3-D pipeline level occupies the 0xE mask");
WINE_DDI_STATIC_ASSERT(
        (D3D10DDI_CREATEDEVICE_FLAG_DISABLE_EXTRA_THREAD_CREATION
                & D3D11DDI_CREATEDEVICE_FLAG_3DPIPELINESUPPORT_MASK) == 0
        && (D3D11DDI_CREATEDEVICE_FLAG_SINGLETHREADED
                & D3D11DDI_CREATEDEVICE_FLAG_3DPIPELINESUPPORT_MASK) == 0,
        "no create-device flag may overlap the 3-D pipeline level mask");

/*
 * Group: core-layer device callbacks
 * Specification: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/ns-d3d10umddi-d3dwddm2_6ddi_corelayer_devicecallbacks
 * Retrieved: 2026-09-07
 *
 * This is the table the host fills and the driver calls, which is why it is
 * authored signature-complete rather than as bare slots.  Every other table so
 * far is filled by the driver and called by the host, so an unpromoted slot
 * there is simply never invoked; here the driver invokes the host on its own
 * schedule and with its own arguments, and a slot whose signature is wrong is
 * a corrupted call frame rather than a missing feature.
 *
 * Both documentation surfaces were cross-validated before it was written: the
 * rendered syntax block and the markdown mirror agree on 47 members in the
 * same order.  46 of the member types are distinct;
 * PFND3DWDDM2_2DDI_SHADERCACHE_ADDREF_RELEASE_CB is the one type used twice,
 * for pfnShaderCacheAddRefCb and pfnShaderCacheReleaseCb.
 *
 * Note that pfnDisableDeferredStagingResourceDestruction is the one member
 * with no Cb suffix.  Both surfaces spell it that way; it is not a typo here.
 *
 * Companion specifications, all retrieved 2026-09-07, each the page
 * https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3d10umddi/<slug>
 * for the slug listed:
 *
 *   nc-d3d10umddi-pfnd3d10ddi_seterror_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_vs_constbuf_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_ps_srv_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_ps_shader_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_ps_sampler_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_vs_shader_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_ps_constbuf_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_ia_inputlayout_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_ia_vertexbuf_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_ia_indexbuf_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_gs_constbuf_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_gs_shader_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_ia_primitive_topology_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_vs_srv_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_vs_sampler_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_gs_srv_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_gs_sampler_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_om_rendertargets_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_om_blendstate_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_om_depthstate_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_rs_raststate_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_so_targets_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_rs_viewports_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_rs_scissor_cb
 *   nc-d3d10umddi-pfnd3d10ddi_disable_deferred_staging_resource_destruction_cb
 *   nc-d3d10umddi-pfnd3d10ddi_state_textfiltersize_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_hs_srv_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_hs_shader_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_hs_sampler_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_hs_constbuf_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_ds_srv_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_ds_shader_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_ds_sampler_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_ds_constbuf_cb
 *   nc-d3d10umddi-pfnd3d11ddi_perform_amortized_processing_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_cs_srv_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_cs_uav_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_cs_shader_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_cs_sampler_cb
 *   nc-d3d10umddi-pfnd3d11ddi_state_cs_constbuf_cb
 *   nc-d3d10umddi-pfnd3dwddm2_2ddi_shadercache_store_value_cb
 *   nc-d3d10umddi-pfnd3dwddm2_2ddi_shadercache_addref_release_cb
 *
 * and, for the two context-creation slots, whose own typedef names have no
 * page and whose documentation the structure page points at instead:
 *
 *   https://learn.microsoft.com/en-us/previous-versions/ff568895(v=vs.85)
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dumddi/nc-d3dumddi-pfnd3dddi_createcontextvirtualcb
 *
 * Base and Count are not in the same order in both halves of this table, and
 * that is quoted, not a transcription slip.  The D3D10-era pages document
 * (hRuntimeDevice, Count, Base); the D3D11-era pages document
 * (hRuntimeDevice, Base, Count).  Both parameters are UINT, so nothing about
 * the ABI distinguishes them and no assertion here can catch a host that
 * implements one family with the other's order.  The parameter names below
 * are therefore load-bearing documentation rather than decoration.
 *
 * Two slots are declared without a signature.  The structure page names their
 * types but the public set contains no page for either
 * PFND3DWDDM2_2DDI_SHADERCACHE_GET_VALUE_CB or
 * PFND3DWDDM2_6DDI_QUERY_SCANOUT_CAPS_CB: both surfaces return 404, and the
 * structure page prints no link for them where it links every other member.
 * Rule 1 forbids reconstructing what is not published, so they take the
 * undeclared-slot type below.  Their offsets are exact, which is what the
 * table's layout depends on; what is missing is only the ability to implement
 * them, and a host that needs to must record where the signature came from
 * under a group of its own.
 *
 * D3DWDDM2_2DDI_HRTCACHESESSION is a runtime handle, and its name is quoted
 * from the shader-cache syntax blocks above.  Its contents follow the
 * documented runtime-handle convention, exactly as the adapter pair's do, and
 * that is a derivation rather than a quotation.  The argument structures the
 * remaining slots point at stay incomplete, each the subject of a group of its
 * own: what this group needs from them is a pointer.
 *
 * No calling convention is written on these pointers, for the reason the
 * adapter tables record.  The archived pfnCreateContextCb page does print
 * APIENTRY CALLBACK, but this header is frozen to Win64 x86_64, where that
 * expands to the one calling convention there is.
 */
typedef struct D3DWDDM2_2DDI_HRTCACHESESSION
{
    void *handle;
} D3DWDDM2_2DDI_HRTCACHESESSION;

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3DWDDM2_2DDI_HRTCACHESESSION);
WINE_DDI_ASSERT_SIZE(D3DWDDM2_2DDI_HRTCACHESESSION, 8);
WINE_DDI_ASSERT_ALIGN(D3DWDDM2_2DDI_HRTCACHESESSION, 8);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_2DDI_HRTCACHESESSION, handle, 0);
WINE_DDI_ASSERT_FIELD_SIZE(D3DWDDM2_2DDI_HRTCACHESESSION, handle, 8);

typedef struct D3DWDDM2_2DDI_SHADERCACHE_HASH D3DWDDM2_2DDI_SHADERCACHE_HASH;
typedef struct _D3DDDICB_CREATECONTEXT D3DDDICB_CREATECONTEXT;
typedef struct _D3DDDICB_CREATECONTEXTVIRTUAL D3DDDICB_CREATECONTEXTVIRTUAL;

/* A slot whose signature the public specification does not give.  It is a
 * function pointer, so its size and every offset after it are exact, but it
 * takes no arguments and returns nothing, so calling it as though its real
 * contract were known does not compile without an explicit cast.  That is the
 * point: an undeclared contract must be impossible to invoke by accident. */
typedef void (*PFNWINE_D3D11DDI_UNDECLARED_CB)(void);

/* The one callback that reports a driver-side failure to the runtime.  Every
 * DDI entry point that returns void uses this instead. */
typedef VOID (*PFND3D10DDI_SETERROR_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice,
        HRESULT hResult);

/* The D3D10-era state refresh callbacks that name no range: the runtime
 * refreshes the whole of the state in question. */
typedef void (*PFND3D10DDI_STATE_PS_SHADER_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_VS_SHADER_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_GS_SHADER_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_IA_INPUTLAYOUT_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_IA_INDEXBUF_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_IA_PRIMITIVE_TOPOLOGY_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_OM_RENDERTARGETS_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_OM_BLENDSTATE_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_OM_DEPTHSTATE_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_RS_RASTSTATE_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_SO_TARGETS_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_RS_VIEWPORTS_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_RS_SCISSOR_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_STATE_TEXTFILTERSIZE_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D10DDI_DISABLE_DEFERRED_STAGING_RESOURCE_DESTRUCTION_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);

/* The D3D10-era state refresh callbacks that name a range, as (Count, Base).
 * Count may be passed as -1, which asks the runtime to substitute its own
 * high-water mark, so a host must not treat it as an unsigned array length. */
typedef void (*PFND3D10DDI_STATE_VS_CONSTBUF_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Count, UINT Base);
typedef void (*PFND3D10DDI_STATE_PS_CONSTBUF_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Count, UINT Base);
typedef void (*PFND3D10DDI_STATE_GS_CONSTBUF_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Count, UINT Base);
typedef void (*PFND3D10DDI_STATE_VS_SRV_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Count, UINT Base);
typedef void (*PFND3D10DDI_STATE_PS_SRV_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Count, UINT Base);
typedef void (*PFND3D10DDI_STATE_GS_SRV_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Count, UINT Base);
typedef void (*PFND3D10DDI_STATE_VS_SAMPLER_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Count, UINT Base);
typedef void (*PFND3D10DDI_STATE_PS_SAMPLER_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Count, UINT Base);
typedef void (*PFND3D10DDI_STATE_GS_SAMPLER_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Count, UINT Base);
typedef void (*PFND3D10DDI_STATE_IA_VERTEXBUF_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Count, UINT Base);

/* The D3D11-era state refresh callbacks.  Same two UINTs, documented in the
 * opposite order: (Base, Count). */
typedef void (*PFND3D11DDI_STATE_HS_SHADER_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D11DDI_STATE_DS_SHADER_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D11DDI_STATE_CS_SHADER_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D11DDI_PERFORM_AMORTIZED_PROCESSING_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice);
typedef void (*PFND3D11DDI_STATE_HS_SRV_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Base, UINT Count);
typedef void (*PFND3D11DDI_STATE_HS_SAMPLER_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Base, UINT Count);
typedef void (*PFND3D11DDI_STATE_HS_CONSTBUF_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Base, UINT Count);
typedef void (*PFND3D11DDI_STATE_DS_SRV_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Base, UINT Count);
typedef void (*PFND3D11DDI_STATE_DS_SAMPLER_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Base, UINT Count);
typedef void (*PFND3D11DDI_STATE_DS_CONSTBUF_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Base, UINT Count);
typedef void (*PFND3D11DDI_STATE_CS_SRV_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Base, UINT Count);
typedef void (*PFND3D11DDI_STATE_CS_UAV_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Base, UINT Count);
typedef void (*PFND3D11DDI_STATE_CS_SAMPLER_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Base, UINT Count);
typedef void (*PFND3D11DDI_STATE_CS_CONSTBUF_CB)(
        D3D10DDI_HRTCORELAYER hRuntimeDevice, UINT Base, UINT Count);

/* The kernel-facing slots.  These take the display device handle rather than
 * the core-layer handle, because they reach past the runtime into the display
 * kernel; docs/D3D11ON12.md lists the display-kernel paths as disabled for
 * this port, so the host is expected to refuse rather than forward them. */
typedef HRESULT (*PFND3DWDDM2_0DDI_CREATECONTEXT_CB)(
        HANDLE hDevice,
        D3DDDICB_CREATECONTEXT *pData);
typedef HRESULT (*PFND3DWDDM2_0DDI_CREATECONTEXTVIRTUAL_CB)(
        HANDLE hDevice,
        D3DDDICB_CREATECONTEXTVIRTUAL *pData);

/* The shader cache.  Get is undeclared above; store and the shared
 * addref/release entry point are published. */
typedef HRESULT (*PFND3DWDDM2_2DDI_SHADERCACHE_STORE_VALUE_CB)(
        D3DWDDM2_2DDI_HRTCACHESESSION hCacheSession,
        const D3DWDDM2_2DDI_SHADERCACHE_HASH *pPrecomputedHash,
        const void *pKey,
        SIZE_T KeyLen,
        const void *pValue,
        SIZE_T ValueLen);
typedef void (*PFND3DWDDM2_2DDI_SHADERCACHE_ADDREF_RELEASE_CB)(
        D3DWDDM2_2DDI_HRTCACHESESSION hCacheSession);

typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DWDDM2_2DDI_SHADERCACHE_GET_VALUE_CB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DWDDM2_6DDI_QUERY_SCANOUT_CAPS_CB;

struct D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS
{
    PFND3D10DDI_SETERROR_CB                    pfnSetErrorCb;
    PFND3D10DDI_STATE_VS_CONSTBUF_CB           pfnStateVsConstBufCb;
    PFND3D10DDI_STATE_PS_SRV_CB                pfnStatePsSrvCb;
    PFND3D10DDI_STATE_PS_SHADER_CB             pfnStatePsShaderCb;
    PFND3D10DDI_STATE_PS_SAMPLER_CB            pfnStatePsSamplerCb;
    PFND3D10DDI_STATE_VS_SHADER_CB             pfnStateVsShaderCb;
    PFND3D10DDI_STATE_PS_CONSTBUF_CB           pfnStatePsConstBufCb;
    PFND3D10DDI_STATE_IA_INPUTLAYOUT_CB        pfnStateIaInputLayoutCb;
    PFND3D10DDI_STATE_IA_VERTEXBUF_CB          pfnStateIaVertexBufCb;
    PFND3D10DDI_STATE_IA_INDEXBUF_CB           pfnStateIaIndexBufCb;
    PFND3D10DDI_STATE_GS_CONSTBUF_CB           pfnStateGsConstBufCb;
    PFND3D10DDI_STATE_GS_SHADER_CB             pfnStateGsShaderCb;
    PFND3D10DDI_STATE_IA_PRIMITIVE_TOPOLOGY_CB pfnStateIaPrimitiveTopologyCb;
    PFND3D10DDI_STATE_VS_SRV_CB                pfnStateVsSrvCb;
    PFND3D10DDI_STATE_VS_SAMPLER_CB            pfnStateVsSamplerCb;
    PFND3D10DDI_STATE_GS_SRV_CB                pfnStateGsSrvCb;
    PFND3D10DDI_STATE_GS_SAMPLER_CB            pfnStateGsSamplerCb;
    PFND3D10DDI_STATE_OM_RENDERTARGETS_CB      pfnStateOmRenderTargetsCb;
    PFND3D10DDI_STATE_OM_BLENDSTATE_CB         pfnStateOmBlendStateCb;
    PFND3D10DDI_STATE_OM_DEPTHSTATE_CB         pfnStateOmDepthStateCb;
    PFND3D10DDI_STATE_RS_RASTSTATE_CB          pfnStateRsRastStateCb;
    PFND3D10DDI_STATE_SO_TARGETS_CB            pfnStateSoTargetsCb;
    PFND3D10DDI_STATE_RS_VIEWPORTS_CB          pfnStateRsViewportsCb;
    PFND3D10DDI_STATE_RS_SCISSOR_CB            pfnStateRsScissorCb;
    PFND3D10DDI_DISABLE_DEFERRED_STAGING_RESOURCE_DESTRUCTION_CB
                                               pfnDisableDeferredStagingResourceDestruction;
    PFND3D10DDI_STATE_TEXTFILTERSIZE_CB        pfnStateTextFilterSizeCb;
    PFND3D11DDI_STATE_HS_SRV_CB                pfnStateHsSrvCb;
    PFND3D11DDI_STATE_HS_SHADER_CB             pfnStateHsShaderCb;
    PFND3D11DDI_STATE_HS_SAMPLER_CB            pfnStateHsSamplerCb;
    PFND3D11DDI_STATE_HS_CONSTBUF_CB           pfnStateHsConstBufCb;
    PFND3D11DDI_STATE_DS_SRV_CB                pfnStateDsSrvCb;
    PFND3D11DDI_STATE_DS_SHADER_CB             pfnStateDsShaderCb;
    PFND3D11DDI_STATE_DS_SAMPLER_CB            pfnStateDsSamplerCb;
    PFND3D11DDI_STATE_DS_CONSTBUF_CB           pfnStateDsConstBufCb;
    PFND3D11DDI_PERFORM_AMORTIZED_PROCESSING_CB pfnPerformAmortizedProcessingCb;
    PFND3D11DDI_STATE_CS_SRV_CB                pfnStateCsSrvCb;
    PFND3D11DDI_STATE_CS_UAV_CB                pfnStateCsUavCb;
    PFND3D11DDI_STATE_CS_SHADER_CB             pfnStateCsShaderCb;
    PFND3D11DDI_STATE_CS_SAMPLER_CB            pfnStateCsSamplerCb;
    PFND3D11DDI_STATE_CS_CONSTBUF_CB           pfnStateCsConstBufCb;
    PFND3DWDDM2_0DDI_CREATECONTEXT_CB          pfnCreateContextCb;
    PFND3DWDDM2_0DDI_CREATECONTEXTVIRTUAL_CB   pfnCreateContextVirtualCb;
    PFND3DWDDM2_2DDI_SHADERCACHE_GET_VALUE_CB  pfnShaderCacheGetValueCb;
    PFND3DWDDM2_2DDI_SHADERCACHE_STORE_VALUE_CB pfnShaderCacheStoreValueCb;
    PFND3DWDDM2_2DDI_SHADERCACHE_ADDREF_RELEASE_CB pfnShaderCacheAddRefCb;
    PFND3DWDDM2_2DDI_SHADERCACHE_ADDREF_RELEASE_CB pfnShaderCacheReleaseCb;
    PFND3DWDDM2_6DDI_QUERY_SCANOUT_CAPS_CB     pfnQueryScanoutCapsCb;
};

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS);
WINE_DDI_ASSERT_SIZE(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS, 376);
WINE_DDI_ASSERT_ALIGN(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS, 8);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnSetErrorCb, 0);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateVsConstBufCb, 8);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStatePsSrvCb, 16);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStatePsShaderCb, 24);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStatePsSamplerCb, 32);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateVsShaderCb, 40);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStatePsConstBufCb, 48);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateIaInputLayoutCb, 56);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateIaVertexBufCb, 64);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateIaIndexBufCb, 72);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateGsConstBufCb, 80);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateGsShaderCb, 88);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateIaPrimitiveTopologyCb, 96);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateVsSrvCb, 104);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateVsSamplerCb, 112);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateGsSrvCb, 120);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateGsSamplerCb, 128);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateOmRenderTargetsCb, 136);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateOmBlendStateCb, 144);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateOmDepthStateCb, 152);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateRsRastStateCb, 160);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateSoTargetsCb, 168);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateRsViewportsCb, 176);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateRsScissorCb, 184);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnDisableDeferredStagingResourceDestruction, 192);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateTextFilterSizeCb, 200);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateHsSrvCb, 208);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateHsShaderCb, 216);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateHsSamplerCb, 224);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateHsConstBufCb, 232);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateDsSrvCb, 240);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateDsShaderCb, 248);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateDsSamplerCb, 256);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateDsConstBufCb, 264);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnPerformAmortizedProcessingCb, 272);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateCsSrvCb, 280);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateCsUavCb, 288);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateCsShaderCb, 296);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateCsSamplerCb, 304);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnStateCsConstBufCb, 312);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnCreateContextCb, 320);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnCreateContextVirtualCb, 328);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnShaderCacheGetValueCb, 336);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnShaderCacheStoreValueCb, 344);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnShaderCacheAddRefCb, 352);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnShaderCacheReleaseCb, 360);
WINE_DDI_ASSERT_FIELD(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS,
        pfnQueryScanoutCapsCb, 368);

/* Every slot is a function pointer, so the table is exactly its member count
 * times the pointer size.  Asserting that as arithmetic rather than as another
 * literal is what catches a member being dropped and its offsets renumbered to
 * match, which is the one mistake the per-field assertions above cannot see. */
WINE_DDI_STATIC_ASSERT(
        sizeof(D3DWDDM2_6DDI_CORELAYER_DEVICECALLBACKS)
        == 47 * sizeof(void (*)(void)),
        "the core-layer callback table is 47 function pointers");

/*
 * Group: kernel device callbacks
 * Specification: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dumddi/ns-d3dumddi-_d3dddi_devicecallbacks
 * Retrieved: 2026-09-07
 *
 * Companion specifications, all retrieved 2026-09-07:
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dumddi/ns-d3dumddi-_d3dddicb_escape
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dumddi/ns-d3dumddi-_d3dddicb_synctoken
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dumddi/nc-d3dumddi-pfnd3dddi_escapecb
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dumddi/nc-d3dumddi-pfnd3dddi_synctokencb
 *   https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dukmdt/ns-d3dukmdt-_d3dddi_escapeflags
 *
 * This is D3D10DDIARG_CREATEDEVICE's pKTCallbacks, the second and last table
 * the host fills and the driver calls, and the last unauthored member of the
 * device-creation arguments.
 *
 * Unlike the core-layer table, this one is not authored signature-complete.
 * The pinned driver reads exactly three of its slots, and the roadmap in
 * docs/CLEANROOM-DDI.md asks for only the members D3D11On12 invokes:
 *
 *   pfnEscapeCb          (slot 10) src/device.cpp, in Device::ReportError
 *   pfnAcquireResourceCb (slot 54) include/device.hpp, via a pointer-to-member
 *   pfnReleaseResourceCb (slot 55) include/device.hpp, likewise
 *
 * So the promoted set and the invoked set are the same set, deliberately.
 * Every other slot keeps its published type name as an alias of the
 * undeclared-slot type, which holds the offset exactly, cannot be called
 * without a cast, and turns promoting a signature later into a one-line change
 * here rather than an edit to the structure.  scripts/gen_ddi_layout.py holds
 * the same three indices and fails if they ever name different slots.
 *
 * Note that pfnPresentCb is in this table and is *not* one of the three.  The
 * driver does call a pfnPresentCb, but it is the DXGI table's, reached through
 * m_pDXGICallbacks in src/present.cpp; that belongs to the DXGI DDI interop
 * group.  Reading the name alone would put a signature on the wrong slot.
 *
 * The two documentation surfaces disagree here, and the disagreement is
 * recorded rather than resolved by picking one: the rendered syntax block
 * gives 66 members and the markdown mirror 65, the odd one being
 * pfnCreateNativeFenceCb, a WDDM 3.1 addition the mirror has not caught up
 * with.  The superset is declared.  See docs/D3D11ON12.md, under Decisions and
 * rejected alternatives, for why over-declaring is the safe direction for a
 * structure the host allocates.  What makes the disagreement tolerable is that
 * it is confined to the tail: slots 10, 54 and 55 sit at the same offsets
 * under both surfaces.
 *
 * pfnEscapeCb's first parameter is documented as hAdapter, but the driver
 * passes a null and puts the real handle in D3DDDICB_ESCAPE.hDevice.  A host
 * that validated that argument would reject every call the driver makes.
 *
 * The two sync-token slots must share one type, and share it by name.  The
 * driver does not call them through the table directly; it stores
 * "PFND3DDDI_SYNCTOKENCB D3DDDI_DEVICECALLBACKS::* const m_pCallback" and
 * binds it to one or the other.  A pointer-to-member needs the structure to be
 * a complete type in C++ and needs both members to have exactly that type, not
 * merely a compatible function-pointer type, so this is a constraint no offset
 * assertion can express.  tests/d3d11ddilayout.c reproduces the construct.
 *
 * D3DDDI_EXECUTIONSTATEESCAPE is deliberately absent.  The driver builds one
 * by value and passes its sizeof as PrivateDriverDataSize, but it has no
 * public reference page on either surface and no definition in the pinned
 * WineCX, so rule 1 forbids authoring it and no placeholder substitutes for a
 * type used by value.  Device::ReportError therefore does not compile yet.
 * That is a port dependency rather than a gap in this table, and
 * docs/CLEANROOM-DDI.md records it as an open question.
 */

/*
 * The escape flags, deliberately not named D3DDDI_ESCAPEFLAGS.
 *
 * The pinned WineCX does define that name, in include/d3dukmdt.h, as the
 * oldest published variant: HardwareAccess and 31 reserved bits, with no
 * DeviceStatusQuery.  DeviceStatusQuery is the one bit the driver sets.  The
 * host is Wine's D3D11 frontend and will include both that header and this
 * one, so declaring our own under the same name is a duplicate typedef and
 * deferring to Wine's is a missing member.  A distinct name is neither: the
 * layout is identical, and the driver never spells the type, only
 * EscapeCB.Flags.DeviceStatusQuery.
 *
 * The specification prints this structure with the later bits behind #if
 * ellipses, so which of them exist is version-dependent and unpublished.  The
 * four leading bits and Reserved : 28 are one of the printed variants
 * verbatim, not a blend of them.  Value aliases the whole word, so the size is
 * four bytes under every variant and only the bit positions could differ;
 * tests/d3d11ddilayout.c pins the two this port depends on.
 */
typedef struct WINE_D3D11DDI_ESCAPEFLAGS
{
    union
    {
        struct
        {
            UINT HardwareAccess : 1;
            UINT DeviceStatusQuery : 1;
            UINT ChangeFrameLatency : 1;
            UINT NoAdapterSynchronization : 1;
            UINT Reserved : 28;
        };
        UINT Value;
    };
} WINE_D3D11DDI_ESCAPEFLAGS;

WINE_DDI_ASSERT_SIZE(WINE_D3D11DDI_ESCAPEFLAGS, 4);
WINE_DDI_ASSERT_ALIGN(WINE_D3D11DDI_ESCAPEFLAGS, 4);
WINE_DDI_ASSERT_FIELD(WINE_D3D11DDI_ESCAPEFLAGS, Value, 0);

/* Both argument structures carry interior padding, so a host that assigns
 * member by member leaves the driver reading uninitialized bytes.  Zero the
 * whole structure, as D3D10DDIARG_CREATEDEVICE also requires. */
typedef struct _D3DDDICB_ESCAPE
{
    HANDLE                    hDevice;
    WINE_D3D11DDI_ESCAPEFLAGS Flags;
    void                      *pPrivateDriverData;
    UINT                      PrivateDriverDataSize;
    HANDLE                    hContext;
} D3DDDICB_ESCAPE;

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3DDDICB_ESCAPE);
WINE_DDI_ASSERT_SIZE(D3DDDICB_ESCAPE, 40);
WINE_DDI_ASSERT_ALIGN(D3DDDICB_ESCAPE, 8);
WINE_DDI_ASSERT_FIELD(D3DDDICB_ESCAPE, hDevice, 0);
WINE_DDI_ASSERT_FIELD(D3DDDICB_ESCAPE, Flags, 8);
WINE_DDI_ASSERT_FIELD_SIZE(D3DDDICB_ESCAPE, Flags, 4);
/* Four bytes of padding follow Flags, and four more follow
 * PrivateDriverDataSize; no member names either. */
WINE_DDI_ASSERT_FIELD(D3DDDICB_ESCAPE, pPrivateDriverData, 16);
WINE_DDI_ASSERT_FIELD(D3DDDICB_ESCAPE, PrivateDriverDataSize, 24);
WINE_DDI_ASSERT_FIELD_SIZE(D3DDDICB_ESCAPE, PrivateDriverDataSize, 4);
WINE_DDI_ASSERT_FIELD(D3DDDICB_ESCAPE, hContext, 32);

typedef struct _D3DDDICB_SYNCTOKEN
{
    HANDLE       hSyncToken;
    UINT         BroadcastContextCount;
    const HANDLE *BroadcastContextArray;
} D3DDDICB_SYNCTOKEN;

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3DDDICB_SYNCTOKEN);
WINE_DDI_ASSERT_SIZE(D3DDDICB_SYNCTOKEN, 24);
WINE_DDI_ASSERT_ALIGN(D3DDDICB_SYNCTOKEN, 8);
WINE_DDI_ASSERT_FIELD(D3DDDICB_SYNCTOKEN, hSyncToken, 0);
WINE_DDI_ASSERT_FIELD(D3DDDICB_SYNCTOKEN, BroadcastContextCount, 8);
WINE_DDI_ASSERT_FIELD_SIZE(D3DDDICB_SYNCTOKEN, BroadcastContextCount, 4);
WINE_DDI_ASSERT_FIELD(D3DDDICB_SYNCTOKEN, BroadcastContextArray, 16);

/* The three promoted signatures: the slots the pinned driver invokes. */
typedef HRESULT (*PFND3DDDI_ESCAPECB)(
        HANDLE hAdapter,
        const D3DDDICB_ESCAPE *pData);

typedef HRESULT (*PFND3DDDI_SYNCTOKENCB)(
        HANDLE hDevice,
        const D3DDDICB_SYNCTOKEN *pData);

/* The 63 slots the driver never reads.  Each keeps its published type name so
 * the structure below reads as the specification prints it, and each is an
 * alias of the undeclared-slot type so that reading one here is unambiguous
 * about what has and has not been derived from a specification. */
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_ALLOCATECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_DEALLOCATECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_SETPRIORITYCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_QUERYRESIDENCYCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_SETDISPLAYMODECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_PRESENTCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_RENDERCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_LOCKCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_UNLOCKCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_CREATEOVERLAYCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_UPDATEOVERLAYCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_FLIPOVERLAYCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_DESTROYOVERLAYCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_CREATECONTEXTCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_DESTROYCONTEXTCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_CREATESYNCHRONIZATIONOBJECTCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_DESTROYSYNCHRONIZATIONOBJECTCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_WAITFORSYNCHRONIZATIONOBJECTCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_SIGNALSYNCHRONIZATIONOBJECTCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_SETASYNCCALLBACKSCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_SETDISPLAYPRIVATEDRIVERFORMATCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_OFFERALLOCATIONSCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_RECLAIMALLOCATIONSCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_CREATESYNCHRONIZATIONOBJECT2CB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_WAITFORSYNCHRONIZATIONOBJECT2CB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_SIGNALSYNCHRONIZATIONOBJECT2CB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_PRESENTMULTIPLANEOVERLAYCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_LOGUMDMARKERCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_MAKERESIDENTCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_EVICTCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_WAITFORSYNCHRONIZATIONOBJECTFROMCPUCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_SIGNALSYNCHRONIZATIONOBJECTFROMCPUCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_WAITFORSYNCHRONIZATIONOBJECTFROMGPUCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_SIGNALSYNCHRONIZATIONOBJECTFROMGPUCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_CREATEPAGINGQUEUECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_DESTROYPAGINGQUEUECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_LOCK2CB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_UNLOCK2CB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_INVALIDATECACHECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_RESERVEGPUVIRTUALADDRESSCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_MAPGPUVIRTUALADDRESSCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_FREEGPUVIRTUALADDRESSCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_UPDATEGPUVIRTUALADDRESSCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_CREATECONTEXTVIRTUALCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_SUBMITCOMMANDCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_DEALLOCATE2CB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_SIGNALSYNCHRONIZATIONOBJECTFROMGPU2CB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_RECLAIMALLOCATIONS2CB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_GETRESOURCEPRESENTPRIVATEDRIVERDATACB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_UPDATEALLOCATIONPROPERTYCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_OFFERALLOCATIONS2CB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_RECLAIMALLOCATIONS3CB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_CREATEHWCONTEXTCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_DESTROYHWCONTEXTCB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_CREATEHWQUEUECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_DESTROYHWQUEUECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_SUBMITCOMMANDTOHWQUEUECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_SUBMITWAITFORSYNCOBJECTSTOHWQUEUECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB
        PFND3DDDI_SUBMITSIGNALSYNCOBJECTSTOHWQUEUECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_SUBMITPRESENTBLTTOHWQUEUECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_SUBMITPRESENTTOHWQUEUECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_SUBMITHISTORYSEQUENCECB;
typedef PFNWINE_D3D11DDI_UNDECLARED_CB PFND3DDDI_CREATENATIVEFENCECB;

struct _D3DDDI_DEVICECALLBACKS
{
    PFND3DDDI_ALLOCATECB                            pfnAllocateCb;
    PFND3DDDI_DEALLOCATECB                          pfnDeallocateCb;
    PFND3DDDI_SETPRIORITYCB                         pfnSetPriorityCb;
    PFND3DDDI_QUERYRESIDENCYCB                      pfnQueryResidencyCb;
    PFND3DDDI_SETDISPLAYMODECB                      pfnSetDisplayModeCb;
    PFND3DDDI_PRESENTCB                             pfnPresentCb;
    PFND3DDDI_RENDERCB                              pfnRenderCb;
    PFND3DDDI_LOCKCB                                pfnLockCb;
    PFND3DDDI_UNLOCKCB                              pfnUnlockCb;
    PFND3DDDI_ESCAPECB                              pfnEscapeCb;
    PFND3DDDI_CREATEOVERLAYCB                       pfnCreateOverlayCb;
    PFND3DDDI_UPDATEOVERLAYCB                       pfnUpdateOverlayCb;
    PFND3DDDI_FLIPOVERLAYCB                         pfnFlipOverlayCb;
    PFND3DDDI_DESTROYOVERLAYCB                      pfnDestroyOverlayCb;
    PFND3DDDI_CREATECONTEXTCB                       pfnCreateContextCb;
    PFND3DDDI_DESTROYCONTEXTCB                      pfnDestroyContextCb;
    PFND3DDDI_CREATESYNCHRONIZATIONOBJECTCB         pfnCreateSynchronizationObjectCb;
    PFND3DDDI_DESTROYSYNCHRONIZATIONOBJECTCB        pfnDestroySynchronizationObjectCb;
    PFND3DDDI_WAITFORSYNCHRONIZATIONOBJECTCB        pfnWaitForSynchronizationObjectCb;
    PFND3DDDI_SIGNALSYNCHRONIZATIONOBJECTCB         pfnSignalSynchronizationObjectCb;
    PFND3DDDI_SETASYNCCALLBACKSCB                   pfnSetAsyncCallbacksCb;
    PFND3DDDI_SETDISPLAYPRIVATEDRIVERFORMATCB       pfnSetDisplayPrivateDriverFormatCb;
    PFND3DDDI_OFFERALLOCATIONSCB                    pfnOfferAllocationsCb;
    PFND3DDDI_RECLAIMALLOCATIONSCB                  pfnReclaimAllocationsCb;
    PFND3DDDI_CREATESYNCHRONIZATIONOBJECT2CB        pfnCreateSynchronizationObject2Cb;
    PFND3DDDI_WAITFORSYNCHRONIZATIONOBJECT2CB       pfnWaitForSynchronizationObject2Cb;
    PFND3DDDI_SIGNALSYNCHRONIZATIONOBJECT2CB        pfnSignalSynchronizationObject2Cb;
    PFND3DDDI_PRESENTMULTIPLANEOVERLAYCB            pfnPresentMultiPlaneOverlayCb;
    PFND3DDDI_LOGUMDMARKERCB                        pfnLogUMDMarkerCb;
    PFND3DDDI_MAKERESIDENTCB                        pfnMakeResidentCb;
    PFND3DDDI_EVICTCB                               pfnEvictCb;
    PFND3DDDI_WAITFORSYNCHRONIZATIONOBJECTFROMCPUCB pfnWaitForSynchronizationObjectFromCpuCb;
    PFND3DDDI_SIGNALSYNCHRONIZATIONOBJECTFROMCPUCB  pfnSignalSynchronizationObjectFromCpuCb;
    PFND3DDDI_WAITFORSYNCHRONIZATIONOBJECTFROMGPUCB pfnWaitForSynchronizationObjectFromGpuCb;
    PFND3DDDI_SIGNALSYNCHRONIZATIONOBJECTFROMGPUCB  pfnSignalSynchronizationObjectFromGpuCb;
    PFND3DDDI_CREATEPAGINGQUEUECB                   pfnCreatePagingQueueCb;
    PFND3DDDI_DESTROYPAGINGQUEUECB                  pfnDestroyPagingQueueCb;
    PFND3DDDI_LOCK2CB                               pfnLock2Cb;
    PFND3DDDI_UNLOCK2CB                             pfnUnlock2Cb;
    PFND3DDDI_INVALIDATECACHECB                     pfnInvalidateCacheCb;
    PFND3DDDI_RESERVEGPUVIRTUALADDRESSCB            pfnReserveGpuVirtualAddressCb;
    PFND3DDDI_MAPGPUVIRTUALADDRESSCB                pfnMapGpuVirtualAddressCb;
    PFND3DDDI_FREEGPUVIRTUALADDRESSCB               pfnFreeGpuVirtualAddressCb;
    PFND3DDDI_UPDATEGPUVIRTUALADDRESSCB             pfnUpdateGpuVirtualAddressCb;
    PFND3DDDI_CREATECONTEXTVIRTUALCB                pfnCreateContextVirtualCb;
    PFND3DDDI_SUBMITCOMMANDCB                       pfnSubmitCommandCb;
    PFND3DDDI_DEALLOCATE2CB                         pfnDeallocate2Cb;
    PFND3DDDI_SIGNALSYNCHRONIZATIONOBJECTFROMGPU2CB pfnSignalSynchronizationObjectFromGpu2Cb;
    PFND3DDDI_RECLAIMALLOCATIONS2CB                 pfnReclaimAllocations2Cb;
    PFND3DDDI_GETRESOURCEPRESENTPRIVATEDRIVERDATACB pfnGetResourcePresentPrivateDriverDataCb;
    PFND3DDDI_UPDATEALLOCATIONPROPERTYCB            pfnUpdateAllocationPropertyCb;
    PFND3DDDI_OFFERALLOCATIONS2CB                   pfnOfferAllocations2Cb;
    PFND3DDDI_RECLAIMALLOCATIONS3CB                 pfnReclaimAllocations3Cb;
    PFND3DDDI_SYNCTOKENCB                           pfnAcquireResourceCb;
    PFND3DDDI_SYNCTOKENCB                           pfnReleaseResourceCb;
    PFND3DDDI_CREATEHWCONTEXTCB                     pfnCreateHwContextCb;
    PFND3DDDI_DESTROYHWCONTEXTCB                    pfnDestroyHwContextCb;
    PFND3DDDI_CREATEHWQUEUECB                       pfnCreateHwQueueCb;
    PFND3DDDI_DESTROYHWQUEUECB                      pfnDestroyHwQueueCb;
    PFND3DDDI_SUBMITCOMMANDTOHWQUEUECB              pfnSubmitCommandToHwQueueCb;
    PFND3DDDI_SUBMITWAITFORSYNCOBJECTSTOHWQUEUECB   pfnSubmitWaitForSyncObjectsToHwQueueCb;
    PFND3DDDI_SUBMITSIGNALSYNCOBJECTSTOHWQUEUECB    pfnSubmitSignalSyncObjectsToHwQueueCb;
    PFND3DDDI_SUBMITPRESENTBLTTOHWQUEUECB           pfnSubmitPresentBltToHwQueueCb;
    PFND3DDDI_SUBMITPRESENTTOHWQUEUECB              pfnSubmitPresentToHwQueueCb;
    PFND3DDDI_SUBMITHISTORYSEQUENCECB               pfnSubmitHistorySequenceCb;
    PFND3DDDI_CREATENATIVEFENCECB                   pfnCreateNativeFenceCb;
};

WINE_DDI_ASSERT_STANDARD_LAYOUT(D3DDDI_DEVICECALLBACKS);
WINE_DDI_ASSERT_SIZE(D3DDDI_DEVICECALLBACKS, 528);
WINE_DDI_ASSERT_ALIGN(D3DDDI_DEVICECALLBACKS, 8);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnAllocateCb, 0);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnDeallocateCb, 8);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSetPriorityCb, 16);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnQueryResidencyCb, 24);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSetDisplayModeCb, 32);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnPresentCb, 40);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnRenderCb, 48);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnLockCb, 56);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnUnlockCb, 64);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnEscapeCb, 72);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnCreateOverlayCb, 80);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnUpdateOverlayCb, 88);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnFlipOverlayCb, 96);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnDestroyOverlayCb, 104);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnCreateContextCb, 112);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnDestroyContextCb, 120);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnCreateSynchronizationObjectCb, 128);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnDestroySynchronizationObjectCb, 136);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnWaitForSynchronizationObjectCb, 144);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSignalSynchronizationObjectCb, 152);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSetAsyncCallbacksCb, 160);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSetDisplayPrivateDriverFormatCb, 168);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnOfferAllocationsCb, 176);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnReclaimAllocationsCb, 184);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnCreateSynchronizationObject2Cb, 192);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnWaitForSynchronizationObject2Cb, 200);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSignalSynchronizationObject2Cb, 208);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnPresentMultiPlaneOverlayCb, 216);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnLogUMDMarkerCb, 224);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnMakeResidentCb, 232);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnEvictCb, 240);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnWaitForSynchronizationObjectFromCpuCb, 248);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSignalSynchronizationObjectFromCpuCb, 256);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnWaitForSynchronizationObjectFromGpuCb, 264);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSignalSynchronizationObjectFromGpuCb, 272);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnCreatePagingQueueCb, 280);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnDestroyPagingQueueCb, 288);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnLock2Cb, 296);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnUnlock2Cb, 304);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnInvalidateCacheCb, 312);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnReserveGpuVirtualAddressCb, 320);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnMapGpuVirtualAddressCb, 328);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnFreeGpuVirtualAddressCb, 336);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnUpdateGpuVirtualAddressCb, 344);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnCreateContextVirtualCb, 352);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSubmitCommandCb, 360);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnDeallocate2Cb, 368);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSignalSynchronizationObjectFromGpu2Cb, 376);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnReclaimAllocations2Cb, 384);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnGetResourcePresentPrivateDriverDataCb, 392);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnUpdateAllocationPropertyCb, 400);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnOfferAllocations2Cb, 408);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnReclaimAllocations3Cb, 416);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnAcquireResourceCb, 424);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnReleaseResourceCb, 432);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnCreateHwContextCb, 440);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnDestroyHwContextCb, 448);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnCreateHwQueueCb, 456);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnDestroyHwQueueCb, 464);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSubmitCommandToHwQueueCb, 472);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSubmitWaitForSyncObjectsToHwQueueCb, 480);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSubmitSignalSyncObjectsToHwQueueCb, 488);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSubmitPresentBltToHwQueueCb, 496);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSubmitPresentToHwQueueCb, 504);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnSubmitHistorySequenceCb, 512);
WINE_DDI_ASSERT_FIELD(D3DDDI_DEVICECALLBACKS,
        pfnCreateNativeFenceCb, 520);

/* Every slot is a function pointer, so the table is its member count times the
 * pointer size.  Asserting that as arithmetic rather than as another literal
 * catches a member being dropped and the offsets renumbered to match, which
 * the per-field assertions above cannot see. */
WINE_DDI_STATIC_ASSERT(
        sizeof(D3DDDI_DEVICECALLBACKS) == 66 * sizeof(void (*)(void)),
        "the kernel callback table is 66 function pointers");

#endif /* WINE_D3D11DDI_H */
