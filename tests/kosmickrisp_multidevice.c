#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expr) do { VkResult result = (expr); if (result != VK_SUCCESS) { \
    fprintf(stderr, "%s failed: %d at %d\n", #expr, result, __LINE__); exit(1); } } while (0)
#define RESOLVE(name) PFN_##name name = (PFN_##name)gipa(instance, #name); if (!name) return 1
#include "kosmickrisp_geometry.h"
#undef RESOLVE

struct probe_context {
    VkInstance instance;
    VkPhysicalDevice physical;
    VkDevice device;
    uint32_t family;
    uint8_t uuid[VK_UUID_SIZE];
    PFN_vkGetDeviceProcAddr gdpa;
    PFN_vkDestroyInstance destroy_instance;
    PFN_vkDestroyDevice destroy_device;
};

static int create_context(PFN_vkGetInstanceProcAddr gipa, struct probe_context *context)
{
    PFN_vkCreateInstance create_instance = (PFN_vkCreateInstance)gipa(VK_NULL_HANDLE, "vkCreateInstance");
    if (!create_instance) return 1;
    VkApplicationInfo app = { .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO, .apiVersion = VK_API_VERSION_1_3 };
    VkInstanceCreateInfo instance_info = { .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app };
    CHECK(create_instance(&instance_info, NULL, &context->instance));
#define LOAD(name) PFN_##name name = (PFN_##name)gipa(context->instance, #name); if (!name) return 1
    LOAD(vkEnumeratePhysicalDevices);
    LOAD(vkGetPhysicalDeviceProperties2);
    LOAD(vkGetPhysicalDeviceFeatures);
    LOAD(vkGetPhysicalDeviceQueueFamilyProperties);
    LOAD(vkCreateDevice);
    LOAD(vkDestroyDevice);
    LOAD(vkDestroyInstance);
    LOAD(vkGetDeviceProcAddr);
#undef LOAD
    context->destroy_instance = vkDestroyInstance;
    context->destroy_device = vkDestroyDevice;
    context->gdpa = vkGetDeviceProcAddr;
    uint32_t count = 1;
    VkResult result = vkEnumeratePhysicalDevices(context->instance, &count, &context->physical);
    if (result != VK_SUCCESS && result != VK_INCOMPLETE) return 1;
    if (!count) return 77;
    VkPhysicalDeviceIDProperties id = { .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ID_PROPERTIES };
    VkPhysicalDeviceProperties2 properties = { .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, .pNext = &id };
    vkGetPhysicalDeviceProperties2(context->physical, &properties);
    memcpy(context->uuid, id.deviceUUID, sizeof(context->uuid));
    VkPhysicalDeviceFeatures supported;
    vkGetPhysicalDeviceFeatures(context->physical, &supported);
    if (!supported.geometryShader || !supported.tessellationShader || !supported.vertexPipelineStoresAndAtomics) return 77;
    count = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(context->physical, &count, NULL);
    VkQueueFamilyProperties *families = calloc(count, sizeof(*families));
    if (!families) return 1;
    vkGetPhysicalDeviceQueueFamilyProperties(context->physical, &count, families);
    for (context->family = 0; context->family < count; ++context->family)
        if (families[context->family].queueFlags & VK_QUEUE_GRAPHICS_BIT) break;
    free(families);
    if (context->family == count) return 77;
    float priority = 1;
    VkDeviceQueueCreateInfo queue = { .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = context->family, .queueCount = 1, .pQueuePriorities = &priority };
    VkPhysicalDeviceFeatures enabled = { .geometryShader = VK_TRUE,
        .tessellationShader = VK_TRUE, .vertexPipelineStoresAndAtomics = VK_TRUE };
    VkDeviceCreateInfo device_info = { .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount = 1, .pQueueCreateInfos = &queue, .pEnabledFeatures = &enabled };
    CHECK(vkCreateDevice(context->physical, &device_info, NULL, &context->device));
    printf("device-created=%s\n", properties.properties.deviceName);
    return 0;
}

static void destroy_context(struct probe_context *context)
{
    if (context->device) context->destroy_device(context->device, NULL);
    if (context->instance && context->destroy_instance) context->destroy_instance(context->instance, NULL);
    context->device = VK_NULL_HANDLE;
    context->instance = VK_NULL_HANDLE;
}

int main(int argc, char **argv)
{
    if (argc < 2 || argc > 3 || (argc == 3 && strcmp(argv[2], "--create-only"))) {
        fprintf(stderr, "usage: multidevice ICD [--create-only]\n");
        return 1;
    }
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); return 1; }
    PFN_vkGetInstanceProcAddr gipa = (PFN_vkGetInstanceProcAddr)dlsym(library, "vk_icdGetInstanceProcAddr");
    if (!gipa) { dlclose(library); return 1; }
    struct probe_context contexts[2] = {{0}};
    int result = create_context(gipa, &contexts[0]);
    if (!result) result = create_context(gipa, &contexts[1]);
    if (!result && memcmp(contexts[0].uuid, contexts[1].uuid, VK_UUID_SIZE)) result = 77;
    if (!result) {
        destroy_context(&contexts[0]);
        puts("first-device-and-instance-destroyed");
        if (argc != 3) {
            result = geometry_readback(gipa, contexts[1].gdpa, contexts[1].instance,
                contexts[1].physical, contexts[1].device, contexts[1].family);
            if (!result) puts("remaining-device-render-and-compute-readback=PASS");
        }
    }
    destroy_context(&contexts[0]);
    destroy_context(&contexts[1]);
    dlclose(library);
    if (!result) printf("multidevice-%s=PASS\n", argc == 3 ? "creation-and-teardown" : "lifetime");
    return result;
}
