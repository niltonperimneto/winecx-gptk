/* SPDX-License-Identifier: GPL-3.0-only
 * D3D11On12 core ABI and input validation.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <initguid.h>
#include <d3d12.h>

#include "d3d11on12core.h"
#include "wine_d3d11_diag.h"

namespace
{
template<typename Interface>
class ComRef
{
public:
    ComRef() noexcept = default;
    ~ComRef() noexcept
    {
        if (pointer_)
            pointer_->Release();
    }

    ComRef(const ComRef &) = delete;
    ComRef &operator=(const ComRef &) = delete;

    Interface *get() const noexcept { return pointer_; }

    /* Releasing first is what keeps a second acquisition through the same
     * holder from dropping the first reference on the floor.  No call site
     * reuses a holder today, and this is here so that the holder is not the
     * reason one cannot. */
    Interface **put() noexcept
    {
        if (pointer_)
        {
            pointer_->Release();
            pointer_ = nullptr;
        }
        return &pointer_;
    }

private:
    Interface *pointer_ = nullptr;
};

/* Every interface this boundary acquires goes through here.
 *
 * A success code returned with no interface breaks the COM contract, and the
 * D3DMetal payload does it, so the pointer has to be checked at every
 * acquisition and not just at most of them.  Making that one funnel rather
 * than a rule each new call site has to remember is the point: CI rejects a
 * QueryInterface or GetDevice call that does not pass its holder through
 * this.
 *
 * The holder is taken by reference, not as a pointer value.  Argument
 * evaluation order is unspecified, so passing acquired.get() alongside the
 * call that fills it could read the pointer before the call writes it and
 * reject every success.  Binding a reference reads nothing; the read happens
 * in the body, once both arguments are evaluated. */
template<typename Interface>
HRESULT strictResult(HRESULT hr, const ComRef<Interface> &acquired) noexcept
{
    if (SUCCEEDED(hr) && !acquired.get())
        return E_NOINTERFACE;
    return hr;
}

void clearOutputs(ID3D11Device **device, ID3D11DeviceContext **context,
        D3D_FEATURE_LEVEL *featureLevel) noexcept
{
    if (device)
        *device = nullptr;
    if (context)
        *context = nullptr;
    if (featureLevel)
        *featureLevel = static_cast<D3D_FEATURE_LEVEL>(0);
}

/* Decide whether two objects are the same COM object.
 *
 * IUnknown is the canonical test: it is the only interface COM requires to
 * return one stable pointer per object.  But a payload that answers an
 * IUnknown query with S_OK and no pointer cannot be identified that way at
 * all, and comparing two such answers would make every object identical to
 * every other -- which is how a queue belonging to a different device used to
 * pass this check.
 *
 * So identity is never inferred from a failure.  An indeterminate answer is
 * propagated to the caller, which fails closed.  The typed-pointer fast path
 * at the call site keeps that from rejecting a payload whose only defect is
 * the IUnknown query. */
HRESULT comObjectsIdentical(IUnknown *left, IUnknown *right,
        bool *identical) noexcept
{
    ComRef<IUnknown> leftIdentity;
    ComRef<IUnknown> rightIdentity;
    HRESULT hr;

    *identical = false;

    hr = strictResult(left->QueryInterface(IID_IUnknown,
            reinterpret_cast<void **>(leftIdentity.put())), leftIdentity);
    if (FAILED(hr))
        return hr;

    hr = strictResult(right->QueryInterface(IID_IUnknown,
            reinterpret_cast<void **>(rightIdentity.put())), rightIdentity);
    if (FAILED(hr))
        return hr;

    *identical = leftIdentity.get() == rightIdentity.get();
    return S_OK;
}

/* The public creation flags this boundary recognizes.
 *
 * Composed from the named enumerators rather than from literals: the numbers
 * are the SDK's to define, and a hand-copied bitmask here would be one more
 * place for them to be wrong.  An application passing a bit outside this set
 * is passing something no published flag names, and accepting it silently
 * would mean promising to honour it.
 *
 * Honouring the ones inside the set is a separate matter, and not this
 * milestone's: which public flag sets which member of the DDI's Flags word is
 * a runtime implementation detail that is not publicly specified, so this
 * validates and records rather than translating.  See docs/CLEANROOM-DDI.md
 * for the open question. */
constexpr UINT knownCreateDeviceFlags = D3D11_CREATE_DEVICE_SINGLETHREADED
        | D3D11_CREATE_DEVICE_DEBUG
        | D3D11_CREATE_DEVICE_SWITCH_TO_REF
        | D3D11_CREATE_DEVICE_PREVENT_INTERNAL_THREADING_OPTIMIZATIONS
        | D3D11_CREATE_DEVICE_BGRA_SUPPORT
        | D3D11_CREATE_DEVICE_DEBUGGABLE
        | D3D11_CREATE_DEVICE_PREVENT_ALTERING_LAYER_SETTINGS_FROM_REGISTRY
        | D3D11_CREATE_DEVICE_DISABLE_GPU_TIMEOUT
        | D3D11_CREATE_DEVICE_VIDEO_SUPPORT;

/* One guard per repeatable condition.  An application that probes
 * D3D11On12CreateDevice in its initialization loop must not be able to flood
 * the log with these. */
volatile LONG reportedDeviceNotD3D12;
volatile LONG reportedQueueNotD3D12;
volatile LONG reportedQueueDevice;
volatile LONG reportedIdentity;
volatile LONG reportedNodeCount;
volatile LONG reportedUntranslatedFlags;
volatile LONG reportedNoHost;
}

extern "C" UINT WINAPI WineD3D11On12GetABIVersion() noexcept
{
    return WINE_D3D11ON12_ABI_VERSION;
}

extern "C" HRESULT WINAPI WineD3D11On12GetInterface(UINT requestedVersion,
        UINT interfaceSize, WineD3D11On12Interface *interfaceOut) noexcept
{
    if (!interfaceOut || interfaceSize != sizeof(*interfaceOut))
        return E_INVALIDARG;

    ZeroMemory(interfaceOut, sizeof(*interfaceOut));
    interfaceOut->size = sizeof(*interfaceOut);
    interfaceOut->version = WINE_D3D11ON12_ABI_VERSION;

    if (requestedVersion != WINE_D3D11ON12_ABI_VERSION)
        return E_NOINTERFACE;

    interfaceOut->capabilities = WINE_D3D11ON12_CAP_VALIDATION;
    interfaceOut->createDevice = WineD3D11On12CreateDeviceV1;
    return S_OK;
}

extern "C" HRESULT WINAPI WineD3D11On12CreateDeviceV1(IUnknown *deviceObject,
        UINT flags, const D3D_FEATURE_LEVEL *featureLevels,
        UINT featureLevelCount, IUnknown *const *queueObjects, UINT queueCount,
        UINT nodeMask, ID3D11Device **device11,
        ID3D11DeviceContext **context11,
        D3D_FEATURE_LEVEL *chosenFeatureLevel) noexcept
{
    clearOutputs(device11, context11, chosenFeatureLevel);

    if (!deviceObject || !queueObjects || queueCount != 1 || !queueObjects[0])
        return E_INVALIDARG;
    if ((featureLevels == nullptr) != (featureLevelCount == 0))
        return E_INVALIDARG;
    if (flags & ~knownCreateDeviceFlags)
        return E_INVALIDARG;
    if (nodeMask && (nodeMask & (nodeMask - 1)))
        return E_INVALIDARG;

    /* Accepted, but carried no further than this function.  Saying so once is
     * the difference between a known gap and a parameter that looks honoured
     * because nothing complained. */
    if (flags)
        wineD3D11DiagReportOnce(&reportedUntranslatedFlags,
                "d3d11on12core: the requested D3D11 creation flags are "
                "validated but not yet translated to the DDI's create-device "
                "flags; no flag is being honoured in this milestone.\n");

    /* Propagate the QueryInterface result.  A caller that passed something
     * which is not a D3D12 device or queue must be told E_NOINTERFACE rather
     * than a generic argument error. */
    ComRef<ID3D12Device> device12;
    HRESULT hr = strictResult(deviceObject->QueryInterface(IID_ID3D12Device,
            reinterpret_cast<void **>(device12.put())), device12);
    if (FAILED(hr))
    {
        wineD3D11DiagReportOnce(&reportedDeviceNotD3D12,
                "d3d11on12core: the supplied device object does not implement "
                "ID3D12Device.\n");
        return hr;
    }

    /* A single-bit mask is not the same as a mask naming a node that exists.
     * The bit index has to be below the device's node count, or the host would
     * later ask the driver to create a device on a node the caller's D3D12
     * device does not have.  Only asked when a node was named: a zero mask
     * means the default node and needs no device consulted. */
    if (nodeMask)
    {
        const UINT nodeCount = device12.get()->GetNodeCount();

        if (!nodeCount)
        {
            wineD3D11DiagReportOnce(&reportedNodeCount,
                    "d3d11on12core: the supplied device reports zero nodes, so "
                    "no node mask can name a node it has.\n");
            return E_INVALIDARG;
        }
        /* At 32 nodes or more every single-bit mask a UINT can hold names a
         * node, and 1u << 32 is undefined rather than large. */
        if (nodeCount < 32 && nodeMask >= (1u << nodeCount))
            return E_INVALIDARG;
    }

    ComRef<ID3D12CommandQueue> queue;
    hr = strictResult(queueObjects[0]->QueryInterface(IID_ID3D12CommandQueue,
            reinterpret_cast<void **>(queue.put())), queue);
    if (FAILED(hr))
    {
        wineD3D11DiagReportOnce(&reportedQueueNotD3D12,
                "d3d11on12core: the supplied queue object does not implement "
                "ID3D12CommandQueue.\n");
        return hr;
    }
    if (queue.get()->GetDesc().Type != D3D12_COMMAND_LIST_TYPE_DIRECT)
        return E_INVALIDARG;

    ComRef<ID3D12Device> queueDevice;
    hr = strictResult(queue.get()->GetDevice(IID_ID3D12Device,
            reinterpret_cast<void **>(queueDevice.put())), queueDevice);
    if (FAILED(hr))
    {
        wineD3D11DiagReportOnce(&reportedQueueDevice,
                "d3d11on12core: the supplied queue would not report its "
                "owning ID3D12Device.\n");
        return hr;
    }

    /* Two equal ID3D12Device pointers already answer the question, and they
     * are what a stable implementation returns, so the IUnknown query is only
     * needed when they differ.  Submitting to a queue owned by another device
     * would break the first non-negotiable invariant, so an answer that cannot
     * be established is a rejection. */
    bool identical = device12.get() == queueDevice.get();
    if (!identical)
    {
        hr = comObjectsIdentical(device12.get(), queueDevice.get(), &identical);
        if (FAILED(hr))
        {
            wineD3D11DiagReportOnce(&reportedIdentity,
                    "d3d11on12core: the COM identity of the supplied device "
                    "and the queue's owning device could not be established; "
                    "refusing to assume they match.\n");
            return hr;
        }
    }
    if (!identical)
        return E_INVALIDARG;

    if (featureLevelCount)
    {
        D3D12_FEATURE_DATA_FEATURE_LEVELS levels = {};
        levels.NumFeatureLevels = featureLevelCount;
        levels.pFeatureLevelsRequested = featureLevels;
        hr = device12.get()->CheckFeatureSupport(D3D12_FEATURE_FEATURE_LEVELS,
                &levels, sizeof(levels));
        if (FAILED(hr) || !levels.MaxSupportedFeatureLevel)
            return FAILED(hr) ? hr : E_INVALIDARG;
    }

    /* The next milestone constructs the Wine D3D11 runtime/DDI host here.
     * Never return success until genuine ID3D11Device and context objects are
     * backed by the supplied device and queue. */
    wineD3D11DiagReportOnce(&reportedNoHost,
            "d3d11on12core: device and queue accepted, but no D3D11 "
            "runtime/DDI host is implemented in this milestone; returning "
            "DXGI_ERROR_UNSUPPORTED instead of a fabricated device.\n");
    return DXGI_ERROR_UNSUPPORTED;
}
