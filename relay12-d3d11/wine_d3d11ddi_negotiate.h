/* SPDX-License-Identifier: GPL-3.0-only
 *
 * DDI version negotiation for the D3D11On12 host.
 *
 * This is policy, not specification, which is why it is here and not under
 * relay12-d3d11/ddi: that directory holds declarations authored from public
 * documentation, and nothing else belongs in it.  What this file encodes is
 * how the host calls one of those declarations safely and which of the
 * driver's answers it chooses.  docs/CLEANROOM-DDI.md carries the argument for
 * the choice; the reason the call needs a wrapper at all is below.
 *
 * It is header-only and static inline so the C tests and the C++ host share
 * one definition with no link step.  The DDI declarations are already proven
 * identical in both languages by tests/d3d11ddilayout.c, and this must not be
 * the thing that diverges.
 *
 * ---------------------------------------------------------------------------
 * The calling contract, which is not obvious and is not documented
 *
 * GetSupportedVersions takes _Inout_ UINT32 *puEntries and _Out_opt_ UINT64
 * *pSupportedDDIInterfaceVersions, which reads like a buffer and its size.  It
 * is not.  The pinned driver's implementation, in third_party/D3D11On12
 * src/adapter.cpp, is:
 *
 *     *pNumVersions = _countof(SupportedVersions);
 *     if (pSupportedVersions)
 *         std::copy(SupportedVersions, std::end(SupportedVersions),
 *                 pSupportedVersions);
 *
 * It overwrites the count before reading it, and then writes its own number of
 * words whenever the pointer is non-null.  The value the caller passed in is
 * never examined.  So a host that treats puEntries as a capacity and hands
 * over a one-entry buffer has sixteen bytes written into it.
 *
 * The only safe sequence is therefore: call once with a null buffer to learn
 * the count, allocate at least that many words, and call again.  Both steps
 * are here so that no call site has to know this, and so the knowledge has one
 * place to be wrong.
 *
 * wineD3D11DdiSelectVersion re-probes the count itself rather than trusting
 * the capacity it was handed.  That is not redundant: the caller's probe and
 * its call are separated by an allocation, and a driver whose count grew in
 * between would overrun a buffer that was correctly sized when it was
 * measured.
 * ---------------------------------------------------------------------------
 */
#ifndef WINE_D3D11DDI_NEGOTIATE_H
#define WINE_D3D11DDI_NEGOTIATE_H

#include <dxgi.h>

#include "wine_d3d11ddi.h"

/* Ask the driver how many DDI versions it advertises, without giving it
 * anywhere to write them.
 *
 * The count is what the caller sizes its buffer from, and it is a lower bound
 * on what wineD3D11DdiSelectVersion will accept, not a promise: see the note
 * about re-probing above. */
static inline HRESULT wineD3D11DdiCountVersions(
        PFND3D10_2DDI_GETSUPPORTEDVERSIONS getSupportedVersions,
        D3D10DDI_HADAPTER adapter, UINT32 *count)
{
    UINT32 reported = 0;
    HRESULT hr;

    if (!count)
        return E_INVALIDARG;
    *count = 0;
    if (!getSupportedVersions)
        return E_INVALIDARG;

    hr = getSupportedVersions(adapter, &reported, NULL);
    if (FAILED(hr))
        return hr;

    *count = reported;
    return hr;
}

/* Choose the DDI version to negotiate, out of what the driver advertises.
 *
 * words/capacity is caller-owned storage of at least the count
 * wineD3D11DdiCountVersions reported.  On success selectedWord is the
 * advertised supported-version word and selectedInterfaceVersion is its high
 * 32 bits, which is what goes into D3D10DDIARG_CREATEDEVICE.Interface.
 *
 * The rule is the numerically highest word whose interface version carries
 * major version 11.  Filtering comes before ordering deliberately: a word for
 * some other major version could be numerically larger, and selecting it would
 * negotiate a DDI this host does not implement.  Within major version 11 the
 * ordering stands in for naming, because the minor and build literals are not
 * publicly specified -- an ordering argument, not an identification, so the
 * host must still validate the device it gets back.
 *
 * Returns:
 *   S_OK                      a version was selected
 *   DXGI_ERROR_UNSUPPORTED    nothing advertised, or nothing for major 11
 *   ERROR_INSUFFICIENT_BUFFER as an HRESULT: the buffer is smaller than the
 *                             count the driver reports now, so the driver was
 *                             not called with it
 *   E_UNEXPECTED              the driver's two answers disagree on the count
 *   anything else             the driver's own failure, propagated verbatim
 */
static inline HRESULT wineD3D11DdiSelectVersion(
        PFND3D10_2DDI_GETSUPPORTEDVERSIONS getSupportedVersions,
        D3D10DDI_HADAPTER adapter, UINT64 *words, UINT32 capacity,
        UINT64 *selectedWord, UINT *selectedInterfaceVersion)
{
    UINT32 reported = 0;
    UINT32 written = 0;
    UINT32 index;
    UINT64 best = 0;
    int found = 0;
    HRESULT hr;

    /* Before anything can fail, and before any argument is trusted. */
    if (selectedWord)
        *selectedWord = 0;
    if (selectedInterfaceVersion)
        *selectedInterfaceVersion = 0;

    if (!getSupportedVersions || !words || !capacity || !selectedWord
            || !selectedInterfaceVersion)
        return E_INVALIDARG;

    hr = getSupportedVersions(adapter, &reported, NULL);
    if (FAILED(hr))
        return hr;
    if (!reported)
        return DXGI_ERROR_UNSUPPORTED;

    /* The refusal that matters.  The driver is about to write its own count of
     * words into this buffer regardless of what it is told, so if the buffer
     * cannot hold that many it must not be shown to the driver at all. */
    if (reported > capacity)
        return HRESULT_FROM_WIN32(ERROR_INSUFFICIENT_BUFFER);

    written = reported;
    hr = getSupportedVersions(adapter, &written, words);
    if (FAILED(hr))
        return hr;

    /* A driver that now reports a different count than it did a moment ago has
     * already written an unknown number of words, so this cannot undo the
     * damage -- but continuing would compound it by reading words that were
     * never written.  Fail closed and do not guess which answer was true. */
    if (written != reported)
        return E_UNEXPECTED;

    for (index = 0; index < reported; ++index)
    {
        const UINT interfaceVersion =
                WINE_D3D11_DDI_INTERFACE_FROM_SUPPORTED(words[index]);

        if (WINE_D3D11_DDI_MAJOR_FROM_INTERFACE(interfaceVersion)
                != D3D11_DDI_MAJOR_VERSION)
            continue;

        if (!found || words[index] > best)
        {
            best = words[index];
            found = 1;
        }
    }

    if (!found)
        return DXGI_ERROR_UNSUPPORTED;

    *selectedWord = best;
    *selectedInterfaceVersion = WINE_D3D11_DDI_INTERFACE_FROM_SUPPORTED(best);
    return S_OK;
}

#endif /* WINE_D3D11DDI_NEGOTIATE_H */
