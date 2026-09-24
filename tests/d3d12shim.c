/* Behaviour of gptk-video/d3d12shim.dll against a recording D3DMetal.
 *
 * d3d12shim_mock.c is built as d3dmt.dll beside this test, so the shim, loaded
 * here as d3d12shim.dll, forwards to it. Each check states what the shim must
 * do and is given the input that would break it:
 *
 *  - D3D12_FEATURE_D3D12_TIGHT_ALIGNMENT is answered "not supported" only when
 *    D3DMetal refuses it; an answer from D3DMetal, a wrong size and a null
 *    buffer all pass through untouched.
 *  - ResourceBarrier with nothing to translate hands D3DMetal the app's own
 *    array: same pointer, same count, no copy.
 *  - A translated batch keeps every barrier. The shim used to copy into 32
 *    entries and drop the rest.
 *  - CopyTextureRegion with no video texture forwards its arguments as given.
 *
 * Prints one line per check and a final "RESULT:" line, which is the verdict. */
#include <windows.h>
#include <d3d12.h>
#include <stdio.h>
#include <string.h>

typedef HRESULT (WINAPI *create_device_fn)(IUnknown *, D3D_FEATURE_LEVEL, REFIID, void **);
typedef void (WINAPI *answer_fn)(int);
typedef void **(WINAPI *vtable_fn)(void);
typedef LONG (WINAPI *unexpected_fn)(void);
typedef UINT (WINAPI *barriers_fn)(UINT *, const D3D12_RESOURCE_BARRIER **, const D3D12_RESOURCE_BARRIER **);
typedef UINT (WINAPI *copy_fn)(const D3D12_TEXTURE_COPY_LOCATION **, const D3D12_TEXTURE_COPY_LOCATION **,
        UINT *, const D3D12_BOX **);

typedef HRESULT (WINAPI *cfs_fn)(void *, D3D12_FEATURE, void *, UINT);
typedef HRESULT (WINAPI *ccl_fn)(void *, UINT, D3D12_COMMAND_LIST_TYPE, void *, void *, REFIID, void **);
typedef void (WINAPI *rb_fn)(void *, UINT, const D3D12_RESOURCE_BARRIER *);
typedef void (WINAPI *ctr_fn)(void *, const D3D12_TEXTURE_COPY_LOCATION *, UINT, UINT, UINT,
        const D3D12_TEXTURE_COPY_LOCATION *, const D3D12_BOX *);

#define TIGHT_ALIGNMENT ((D3D12_FEATURE)54)

static int failures;

#define CHECK(cond, name) do { \
        if (cond) printf("[ok] %s\n", name); \
        else { printf("[fail] %s (line %d)\n", name, __LINE__); ++failures; } \
    } while (0)

static void *slot(void *object, unsigned int index)
{
    return (*(void ***)object)[index];
}

static D3D12_RESOURCE_BARRIER transition(ID3D12Resource *resource, D3D12_RESOURCE_STATES before,
        D3D12_RESOURCE_STATES after)
{
    D3D12_RESOURCE_BARRIER barrier;

    memset(&barrier, 0, sizeof(barrier));
    barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    barrier.Transition.pResource = resource;
    barrier.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
    barrier.Transition.StateBefore = before;
    barrier.Transition.StateAfter = after;
    return barrier;
}

int main(void)
{
    static D3D12_RESOURCE_BARRIER batch[64];
    D3D12_FEATURE_DATA_FORMAT_SUPPORT format;
    const D3D12_RESOURCE_BARRIER *seen_array, *seen_copy;
    const D3D12_TEXTURE_COPY_LOCATION *seen_dst, *seen_src;
    D3D12_TEXTURE_COPY_LOCATION dst, src;
    const D3D12_BOX *seen_box;
    D3D12_BOX box = {1, 2, 0, 3, 4, 1};
    HMODULE shim, mock;
    create_device_fn create_device;
    answer_fn answer;
    vtable_fn device_vtable, list_vtable;
    unexpected_fn unexpected;
    barriers_fn barriers;
    copy_fn copies;
    ID3D12Resource *resource = (ID3D12Resource *)(UINT_PTR)0x1000;
    void *device = NULL, *list = NULL;
    UINT tier, count, calls, xyz[3], i;
    UINT64 wide;
    HRESULT hr;
    BOOL all;

    setvbuf(stdout, NULL, _IONBF, 0);
    if (!(shim = LoadLibraryA("d3d12shim.dll")) || !(mock = LoadLibraryA("d3dmt.dll")))
    {
        printf("RESULT: FAIL, could not load d3d12shim.dll and the d3dmt.dll mock (%lu)\n", GetLastError());
        return 1;
    }
    create_device = (create_device_fn)(void *)GetProcAddress(shim, "D3D12CreateDevice");
    answer = (answer_fn)(void *)GetProcAddress(mock, "MockAnswerTightAlignment");
    device_vtable = (vtable_fn)(void *)GetProcAddress(mock, "MockDeviceVtable");
    list_vtable = (vtable_fn)(void *)GetProcAddress(mock, "MockListVtable");
    unexpected = (unexpected_fn)(void *)GetProcAddress(mock, "MockUnexpectedCalls");
    barriers = (barriers_fn)(void *)GetProcAddress(mock, "MockBarriers");
    copies = (copy_fn)(void *)GetProcAddress(mock, "MockCopy");
    if (!create_device || !answer || !device_vtable || !list_vtable || !unexpected || !barriers || !copies)
    {
        printf("RESULT: FAIL, an export is missing from the shim or the mock\n");
        return 1;
    }

    hr = create_device(NULL, D3D_FEATURE_LEVEL_11_0, &IID_ID3D12Device, &device);
    CHECK(hr == S_OK && device, "D3D12CreateDevice through the shim");
    if (!device)
    {
        printf("RESULT: FAIL, no device\n");
        return 1;
    }
    CHECK(*(void ***)device != device_vtable(), "the device vtable is swapped for the shim's");

    /* ---- tight alignment ---- */
    answer(0);
    tier = 0xffffffff;
    hr = ((cfs_fn)slot(device, 13))(device, TIGHT_ALIGNMENT, &tier, sizeof(tier));
    CHECK(hr == S_OK && tier == 0, "refused tight alignment is answered as not supported");

    tier = 0xffffffff;
    hr = ((cfs_fn)slot(device, 13))(device, TIGHT_ALIGNMENT, NULL, sizeof(tier));
    CHECK(hr == E_INVALIDARG, "tight alignment with no buffer stays E_INVALIDARG");

    wide = 0xffffffffffffffffull;
    hr = ((cfs_fn)slot(device, 13))(device, TIGHT_ALIGNMENT, &wide, sizeof(wide));
    CHECK(hr == E_INVALIDARG && wide == 0xffffffffffffffffull,
            "tight alignment with a wrong size stays E_INVALIDARG and untouched");

    answer(1);
    tier = 0xffffffff;
    hr = ((cfs_fn)slot(device, 13))(device, TIGHT_ALIGNMENT, &tier, sizeof(tier));
    CHECK(hr == S_OK && tier == 1, "a D3DMetal that answers tight alignment is not overridden");
    answer(0);

    tier = 0;
    hr = ((cfs_fn)slot(device, 13))(device, D3D12_FEATURE_D3D12_OPTIONS, &tier, sizeof(tier));
    CHECK(hr == S_FALSE && tier == 0x5eed, "other features pass through with D3DMetal's result");

    memset(&format, 0, sizeof(format));
    format.Format = DXGI_FORMAT_NV12;
    hr = ((cfs_fn)slot(device, 13))(device, D3D12_FEATURE_FORMAT_SUPPORT, &format, sizeof(format));
    CHECK(hr == S_OK && (format.Support1 & D3D12_FORMAT_SUPPORT1_TEXTURE2D)
            && (format.Support1 & D3D12_FORMAT_SUPPORT1_SHADER_SAMPLE),
            "NV12 format support is still claimed");

    /* ---- command list ---- */
    hr = ((ccl_fn)slot(device, 12))(device, 0, D3D12_COMMAND_LIST_TYPE_DIRECT, NULL, NULL,
            &IID_ID3D12GraphicsCommandList, &list);
    CHECK(hr == S_OK && list, "CreateCommandList through the shim");
    if (!list)
    {
        printf("RESULT: FAIL, no command list\n");
        return 1;
    }
    CHECK(*(void ***)list != list_vtable(), "the command list vtable is swapped for the shim's");

    /* nothing to translate: the app's own array, untouched */
    for (i = 0; i < 3; i++)
        batch[i] = transition(resource, D3D12_RESOURCE_STATE_RENDER_TARGET,
                D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE);
    ((rb_fn)slot(list, 26))(list, 3, batch);
    calls = barriers(&count, &seen_array, &seen_copy);
    CHECK(calls == 1 && count == 3 && seen_array == batch,
            "plain barriers reach D3DMetal as the app's own array");

    ((rb_fn)slot(list, 26))(list, 0, batch);
    CHECK(barriers(&count, &seen_array, &seen_copy) == calls, "an empty batch is not forwarded");

    /* 40 video-only transitions: all translated, none dropped */
    for (i = 0; i < 40; i++)
        batch[i] = transition(resource, D3D12_RESOURCE_STATE_COMMON,
                D3D12_RESOURCE_STATE_VIDEO_DECODE_WRITE);
    ((rb_fn)slot(list, 26))(list, 40, batch);
    calls = barriers(&count, &seen_array, &seen_copy);
    all = count == 40 && seen_array != batch;
    for (i = 0; all && i < count; i++)
        all = seen_copy[i].Transition.StateAfter == D3D12_RESOURCE_STATE_COPY_DEST
                && seen_copy[i].Transition.StateBefore == D3D12_RESOURCE_STATE_COMMON;
    CHECK(all, "a 40-barrier video batch is translated whole, not cut at 32");

    /* one video barrier in a large plain batch: only it changes */
    for (i = 0; i < 63; i++)
        batch[i] = transition(resource, D3D12_RESOURCE_STATE_RENDER_TARGET,
                D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE);
    batch[63] = transition(resource, D3D12_RESOURCE_STATE_COMMON,
            D3D12_RESOURCE_STATE_VIDEO_PROCESS_READ);
    ((rb_fn)slot(list, 26))(list, 64, batch);
    barriers(&count, &seen_array, &seen_copy);
    all = count == 64;
    for (i = 0; all && i < 63; i++)
        all = !memcmp(&seen_copy[i], &batch[i], sizeof(batch[i]));
    CHECK(all && seen_copy[63].Transition.StateAfter == D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE,
            "a mixed 64-barrier batch keeps every plain barrier and fixes the video one");

    /* ---- copy ---- */
    memset(&dst, 0, sizeof(dst));
    memset(&src, 0, sizeof(src));
    dst.pResource = resource;
    dst.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    dst.SubresourceIndex = 1;
    src.pResource = resource;
    ((ctr_fn)slot(list, 16))(list, &dst, 5, 6, 7, &src, &box);
    calls = copies(&seen_dst, &seen_src, xyz, &seen_box);
    CHECK(calls == 1 && seen_dst == &dst && seen_src == &src && seen_box == &box
            && xyz[0] == 5 && xyz[1] == 6 && xyz[2] == 7,
            "CopyTextureRegion forwards the app's arguments as given");

    CHECK(!unexpected(), "the shim called no D3DMetal slot the test did not expect");

    if (failures)
        printf("RESULT: FAIL, %d d3d12shim checks failed\n", failures);
    else
        printf("RESULT: d3d12shim ok\n");
    return failures ? 1 : 0;
}
