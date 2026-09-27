/* A stand-in for Apple's renamed d3d12 (d3dmt.dll) that records what
 * gptk-video/d3d12shim.dll forwards to it.
 *
 * The shim loads "d3dmt.dll" by name, so placing this beside the test makes
 * every call the shim passes through land here, where the test can check the
 * arguments, the pointer identity of the arrays and the counts. Only the slots
 * the shim hooks are implemented; every other slot records an unexpected call.
 * The vtables are as long as the ones the shim copies (64 and 96 slots), so
 * copying them never reads past the end.
 *
 * CreateCommittedResource hands out resources from a fixed pool. They keep the
 * interface the shim attaches with SetPrivateDataInterface and release it only
 * when the test calls MockDestroyResource, which is how D3D12 tells the shim a
 * texture has died. */
#include <windows.h>
#include <d3d12.h>
#include <string.h>

#define DEVICE_SLOTS 64
#define LIST_SLOTS 96
#define MAX_BARRIERS 256
#define RESOURCE_SLOTS 16
#define MAX_RESOURCES 8

struct mock_object
{
    void **vtbl;
};

static void *device_vtbl[DEVICE_SLOTS];
static void *list_vtbl[LIST_SLOTS];
static struct mock_object device = { device_vtbl };
static struct mock_object list = { list_vtbl };

static LONG refcount = 1;
static LONG unexpected;
static int answer_tight_alignment;

static UINT barrier_calls, barrier_count;
static const D3D12_RESOURCE_BARRIER *barrier_array;
static D3D12_RESOURCE_BARRIER barrier_copy[MAX_BARRIERS];

struct mock_resource
{
    void **vtbl;
    LONG ref;
    IUnknown *private_data;
    D3D12_RESOURCE_DESC desc;
};

static void *resource_vtbl[RESOURCE_SLOTS];
static struct mock_resource resources[MAX_RESOURCES];
static UINT nresources;

static UINT copy_calls;
static const D3D12_TEXTURE_COPY_LOCATION *copy_dst, *copy_src;
static UINT copy_x, copy_y, copy_z;
static const D3D12_BOX *copy_box;

static HRESULT WINAPI unexpected_slot(void *self)
{
    InterlockedIncrement(&unexpected);
    return E_NOTIMPL;
}

static HRESULT WINAPI mock_QueryInterface(void *self, REFIID riid, void **out)
{
    if (out)
        *out = NULL;
    return E_NOINTERFACE;
}

static ULONG WINAPI mock_AddRef(void *self)
{
    return InterlockedIncrement(&refcount);
}

static ULONG WINAPI mock_Release(void *self)
{
    return InterlockedDecrement(&refcount);
}

static HRESULT WINAPI mock_CreateCommandList(void *self, UINT mask, D3D12_COMMAND_LIST_TYPE type,
        void *allocator, void *state, REFIID riid, void **out)
{
    *out = &list;
    return S_OK;
}

/* Feature 54 is D3D12_FEATURE_D3D12_TIGHT_ALIGNMENT. D3DMetal refuses it with
 * E_INVALIDARG; MockAnswerTightAlignment(1) plays a D3DMetal that knows it.
 * Other features get a recognisable answer so pass-through can be checked. */
static HRESULT WINAPI mock_CheckFeatureSupport(void *self, D3D12_FEATURE feature, void *data, UINT size)
{
    if (feature == (D3D12_FEATURE)54)
    {
        if (!answer_tight_alignment || !data || size != sizeof(UINT))
            return E_INVALIDARG;
        *(UINT *)data = 1;
        return S_OK;
    }
    if (feature == D3D12_FEATURE_FORMAT_SUPPORT && data
            && size == sizeof(D3D12_FEATURE_DATA_FORMAT_SUPPORT))
    {
        D3D12_FEATURE_DATA_FORMAT_SUPPORT *support = data;

        support->Support1 = support->Format == DXGI_FORMAT_NV12 ? 0 : D3D12_FORMAT_SUPPORT1_BUFFER;
        support->Support2 = 0;
        return S_OK;
    }
    if (data && size >= sizeof(UINT))
        *(UINT *)data = 0x5eed;
    return S_FALSE;
}

static void WINAPI mock_CopyTextureRegion(void *self, const D3D12_TEXTURE_COPY_LOCATION *dst,
        UINT x, UINT y, UINT z, const D3D12_TEXTURE_COPY_LOCATION *src, const D3D12_BOX *box)
{
    ++copy_calls;
    copy_dst = dst;
    copy_src = src;
    copy_x = x;
    copy_y = y;
    copy_z = z;
    copy_box = box;
}

static void WINAPI mock_ResourceBarrier(void *self, UINT count, const D3D12_RESOURCE_BARRIER *barriers)
{
    ++barrier_calls;
    barrier_count = count;
    barrier_array = barriers;
    memcpy(barrier_copy, barriers, min(count, MAX_BARRIERS) * sizeof(*barriers));
}

static ULONG WINAPI resource_AddRef(struct mock_resource *self)
{
    return InterlockedIncrement(&self->ref);
}

static ULONG WINAPI resource_Release(struct mock_resource *self)
{
    return InterlockedDecrement(&self->ref);
}

/* D3D12 holds a reference on the interface until the object is destroyed. */
static HRESULT WINAPI resource_SetPrivateDataInterface(struct mock_resource *self, REFGUID guid,
        IUnknown *data)
{
    if (self->private_data)
        self->private_data->lpVtbl->Release(self->private_data);
    if ((self->private_data = data))
        data->lpVtbl->AddRef(data);
    return S_OK;
}

static HRESULT WINAPI mock_CreateCommittedResource(void *self, const D3D12_HEAP_PROPERTIES *heap,
        D3D12_HEAP_FLAGS flags, const D3D12_RESOURCE_DESC *desc, D3D12_RESOURCE_STATES state,
        const D3D12_CLEAR_VALUE *clear, REFIID riid, void **out)
{
    struct mock_resource *resource;

    if (nresources == MAX_RESOURCES)
        return E_OUTOFMEMORY;
    resource = &resources[nresources++];
    resource->vtbl = resource_vtbl;
    resource->ref = 1;
    resource->desc = *desc;
    *out = resource;
    return S_OK;
}

static void init_vtables(void)
{
    unsigned int i;

    if (device_vtbl[0])
        return;
    for (i = 0; i < DEVICE_SLOTS; i++)
        device_vtbl[i] = (void *)unexpected_slot;
    for (i = 0; i < LIST_SLOTS; i++)
        list_vtbl[i] = (void *)unexpected_slot;
    for (i = 0; i < RESOURCE_SLOTS; i++)
        resource_vtbl[i] = (void *)unexpected_slot;
    resource_vtbl[0] = (void *)mock_QueryInterface;
    resource_vtbl[1] = (void *)resource_AddRef;
    resource_vtbl[2] = (void *)resource_Release;
    resource_vtbl[5] = (void *)resource_SetPrivateDataInterface;
    device_vtbl[27] = (void *)mock_CreateCommittedResource;
    device_vtbl[0] = list_vtbl[0] = (void *)mock_QueryInterface;
    device_vtbl[1] = list_vtbl[1] = (void *)mock_AddRef;
    device_vtbl[2] = list_vtbl[2] = (void *)mock_Release;
    device_vtbl[12] = (void *)mock_CreateCommandList;
    device_vtbl[13] = (void *)mock_CheckFeatureSupport;
    list_vtbl[16] = (void *)mock_CopyTextureRegion;
    list_vtbl[26] = (void *)mock_ResourceBarrier;
}

HRESULT WINAPI D3D12CreateDevice(IUnknown *adapter, D3D_FEATURE_LEVEL level, REFIID riid, void **out)
{
    init_vtables();
    *out = &device;
    InterlockedIncrement(&refcount);
    return S_OK;
}

void WINAPI MockAnswerTightAlignment(int answer)
{
    answer_tight_alignment = answer;
}

void **WINAPI MockDeviceVtable(void)
{
    return device_vtbl;
}

void **WINAPI MockListVtable(void)
{
    return list_vtbl;
}

LONG WINAPI MockUnexpectedCalls(void)
{
    return unexpected;
}

UINT WINAPI MockBarriers(UINT *count, const D3D12_RESOURCE_BARRIER **array,
        const D3D12_RESOURCE_BARRIER **copy)
{
    *count = barrier_count;
    *array = barrier_array;
    *copy = barrier_copy;
    return barrier_calls;
}

UINT WINAPI MockCopy(const D3D12_TEXTURE_COPY_LOCATION **dst, const D3D12_TEXTURE_COPY_LOCATION **src,
        UINT *xyz, const D3D12_BOX **box)
{
    *dst = copy_dst;
    *src = copy_src;
    xyz[0] = copy_x;
    xyz[1] = copy_y;
    xyz[2] = copy_z;
    *box = copy_box;
    return copy_calls;
}

/* Resource i in creation order, its reference count and its format. */
void *WINAPI MockResource(UINT i, LONG *ref, DXGI_FORMAT *format)
{
    if (i >= nresources)
        return NULL;
    *ref = resources[i].ref;
    *format = resources[i].desc.Format;
    return &resources[i];
}

/* What D3D12 does when the object dies: drop the attached interface. */
void WINAPI MockDestroyResource(void *object)
{
    struct mock_resource *resource = object;
    IUnknown *data = resource->private_data;

    resource->private_data = NULL;
    if (data)
        data->lpVtbl->Release(data);
}
