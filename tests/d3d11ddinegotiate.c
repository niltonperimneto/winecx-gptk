/* SPDX-License-Identifier: GPL-3.0-only
 *
 * Edge cases of DDI version negotiation.
 *
 * GetSupportedVersions is the first DDI call the host makes and the only one
 * where getting it wrong writes into memory rather than returning an error.
 * The pinned driver overwrites the caller's count before reading it and then
 * writes its own number of words whenever the buffer pointer is non-null, so
 * the count is not a capacity and a host that treats it as one is overrun.
 * relay12-d3d11/wine_d3d11ddi_negotiate.h exists to make that impossible; this
 * proves it.
 *
 * Every case runs against a buffer with a canary word past the end.  A test
 * that only checked the returned HRESULT would pass just as happily while the
 * driver scribbled past the buffer, which is the failure this file is about.
 * The mocks never actually write out of bounds -- that would be undefined
 * behavior in the test itself.  What is asserted instead is that the wrapper
 * refuses to show the driver a buffer it could overrun, and that it does so
 * before the driver is called at all.
 *
 * The mock carries its state through D3D10DDI_HADAPTER.pDrvPrivate, which is
 * what that handle is for.
 *
 * Build (both languages must succeed):
 *   x86_64-w64-mingw32-gcc -std=gnu11 -O2 -Wall -Wextra -Werror \
 *       -Irelay12-d3d11 -Irelay12-d3d11/ddi -o d3d11ddinegotiate.exe \
 *       tests/d3d11ddinegotiate.c
 *   x86_64-w64-mingw32-g++ -std=c++17 -O2 -Wall -Wextra -Werror \
 *       -Irelay12-d3d11 -Irelay12-d3d11/ddi -x c++ -o d3d11ddinegotiatexx.exe \
 *       tests/d3d11ddinegotiate.c
 */
#include <stdio.h>
#include <string.h>

#include "wine_d3d11ddi_negotiate.h"

static int failures;

static void fail(const char *test, const char *detail)
{
    printf("[fail] %s: %s\n", test, detail);
    ++failures;
}

static void pass(const char *test)
{
    printf("[ ok ] %s\n", test);
}

static void check_hr(const char *test, HRESULT got, HRESULT expected)
{
    if (got == expected)
    {
        pass(test);
        return;
    }
    printf("[fail] %s: got 0x%08lx, expected 0x%08lx\n", test,
            (unsigned long)got, (unsigned long)expected);
    ++failures;
}

/* An interface version for a major version other than 11.  The header's
 * composition macro hardcodes 11, correctly -- this is the test's own, so the
 * major-version filter can be given something to reject. */
#define TEST_INTERFACE_VERSION(major, minor) \
    ((UINT)((((UINT)(major)) << 16) | ((UINT)(minor))))

/* Arbitrary minor and build numbers.  The real ones are not publicly
 * specified, and nothing here depends on their values -- only on their
 * ordering, which is what the selection rule uses. */
#define TEST_WORD(minor, build) \
    WINE_D3D11_DDI_SUPPORTED(WINE_D3D11_DDI_INTERFACE_VERSION(minor), build)

#define TEST_CANARY 0xfeedfacecafebeefULL

struct mock_adapter
{
    const UINT64 *versions;
    /* What the probe reports, and what the fill call writes. */
    UINT32 count;
    /* What the fill call reports, when it disagrees with the probe.  Zero
     * means "the same", which is what a well-behaved driver does. */
    UINT32 disagreed_count;
    HRESULT probe_hr;
    HRESULT fill_hr;
    unsigned int probe_calls;
    unsigned int fill_calls;
};

static void mock_adapter_init(struct mock_adapter *mock,
        const UINT64 *versions, UINT32 count)
{
    memset(mock, 0, sizeof(*mock));
    mock->versions = versions;
    mock->count = count;
    mock->probe_hr = S_OK;
    mock->fill_hr = S_OK;
}

static D3D10DDI_HADAPTER mock_handle(struct mock_adapter *mock)
{
    D3D10DDI_HADAPTER handle;

    handle.pDrvPrivate = mock;
    return handle;
}

/* The pinned driver, reproduced: the count is overwritten before it is read,
 * and the words are copied whenever the pointer is non-null. */
static HRESULT mock_get_supported_versions(D3D10DDI_HADAPTER handle,
        UINT32 *entries, UINT64 *versions)
{
    struct mock_adapter *mock = (struct mock_adapter *)handle.pDrvPrivate;
    UINT32 index;

    if (!entries)
        return E_INVALIDARG;

    if (!versions)
    {
        ++mock->probe_calls;
        *entries = mock->count;
        return mock->probe_hr;
    }

    ++mock->fill_calls;
    /* The incoming count is deliberately not read.  That is the driver's
     * actual behavior, so a wrapper that relied on it being honoured as a
     * capacity would pass a friendlier mock and overrun the real thing. */
    *entries = mock->disagreed_count ? mock->disagreed_count : mock->count;
    if (FAILED(mock->fill_hr))
        return mock->fill_hr;

    for (index = 0; index < mock->count; ++index)
        versions[index] = mock->versions[index];
    return mock->fill_hr;
}

struct selection
{
    UINT64 buffer[3];
    UINT64 selectedWord;
    UINT selectedInterfaceVersion;
};

static void selection_init(struct selection *out)
{
    memset(out, 0, sizeof(*out));
    /* Two usable words and a canary.  Capacity is always passed as 2. */
    out->buffer[2] = TEST_CANARY;
    out->selectedWord = TEST_CANARY;
    out->selectedInterfaceVersion = 0xffffffffu;
}

#define TEST_CAPACITY 2u

static HRESULT call_select(struct mock_adapter *mock, struct selection *out,
        UINT32 capacity)
{
    return wineD3D11DdiSelectVersion(mock_get_supported_versions,
            mock_handle(mock), out->buffer, capacity, &out->selectedWord,
            &out->selectedInterfaceVersion);
}

static void check_canary(const char *test, const struct selection *out)
{
    if (out->buffer[2] != TEST_CANARY)
        fail(test, "the driver wrote past the end of the buffer");
}

static void check_cleared(const char *test, const struct selection *out)
{
    if (out->selectedWord != 0 || out->selectedInterfaceVersion != 0)
        fail(test, "the outputs were not initialized before returning");
}

static void check_untouched(const char *test, const struct selection *out)
{
    if (out->buffer[0] != 0 || out->buffer[1] != 0)
        fail(test, "the buffer was written on a path that must not call the "
                "driver");
}

static void check_calls(const char *test, const struct mock_adapter *mock,
        unsigned int probes, unsigned int fills)
{
    if (mock->probe_calls == probes && mock->fill_calls == fills)
        return;

    printf("[fail] %s: %u probe and %u fill calls, expected %u and %u\n",
            test, mock->probe_calls, mock->fill_calls, probes, fills);
    ++failures;
}

/* The advertised pair, in the shape the pinned driver advertises it: two
 * words, the later version numerically larger. */
static const UINT64 two_versions[] = { TEST_WORD(6, 3), TEST_WORD(7, 1) };

static void test_selects_the_highest(void)
{
    static const char *const test = "the highest advertised word is selected";
    struct mock_adapter mock;
    struct selection out;
    HRESULT hr;

    mock_adapter_init(&mock, two_versions, 2);
    selection_init(&out);

    hr = call_select(&mock, &out, TEST_CAPACITY);
    check_hr(test, hr, S_OK);
    check_canary(test, &out);
    check_calls(test, &mock, 1, 1);
    if (out.selectedWord != TEST_WORD(7, 1))
        fail(test, "the lower advertised word was selected");
    if (out.selectedInterfaceVersion
            != WINE_D3D11_DDI_INTERFACE_VERSION(7))
        fail(test, "the reported interface version is not the selected word's "
                "high 32 bits");
}

static void test_order_is_by_value_not_position(void)
{
    static const char *const test = "the highest word is selected first or "
            "last";
    static const UINT64 descending[] = { TEST_WORD(7, 1), TEST_WORD(6, 3) };
    struct mock_adapter mock;
    struct selection out;

    mock_adapter_init(&mock, descending, 2);
    selection_init(&out);

    check_hr(test, call_select(&mock, &out, TEST_CAPACITY), S_OK);
    check_canary(test, &out);
    if (out.selectedWord != TEST_WORD(7, 1))
        fail(test, "the selection depended on the advertised order");
}

/* The case this file exists for. */
static void test_refuses_a_buffer_it_could_overrun(void)
{
    static const char *const test = "a buffer smaller than the driver's count "
            "is refused";
    struct mock_adapter mock;
    struct selection out;
    HRESULT hr;

    mock_adapter_init(&mock, two_versions, 2);
    selection_init(&out);

    hr = call_select(&mock, &out, 1);
    check_hr(test, hr, HRESULT_FROM_WIN32(ERROR_INSUFFICIENT_BUFFER));
    check_canary(test, &out);
    check_cleared(test, &out);
    check_untouched(test, &out);
    /* The refusal has to come before the driver sees the buffer.  Refusing
     * afterwards would report an error about memory that was already
     * written. */
    check_calls(test, &mock, 1, 0);
}

static void test_refuses_a_count_that_grew(void)
{
    static const char *const test = "a count that grew after the caller sized "
            "its buffer is refused";
    struct mock_adapter mock;
    struct selection out;
    UINT32 counted = 0;
    HRESULT hr;

    /* The realistic sequence: the caller counts, allocates for that count,
     * and calls.  Between the two the driver's answer changes. */
    mock_adapter_init(&mock, two_versions, 1);
    selection_init(&out);

    hr = wineD3D11DdiCountVersions(mock_get_supported_versions,
            mock_handle(&mock), &counted);
    check_hr("counting the advertised versions", hr, S_OK);
    if (counted != 1)
        fail("counting the advertised versions", "the reported count was not "
                "returned");

    mock.count = 2;
    hr = call_select(&mock, &out, counted);
    check_hr(test, hr, HRESULT_FROM_WIN32(ERROR_INSUFFICIENT_BUFFER));
    check_canary(test, &out);
    check_untouched(test, &out);
    check_calls(test, &mock, 2, 0);
}

static void test_no_versions_advertised(void)
{
    static const char *const test = "a driver advertising no versions is "
            "unsupported";
    struct mock_adapter mock;
    struct selection out;

    mock_adapter_init(&mock, two_versions, 0);
    selection_init(&out);

    check_hr(test, call_select(&mock, &out, TEST_CAPACITY),
            DXGI_ERROR_UNSUPPORTED);
    check_canary(test, &out);
    check_cleared(test, &out);
    check_untouched(test, &out);
    check_calls(test, &mock, 1, 0);
}

static void test_driver_failures_are_propagated(void)
{
    static const char *const probe = "a failed probe is propagated";
    static const char *const fill = "a failed fill is propagated";
    struct mock_adapter mock;
    struct selection out;

    /* A failing probe that still writes a count, and a preposterous one.  The
     * wrapper must not use a count it was given alongside a failure. */
    mock_adapter_init(&mock, two_versions, 0xffffffffu);
    mock.probe_hr = E_FAIL;
    selection_init(&out);

    check_hr(probe, call_select(&mock, &out, TEST_CAPACITY), E_FAIL);
    check_canary(probe, &out);
    check_cleared(probe, &out);
    check_untouched(probe, &out);
    check_calls(probe, &mock, 1, 0);

    mock_adapter_init(&mock, two_versions, 2);
    mock.fill_hr = E_OUTOFMEMORY;
    selection_init(&out);

    check_hr(fill, call_select(&mock, &out, TEST_CAPACITY), E_OUTOFMEMORY);
    check_canary(fill, &out);
    check_cleared(fill, &out);
    check_calls(fill, &mock, 1, 1);
}

static void test_inconsistent_counts(void)
{
    static const char *const test = "a driver whose two answers disagree is "
            "refused";
    struct mock_adapter mock;
    struct selection out;

    mock_adapter_init(&mock, two_versions, 2);
    mock.disagreed_count = 1;
    selection_init(&out);

    check_hr(test, call_select(&mock, &out, TEST_CAPACITY), E_UNEXPECTED);
    check_canary(test, &out);
    check_cleared(test, &out);
    check_calls(test, &mock, 1, 1);
}

static void test_single_and_duplicate_words(void)
{
    static const char *const single = "a single advertised version is selected";
    static const char *const duplicate = "duplicate advertised versions are "
            "selected once";
    static const UINT64 duplicated[] = { TEST_WORD(6, 3), TEST_WORD(6, 3) };
    struct mock_adapter mock;
    struct selection out;

    mock_adapter_init(&mock, two_versions, 1);
    selection_init(&out);
    check_hr(single, call_select(&mock, &out, TEST_CAPACITY), S_OK);
    check_canary(single, &out);
    if (out.selectedWord != TEST_WORD(6, 3))
        fail(single, "the only advertised word was not selected");

    mock_adapter_init(&mock, duplicated, 2);
    selection_init(&out);
    check_hr(duplicate, call_select(&mock, &out, TEST_CAPACITY), S_OK);
    check_canary(duplicate, &out);
    if (out.selectedWord != TEST_WORD(6, 3))
        fail(duplicate, "a duplicated word was not selected");
}

static void test_major_version_filter(void)
{
    static const char *const none = "a driver advertising no D3D11 version is "
            "unsupported";
    static const char *const mixed = "a numerically higher word for another "
            "major version does not win";
    static const UINT64 foreign[] =
    {
        WINE_D3D11_DDI_SUPPORTED(TEST_INTERFACE_VERSION(10, 1), 1),
        WINE_D3D11_DDI_SUPPORTED(TEST_INTERFACE_VERSION(12, 0), 1),
    };
    static const UINT64 straddling[] =
    {
        TEST_WORD(7, 1),
        WINE_D3D11_DDI_SUPPORTED(TEST_INTERFACE_VERSION(12, 0), 1),
    };
    struct mock_adapter mock;
    struct selection out;

    mock_adapter_init(&mock, foreign, 2);
    selection_init(&out);
    check_hr(none, call_select(&mock, &out, TEST_CAPACITY),
            DXGI_ERROR_UNSUPPORTED);
    check_canary(none, &out);
    check_cleared(none, &out);

    /* Filtering before ordering is the whole point: the major-12 word is the
     * larger number, and selecting it would negotiate a DDI this host does not
     * implement. */
    mock_adapter_init(&mock, straddling, 2);
    selection_init(&out);
    check_hr(mixed, call_select(&mock, &out, TEST_CAPACITY), S_OK);
    check_canary(mixed, &out);
    if (out.selectedWord != TEST_WORD(7, 1))
        fail(mixed, "a word for another major version was selected");
    if (WINE_D3D11_DDI_MAJOR_FROM_INTERFACE(out.selectedInterfaceVersion)
            != D3D11_DDI_MAJOR_VERSION)
        fail(mixed, "the selected interface version is not a D3D11 one");
}

static void test_rejected_arguments(void)
{
    struct mock_adapter mock;
    struct selection out;
    UINT64 word = TEST_CANARY;
    UINT interfaceVersion = 0xffffffffu;
    UINT32 counted = 0xffffffffu;

    mock_adapter_init(&mock, two_versions, 2);
    selection_init(&out);

    check_hr("selection rejects a null entry point",
            wineD3D11DdiSelectVersion(NULL, mock_handle(&mock), out.buffer,
                    TEST_CAPACITY, &out.selectedWord,
                    &out.selectedInterfaceVersion), E_INVALIDARG);
    check_cleared("selection rejects a null entry point", &out);

    selection_init(&out);
    check_hr("selection rejects a null buffer",
            wineD3D11DdiSelectVersion(mock_get_supported_versions,
                    mock_handle(&mock), NULL, TEST_CAPACITY,
                    &out.selectedWord, &out.selectedInterfaceVersion),
            E_INVALIDARG);
    check_cleared("selection rejects a null buffer", &out);

    selection_init(&out);
    check_hr("selection rejects a zero capacity",
            call_select(&mock, &out, 0), E_INVALIDARG);
    check_cleared("selection rejects a zero capacity", &out);

    check_hr("selection rejects a null selected word",
            wineD3D11DdiSelectVersion(mock_get_supported_versions,
                    mock_handle(&mock), out.buffer, TEST_CAPACITY, NULL,
                    &interfaceVersion), E_INVALIDARG);
    if (interfaceVersion != 0)
        fail("selection rejects a null selected word",
                "the output it was given was not initialized");

    check_hr("selection rejects a null interface version",
            wineD3D11DdiSelectVersion(mock_get_supported_versions,
                    mock_handle(&mock), out.buffer, TEST_CAPACITY, &word,
                    NULL), E_INVALIDARG);
    if (word != 0)
        fail("selection rejects a null interface version",
                "the output it was given was not initialized");

    /* Nothing above may have reached the driver. */
    check_calls("rejected arguments", &mock, 0, 0);

    check_hr("counting rejects a null count",
            wineD3D11DdiCountVersions(mock_get_supported_versions,
                    mock_handle(&mock), NULL), E_INVALIDARG);
    check_hr("counting rejects a null entry point",
            wineD3D11DdiCountVersions(NULL, mock_handle(&mock), &counted),
            E_INVALIDARG);
    if (counted != 0)
        fail("counting rejects a null entry point",
                "the count was not initialized");

    mock.probe_hr = E_FAIL;
    counted = 0xffffffffu;
    check_hr("counting propagates a failed probe",
            wineD3D11DdiCountVersions(mock_get_supported_versions,
                    mock_handle(&mock), &counted), E_FAIL);
    if (counted != 0)
        fail("counting propagates a failed probe",
                "a count was reported alongside a failure");
}

int main(void)
{
    test_selects_the_highest();
    test_order_is_by_value_not_position();
    test_refuses_a_buffer_it_could_overrun();
    test_refuses_a_count_that_grew();
    test_no_versions_advertised();
    test_driver_failures_are_propagated();
    test_inconsistent_counts();
    test_single_and_duplicate_words();
    test_major_version_filter();
    test_rejected_arguments();

    if (failures)
    {
        printf("RESULT: %d DDI negotiation failure(s)\n", failures);
        return 1;
    }
    printf("RESULT: DDI version negotiation holds, including the buffer "
            "contract\n");
    return 0;
}
