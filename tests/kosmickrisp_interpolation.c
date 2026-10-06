#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <dlfcn.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define APIS(X) \
 X(vkCreateInstance) X(vkDestroyInstance) X(vkEnumeratePhysicalDevices) \
 X(vkGetPhysicalDeviceProperties2) X(vkGetPhysicalDeviceFeatures2) \
 X(vkGetPhysicalDeviceQueueFamilyProperties) X(vkGetPhysicalDeviceMemoryProperties) \
 X(vkCreateDevice) X(vkDestroyDevice) X(vkGetDeviceQueue) \
 X(vkCreateImage) X(vkDestroyImage) X(vkGetImageMemoryRequirements) X(vkBindImageMemory) \
 X(vkCreateBuffer) X(vkDestroyBuffer) X(vkGetBufferMemoryRequirements) X(vkBindBufferMemory) \
 X(vkAllocateMemory) X(vkFreeMemory) X(vkMapMemory) X(vkUnmapMemory) \
 X(vkCreateImageView) X(vkDestroyImageView) X(vkCreateRenderPass) X(vkDestroyRenderPass) \
 X(vkCreateFramebuffer) X(vkDestroyFramebuffer) X(vkCreateShaderModule) X(vkDestroyShaderModule) \
 X(vkCreatePipelineLayout) X(vkDestroyPipelineLayout) X(vkCreateGraphicsPipelines) X(vkDestroyPipeline) \
 X(vkCreateCommandPool) X(vkDestroyCommandPool) X(vkAllocateCommandBuffers) X(vkFreeCommandBuffers) \
 X(vkBeginCommandBuffer) X(vkEndCommandBuffer) X(vkCmdBeginRenderPass) X(vkCmdEndRenderPass) \
 X(vkCmdBindPipeline) X(vkCmdDraw) X(vkCmdCopyImageToBuffer) X(vkCmdPipelineBarrier) \
 X(vkQueueSubmit) X(vkQueueWaitIdle) \
 X(vkCreatePipelineCache) X(vkDestroyPipelineCache) X(vkGetPipelineCacheData)
#define OBJECT_APIS(X) \
 X(vkCreateShadersEXT) X(vkDestroyShaderEXT) X(vkCmdBindShadersEXT) \
 X(vkCmdBeginRendering) X(vkCmdEndRendering) X(vkCmdSetViewportWithCount) X(vkCmdSetScissorWithCount) \
 X(vkCmdSetVertexInputEXT) X(vkCmdSetPrimitiveTopology) X(vkCmdSetPrimitiveRestartEnable) \
 X(vkCmdSetRasterizerDiscardEnable) X(vkCmdSetPolygonModeEXT) X(vkCmdSetCullMode) X(vkCmdSetFrontFace) \
 X(vkCmdSetDepthBiasEnable) X(vkCmdSetDepthClampEnableEXT) X(vkCmdSetRasterizationSamplesEXT) \
 X(vkCmdSetSampleMaskEXT) X(vkCmdSetAlphaToCoverageEnableEXT) X(vkCmdSetAlphaToOneEnableEXT) \
 X(vkCmdSetDepthTestEnable) X(vkCmdSetDepthWriteEnable) X(vkCmdSetDepthCompareOp) \
 X(vkCmdSetDepthBoundsTestEnable) X(vkCmdSetStencilTestEnable) X(vkCmdSetLogicOpEnableEXT) \
 X(vkCmdSetColorBlendEnableEXT) X(vkCmdSetColorBlendEquationEXT) X(vkCmdSetColorWriteMaskEXT) \
 X(vkCmdSetPatchControlPointsEXT) X(vkCmdSetTessellationDomainOriginEXT) X(vkCmdSetProvokingVertexModeEXT)
#define DECLARE(name) static PFN_##name name;
APIS(DECLARE)
OBJECT_APIS(DECLARE)
#undef DECLARE
#define CHECK(expr) do { VkResult r = (expr); if (r != VK_SUCCESS) { \
 fprintf(stderr, "%s failed: %d at %d\n", #expr, r, __LINE__); exit(1); } } while (0)

#define RESOLVE(name) PFN_##name name = (PFN_##name)gipa(instance, #name); if (!name) return 1
#include "kosmickrisp_geometry.h"
#undef RESOLVE

static VkDevice device;
static VkPipelineCache pipeline_cache;

static void create_pipeline(const VkGraphicsPipelineCreateInfo *info, VkPipeline *pipeline)
{
    VkPipelineCreationFeedback feedback;
    VkPipelineCreationFeedbackCreateInfo feedback_info = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_CREATION_FEEDBACK_CREATE_INFO,
        .pNext = (void *)info->pNext, .pPipelineCreationFeedback = &feedback };
    VkGraphicsPipelineCreateInfo copy = *info;
    copy.pNext = &feedback_info;
    CHECK(vkCreateGraphicsPipelines(device, pipeline_cache, 1, &copy, NULL, pipeline));
    if (info->stageCount && getenv("KK_PROBE_REQUIRE_CACHE") &&
        !(feedback.flags & VK_PIPELINE_CREATION_FEEDBACK_APPLICATION_PIPELINE_CACHE_HIT_BIT)) {
        fprintf(stderr, "Expected application pipeline cache hit\n");
        exit(1);
    }
}

static VkPhysicalDeviceMemoryProperties memory_properties;
static uint32_t memory_type(uint32_t bits, VkMemoryPropertyFlags flags)
{
    for (uint32_t i = 0; i < memory_properties.memoryTypeCount; ++i)
        if ((bits & (1u << i)) && (memory_properties.memoryTypes[i].propertyFlags & flags) == flags)
            return i;
    fprintf(stderr, "No suitable memory type\n");
    exit(1);
}

static VkShaderModule load_shader(const char *directory, const char *name)
{
    char path[4096];
    snprintf(path, sizeof(path), "%s/%s.spv", directory, name);
    FILE *file = fopen(path, "rb");
    if (!file || fseek(file, 0, SEEK_END)) exit(1);
    long size = ftell(file);
    if (size <= 0 || size % 4 || fseek(file, 0, SEEK_SET)) exit(1);
    uint32_t *code = malloc((size_t)size);
    if (!code || fread(code, 1, (size_t)size, file) != (size_t)size) exit(1);
    fclose(file);
    VkShaderModuleCreateInfo info = { .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
        .codeSize = (size_t)size, .pCode = code };
    VkShaderModule shader;
    CHECK(vkCreateShaderModule(device, &info, NULL, &shader));
    free(code);
    return shader;
}

int main(int argc, char **argv)
{
    if (argc != 8) {
        fprintf(stderr, "usage: probe ICD SHADERS STAGE CASE MODE LAST SAMPLES\n");
        return 1;
    }
    int test = atoi(argv[4]), mode = atoi(argv[5]), last = atoi(argv[6]);
    int gpl = mode == 1 || mode == 3, objects = mode == 2;
    VkSampleCountFlagBits sample_count = atoi(argv[7]) == 4 ? VK_SAMPLE_COUNT_4_BIT : VK_SAMPLE_COUNT_1_BIT;
    const char *blend_mode = getenv("KK_PROBE_BLEND");
    int advanced = blend_mode && !strcmp(blend_mode, "advanced");
    int dual = blend_mode && !strcmp(blend_mode, "dual");
    int alpha_one = getenv("KK_PROBE_ALPHA_ONE") != NULL;
    int alpha_coverage = getenv("KK_PROBE_ALPHA_COVERAGE") != NULL;
    uint32_t sample_mask = getenv("KK_PROBE_SAMPLE_MASK") ? (uint32_t)strtoul(getenv("KK_PROBE_SAMPLE_MASK"), NULL, 0) : ~0u;
    int gs = !strncmp(argv[3], "gs", 2), tes = !strcmp(argv[3], "tes");
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); return 1; }
    PFN_vkGetInstanceProcAddr gipa = (PFN_vkGetInstanceProcAddr)dlsym(library, "vk_icdGetInstanceProcAddr");
    if (!gipa) return 1;
    vkCreateInstance = (PFN_vkCreateInstance)gipa(VK_NULL_HANDLE, "vkCreateInstance");
    VkApplicationInfo app = { .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO, .apiVersion = VK_API_VERSION_1_3 };
    VkInstanceCreateInfo instance_info = { .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app };
    VkInstance instance;
    CHECK(vkCreateInstance(&instance_info, NULL, &instance));
#define LOAD(name) name = (PFN_##name)gipa(instance, #name); if (!name) { fprintf(stderr, "Missing %s\n", #name); return 1; }
    APIS(LOAD)
#undef LOAD
    uint32_t count = 1;
    VkPhysicalDevice physical;
    CHECK(vkEnumeratePhysicalDevices(instance, &count, &physical));
    VkPhysicalDeviceGraphicsPipelineLibraryPropertiesEXT library_props = {
        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_GRAPHICS_PIPELINE_LIBRARY_PROPERTIES_EXT };
    VkPhysicalDeviceProperties2 props = { .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2,
        .pNext = &library_props };
    vkGetPhysicalDeviceProperties2(physical, &props);
    if (!library_props.graphicsPipelineLibraryIndependentInterpolationDecoration) return 1;
    printf("device=%s cacheUUID=", props.properties.deviceName);
    for (unsigned i = 0; i < VK_UUID_SIZE; ++i) printf("%02x", props.properties.pipelineCacheUUID[i]);
    printf("\n");
    VkPhysicalDeviceProvokingVertexFeaturesEXT provoking = {
        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROVOKING_VERTEX_FEATURES_EXT };
    VkPhysicalDeviceGraphicsPipelineLibraryFeaturesEXT library_features = {
        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_GRAPHICS_PIPELINE_LIBRARY_FEATURES_EXT, .pNext = &provoking };
    VkPhysicalDeviceVulkan13Features f13 = { .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES };
    VkPhysicalDeviceShaderObjectFeaturesEXT object_features = {
        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_OBJECT_FEATURES_EXT, .pNext = &f13 };
    provoking.pNext = &object_features;
    VkPhysicalDeviceFeatures2 features = { .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,
        .pNext = &library_features };
    vkGetPhysicalDeviceFeatures2(physical, &features);
    if ((gs && !features.features.geometryShader) || (tes && !features.features.tessellationShader) ||
        (gpl && !library_features.graphicsPipelineLibrary) || (last && !provoking.provokingVertexLast)) return 77;
    if (objects && (!object_features.shaderObject || !f13.dynamicRendering)) return 77;
    count = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, NULL);
    VkQueueFamilyProperties *families = calloc(count, sizeof(*families));
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, families);
    uint32_t family;
    for (family = 0; family < count; ++family) if (families[family].queueFlags & VK_QUEUE_GRAPHICS_BIT) break;
    free(families);
    if (family == count) return 1;
    float priority = 1;
    VkDeviceQueueCreateInfo queue_info = { .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = family, .queueCount = 1, .pQueuePriorities = &priority };
    const char *extensions[] = { "VK_KHR_pipeline_library", "VK_EXT_graphics_pipeline_library", "VK_EXT_provoking_vertex", "VK_EXT_shader_object", "VK_EXT_blend_operation_advanced" };
    library_features.graphicsPipelineLibrary = gpl;
    provoking.provokingVertexLast = last;
    provoking.transformFeedbackPreservesProvokingVertex = VK_FALSE;
    provoking.pNext = objects ? &object_features : NULL;
    object_features.shaderObject = objects;
    f13 = (VkPhysicalDeviceVulkan13Features){ .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES,
        .dynamicRendering = objects };
    VkPhysicalDeviceFeatures enabled = { .geometryShader = gs, .tessellationShader = tes || test == 5,
        .vertexPipelineStoresAndAtomics = test == 5, .dualSrcBlend = dual, .alphaToOne = alpha_one,
        .sampleRateShading = sample_count != VK_SAMPLE_COUNT_1_BIT };
    VkDeviceCreateInfo device_info = { .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .pNext = &library_features, .queueCreateInfoCount = 1, .pQueueCreateInfos = &queue_info,
        .enabledExtensionCount = advanced ? 5 : objects ? 4 : 3, .ppEnabledExtensionNames = extensions, .pEnabledFeatures = &enabled };
    CHECK(vkCreateDevice(physical, &device_info, NULL, &device));
    if (objects) {
#define LOAD_OBJECT(name) name = (PFN_##name)gipa(instance, #name); if (!name) return 1;
        OBJECT_APIS(LOAD_OBJECT)
#undef LOAD_OBJECT
    }
    vkGetPhysicalDeviceMemoryProperties(physical, &memory_properties);
    VkQueue queue;
    vkGetDeviceQueue(device, family, 0, &queue);
    if (test == 5) {
        PFN_vkGetDeviceProcAddr gdpa = (PFN_vkGetDeviceProcAddr)gipa(instance, "vkGetDeviceProcAddr");
        int failed = geometry_readback(gipa, gdpa, instance, physical, device, family);
        vkDestroyDevice(device, NULL);
        vkDestroyInstance(instance, NULL);
        dlclose(library);
        return failed;
    }
    const char *cache_path = getenv("KK_PROBE_CACHE");
    VkPipelineCacheCreateInfo cache_info = { .sType = VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO };
    void *cache_data = NULL;
    if (cache_path) {
        FILE *file = fopen(cache_path, "rb");
        if (file) {
            if (fseek(file, 0, SEEK_END)) return 1;
            long size = ftell(file);
            if (size <= 0 || fseek(file, 0, SEEK_SET)) return 1;
            cache_data = malloc((size_t)size);
            if (!cache_data || fread(cache_data, 1, (size_t)size, file) != (size_t)size) return 1;
            fclose(file);
            cache_info.initialDataSize = (size_t)size;
            cache_info.pInitialData = cache_data;
        }
    }
    CHECK(vkCreatePipelineCache(device, &cache_info, NULL, &pipeline_cache));
    free(cache_data);
    VkImage images[2];
    VkImageView views[2];
    VkDeviceMemory image_memory[2];
    VkImageSubresourceRange range = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 };
    unsigned image_count = sample_count == VK_SAMPLE_COUNT_1_BIT ? 1 : 2;
    for (unsigned i = 0; i < image_count; ++i) {
        VkImageCreateInfo info = { .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
            .imageType = VK_IMAGE_TYPE_2D, .format = VK_FORMAT_R32G32B32A32_SFLOAT,
            .extent = {8, 8, 1}, .mipLevels = 1, .arrayLayers = 1,
            .samples = i ? VK_SAMPLE_COUNT_1_BIT : sample_count, .tiling = VK_IMAGE_TILING_OPTIMAL,
            .usage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT };
        CHECK(vkCreateImage(device, &info, NULL, &images[i]));
        VkMemoryRequirements req;
        vkGetImageMemoryRequirements(device, images[i], &req);
        VkMemoryAllocateInfo alloc = { .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .allocationSize = req.size, .memoryTypeIndex = memory_type(req.memoryTypeBits, 0) };
        CHECK(vkAllocateMemory(device, &alloc, NULL, &image_memory[i]));
        CHECK(vkBindImageMemory(device, images[i], image_memory[i], 0));
        VkImageViewCreateInfo view = { .sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
            .image = images[i], .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = info.format, .subresourceRange = range };
        CHECK(vkCreateImageView(device, &view, NULL, &views[i]));
    }
    VkBuffer buffer;
    VkBufferCreateInfo buffer_info = { .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = 1024, .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT };
    CHECK(vkCreateBuffer(device, &buffer_info, NULL, &buffer));
    VkMemoryRequirements req;
    vkGetBufferMemoryRequirements(device, buffer, &req);
    VkMemoryAllocateInfo alloc = { .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = req.size, .memoryTypeIndex = memory_type(req.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT) };
    VkDeviceMemory buffer_memory;
    CHECK(vkAllocateMemory(device, &alloc, NULL, &buffer_memory));
    CHECK(vkBindBufferMemory(device, buffer, buffer_memory, 0));
    float *pixels;
    CHECK(vkMapMemory(device, buffer_memory, 0, VK_WHOLE_SIZE, 0, (void **)&pixels));
    VkAttachmentDescription attachments[2];
    for (unsigned i = 0; i < image_count; ++i)
        attachments[i] = (VkAttachmentDescription){ .format = VK_FORMAT_R32G32B32A32_SFLOAT,
            .samples = i ? VK_SAMPLE_COUNT_1_BIT : sample_count, .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,
            .storeOp = VK_ATTACHMENT_STORE_OP_STORE, .stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE,
            .stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE, .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
            .finalLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL };
    VkAttachmentReference color_ref = {0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
    VkAttachmentReference resolve_ref = {1, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
    VkSubpassDescription subpass = { .pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS,
        .colorAttachmentCount = 1, .pColorAttachments = &color_ref,
        .pResolveAttachments = image_count == 2 ? &resolve_ref : NULL };
    VkSubpassDependency dependency = { .srcSubpass = 0, .dstSubpass = VK_SUBPASS_EXTERNAL,
        .srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, .dstStageMask = VK_PIPELINE_STAGE_TRANSFER_BIT,
        .srcAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT, .dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT };
    VkRenderPassCreateInfo render_info = { .sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO,
        .attachmentCount = image_count, .pAttachments = attachments, .subpassCount = 1, .pSubpasses = &subpass,
        .dependencyCount = 1, .pDependencies = &dependency };
    VkRenderPass render_pass;
    CHECK(vkCreateRenderPass(device, &render_info, NULL, &render_pass));
    VkFramebufferCreateInfo frame_info = { .sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO,
        .renderPass = render_pass, .attachmentCount = image_count, .pAttachments = views, .width = 8, .height = 8, .layers = 1 };
    VkFramebuffer framebuffer;
    CHECK(vkCreateFramebuffer(device, &frame_info, NULL, &framebuffer));
    VkPipelineLayoutCreateInfo layout_info = { .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO };
    VkPipelineLayout layout;
    CHECK(vkCreatePipelineLayout(device, &layout_info, NULL, &layout));
    VkShaderModule modules[5];
    VkShaderEXT shader_objects[5] = {0};
    VkPipelineShaderStageCreateInfo stages[5];
    unsigned stage_count = 0;
    const char *names[] = { "vert", "tesc", "tese", "geom", "frag" };
    VkShaderStageFlagBits bits[] = { VK_SHADER_STAGE_VERTEX_BIT, VK_SHADER_STAGE_TESSELLATION_CONTROL_BIT,
        VK_SHADER_STAGE_TESSELLATION_EVALUATION_BIT, VK_SHADER_STAGE_GEOMETRY_BIT, VK_SHADER_STAGE_FRAGMENT_BIT };
    for (unsigned i = 0; i < 5; ++i) {
        if ((i == 1 || i == 2) && !tes) continue;
        if (i == 3 && !gs) continue;
        if (i == 4 && test == 4) continue;
        char name[64];
        snprintf(name, sizeof(name), "%s-%s-%d", argv[3], names[i], test);
        modules[stage_count] = load_shader(argv[2], name);
        stages[stage_count] = (VkPipelineShaderStageCreateInfo){ .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .stage = bits[i], .module = modules[stage_count], .pName = "main" };
        if (objects) {
            char path[4096];
            snprintf(path, sizeof(path), "%s/%s.spv", argv[2], name);
            FILE *file = fopen(path, "rb");
            if (!file || fseek(file, 0, SEEK_END)) return 1;
            long size = ftell(file);
            if (size <= 0 || fseek(file, 0, SEEK_SET)) return 1;
            uint32_t *code = malloc((size_t)size);
            if (!code || fread(code, 1, (size_t)size, file) != (size_t)size) return 1;
            fclose(file);
            VkShaderCreateInfoEXT info = { .sType = VK_STRUCTURE_TYPE_SHADER_CREATE_INFO_EXT,
                .stage = bits[i], .nextStage = i == 0 ? (tes ? VK_SHADER_STAGE_TESSELLATION_CONTROL_BIT :
                    gs ? VK_SHADER_STAGE_GEOMETRY_BIT | VK_SHADER_STAGE_FRAGMENT_BIT : VK_SHADER_STAGE_FRAGMENT_BIT) :
                    i == 1 ? VK_SHADER_STAGE_TESSELLATION_EVALUATION_BIT :
                    i == 4 ? 0 : VK_SHADER_STAGE_FRAGMENT_BIT,
                .codeType = VK_SHADER_CODE_TYPE_SPIRV_EXT, .codeSize = (size_t)size, .pCode = code, .pName = "main" };
            CHECK(vkCreateShadersEXT(device, 1, &info, NULL, &shader_objects[i]));
            free(code);
        }
        ++stage_count;
    }
    VkPipelineVertexInputStateCreateInfo vertex = { .sType = VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO };
    VkPipelineInputAssemblyStateCreateInfo assembly = { .sType = VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
        .topology = tes ? VK_PRIMITIVE_TOPOLOGY_PATCH_LIST : VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST };
    VkViewport viewport = {0, 0, 8, 8, 0, 1};
    VkRect2D scissor = {{0, 0}, {8, 8}};
    VkPipelineViewportStateCreateInfo viewport_info = { .sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO,
        .viewportCount = 1, .pViewports = &viewport, .scissorCount = 1, .pScissors = &scissor };
    VkPipelineRasterizationProvokingVertexStateCreateInfoEXT provoking_state = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_PROVOKING_VERTEX_STATE_CREATE_INFO_EXT,
        .provokingVertexMode = last ? VK_PROVOKING_VERTEX_MODE_LAST_VERTEX_EXT : VK_PROVOKING_VERTEX_MODE_FIRST_VERTEX_EXT };
    VkPipelineRasterizationStateCreateInfo raster = { .sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
        .pNext = &provoking_state, .polygonMode = VK_POLYGON_MODE_FILL, .lineWidth = 1 };
    VkPipelineMultisampleStateCreateInfo samples = { .sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
        .rasterizationSamples = sample_count, .sampleShadingEnable = image_count == 2, .minSampleShading = 1,
        .pSampleMask = &sample_mask, .alphaToCoverageEnable = alpha_coverage, .alphaToOneEnable = alpha_one };
    VkPipelineDepthStencilStateCreateInfo depth = { .sType = VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO };
    VkPipelineColorBlendAttachmentState blend = { .colorWriteMask = test == 4 ? 0 : 15 };
    if (blend_mode) {
        blend.blendEnable = VK_TRUE;
        blend.srcColorBlendFactor = dual ? VK_BLEND_FACTOR_SRC1_COLOR : VK_BLEND_FACTOR_ONE;
        blend.dstColorBlendFactor = dual ? VK_BLEND_FACTOR_ZERO : VK_BLEND_FACTOR_ONE;
        blend.colorBlendOp = advanced ? VK_BLEND_OP_MULTIPLY_EXT : VK_BLEND_OP_ADD;
        blend.srcAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
        blend.dstAlphaBlendFactor = VK_BLEND_FACTOR_ZERO;
        blend.alphaBlendOp = blend.colorBlendOp;
    }
    VkPipelineColorBlendAdvancedStateCreateInfoEXT advanced_state = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_ADVANCED_STATE_CREATE_INFO_EXT,
        .srcPremultiplied = VK_TRUE, .dstPremultiplied = VK_TRUE,
        .blendOverlap = VK_BLEND_OVERLAP_UNCORRELATED_EXT };
    VkPipelineColorBlendStateCreateInfo color = { .sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
        .pNext = advanced ? &advanced_state : NULL, .attachmentCount = 1, .pAttachments = &blend };
    VkPipelineTessellationStateCreateInfo tess = { .sType = VK_STRUCTURE_TYPE_PIPELINE_TESSELLATION_STATE_CREATE_INFO,
        .patchControlPoints = 3 };
    VkGraphicsPipelineCreateInfo pipeline_info = { .sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO,
        .stageCount = stage_count, .pStages = stages, .pVertexInputState = &vertex, .pInputAssemblyState = &assembly,
        .pTessellationState = tes ? &tess : NULL, .pViewportState = &viewport_info,
        .pRasterizationState = &raster, .pMultisampleState = &samples, .pDepthStencilState = &depth,
        .pColorBlendState = &color, .layout = layout, .renderPass = render_pass };
    VkPipeline libraries[4] = {0};
    VkPipeline pipeline = VK_NULL_HANDLE;
    VkGraphicsPipelineLibraryCreateInfoEXT part = { .sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_LIBRARY_CREATE_INFO_EXT };
    VkPipelineLibraryCreateInfoKHR link = { .sType = VK_STRUCTURE_TYPE_PIPELINE_LIBRARY_CREATE_INFO_KHR,
        .libraryCount = 4, .pLibraries = libraries };
    if (gpl) {
        for (unsigned i = 0; i < 4; ++i) {
            VkGraphicsPipelineCreateInfo info = pipeline_info;
            part.flags = (VkGraphicsPipelineLibraryFlagBitsEXT)(1u << i);
            info.pNext = &part;
            info.flags = VK_PIPELINE_CREATE_LIBRARY_BIT_KHR;
            info.stageCount = i == 1 ? stage_count - (test != 4) : i == 2 && test != 4 ? 1 : 0;
            info.pStages = i == 1 ? stages : i == 2 ? &stages[stage_count - 1] : NULL;
            info.pVertexInputState = i == 0 ? &vertex : NULL;
            info.pInputAssemblyState = i == 0 ? &assembly : NULL;
            info.pTessellationState = i == 1 && tes ? &tess : NULL;
            info.pViewportState = i == 1 ? &viewport_info : NULL;
            info.pRasterizationState = i == 1 ? &raster : NULL;
            info.pMultisampleState = i >= 2 ? &samples : NULL;
            info.pDepthStencilState = i == 2 ? &depth : NULL;
            info.pColorBlendState = i == 3 ? &color : NULL;
            create_pipeline(&info, &libraries[i]);
        }
        pipeline_info = (VkGraphicsPipelineCreateInfo){ .sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO,
            .pNext = &link, .layout = layout };
    }
    if (!objects) create_pipeline(&pipeline_info, &pipeline);
    VkCommandPoolCreateInfo pool_info = { .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .queueFamilyIndex = family };
    VkCommandPool pool;
    CHECK(vkCreateCommandPool(device, &pool_info, NULL, &pool));
    VkCommandBufferAllocateInfo command_info = { .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = pool, .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1 };
    VkCommandBuffer command;
    int failed = 0;
    VkShaderModule alternate_module = VK_NULL_HANDLE;
    for (unsigned pass = 0; pass < (mode == 3 ? 0u : gpl && test != 4 && test < 6 ? 2u : 1u); ++pass) {
        if (pass) {
            char name[64];
            snprintf(name, sizeof(name), "%s-alt-%d", argv[3], test);
            alternate_module = load_shader(argv[2], name);
            VkPipelineShaderStageCreateInfo fragment = stages[stage_count - 1];
            fragment.module = alternate_module;
            part.flags = VK_GRAPHICS_PIPELINE_LIBRARY_FRAGMENT_SHADER_BIT_EXT;
            VkGraphicsPipelineCreateInfo info = { .sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO,
                .pNext = &part, .flags = VK_PIPELINE_CREATE_LIBRARY_BIT_KHR,
                .stageCount = 1, .pStages = &fragment, .pMultisampleState = &samples,
                .pDepthStencilState = &depth, .layout = layout, .renderPass = render_pass };
            vkDestroyPipeline(device, pipeline, NULL);
            vkDestroyPipeline(device, libraries[2], NULL);
            create_pipeline(&info, &libraries[2]);
            create_pipeline(&pipeline_info, &pipeline);
        }
        CHECK(vkAllocateCommandBuffers(device, &command_info, &command));
        VkCommandBufferBeginInfo begin = { .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO };
        CHECK(vkBeginCommandBuffer(command, &begin));
        VkClearValue clear[2] = { { .color = { .float32 = {-10, -10, -10, -10} } },
            { .color = { .float32 = {-10, -10, -10, -10} } } };
        if (blend_mode) {
            clear[0].color.float32[0] = .25f;
            clear[0].color.float32[3] = 1;
        } else if (test == 6) {
            clear[0].color = (VkClearColorValue){ .float32 = {0, 0, 0, 0} };
        }
        VkRenderPassBeginInfo render_begin = { .sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO,
            .renderPass = render_pass, .framebuffer = framebuffer, .renderArea = scissor,
            .clearValueCount = image_count, .pClearValues = clear };
        if (objects) {
            VkImageMemoryBarrier image_barriers[2];
            for (unsigned i = 0; i < image_count; ++i)
                image_barriers[i] = (VkImageMemoryBarrier){ .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
                    .dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT, .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED,
                    .newLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .image = images[i], .subresourceRange = range };
            vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
                0, 0, NULL, 0, NULL, image_count, image_barriers);
            VkRenderingAttachmentInfo attachment = { .sType = VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO,
                .imageView = views[0], .imageLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
                .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR, .storeOp = VK_ATTACHMENT_STORE_OP_STORE, .clearValue = clear[0],
                .resolveMode = image_count == 2 ? VK_RESOLVE_MODE_AVERAGE_BIT : VK_RESOLVE_MODE_NONE,
                .resolveImageView = image_count == 2 ? views[1] : VK_NULL_HANDLE,
                .resolveImageLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL };
            VkRenderingInfo rendering = { .sType = VK_STRUCTURE_TYPE_RENDERING_INFO,
                .renderArea = scissor, .layerCount = 1, .colorAttachmentCount = 1, .pColorAttachments = &attachment };
            vkCmdBeginRendering(command, &rendering);
            vkCmdBindShadersEXT(command, 5, bits, shader_objects);
            vkCmdSetViewportWithCount(command, 1, &viewport);
            vkCmdSetScissorWithCount(command, 1, &scissor);
            vkCmdSetVertexInputEXT(command, 0, NULL, 0, NULL);
            vkCmdSetPrimitiveTopology(command, assembly.topology);
            vkCmdSetPrimitiveRestartEnable(command, VK_FALSE);
            vkCmdSetRasterizerDiscardEnable(command, VK_FALSE);
            vkCmdSetPolygonModeEXT(command, VK_POLYGON_MODE_FILL);
            vkCmdSetCullMode(command, VK_CULL_MODE_NONE);
            vkCmdSetFrontFace(command, VK_FRONT_FACE_COUNTER_CLOCKWISE);
            vkCmdSetDepthBiasEnable(command, VK_FALSE);
            vkCmdSetDepthClampEnableEXT(command, VK_FALSE);
            vkCmdSetRasterizationSamplesEXT(command, sample_count);
            VkSampleMask mask = sample_mask;
            vkCmdSetSampleMaskEXT(command, sample_count, &mask);
            vkCmdSetAlphaToCoverageEnableEXT(command, alpha_coverage);
            vkCmdSetAlphaToOneEnableEXT(command, alpha_one);
            vkCmdSetDepthTestEnable(command, VK_FALSE);
            vkCmdSetDepthWriteEnable(command, VK_FALSE);
            vkCmdSetDepthCompareOp(command, VK_COMPARE_OP_ALWAYS);
            vkCmdSetDepthBoundsTestEnable(command, VK_FALSE);
            vkCmdSetStencilTestEnable(command, VK_FALSE);
            vkCmdSetLogicOpEnableEXT(command, VK_FALSE);
            VkBool32 blend_enable = VK_FALSE;
            vkCmdSetColorBlendEnableEXT(command, 0, 1, &blend_enable);
            VkColorBlendEquationEXT equation = { VK_BLEND_FACTOR_ONE, VK_BLEND_FACTOR_ZERO, VK_BLEND_OP_ADD,
                VK_BLEND_FACTOR_ONE, VK_BLEND_FACTOR_ZERO, VK_BLEND_OP_ADD };
            vkCmdSetColorBlendEquationEXT(command, 0, 1, &equation);
            VkColorComponentFlags write_mask = test == 4 ? 0 : 15;
            vkCmdSetColorWriteMaskEXT(command, 0, 1, &write_mask);
            vkCmdSetProvokingVertexModeEXT(command, provoking_state.provokingVertexMode);
            if (tes) {
                vkCmdSetPatchControlPointsEXT(command, 3);
                vkCmdSetTessellationDomainOriginEXT(command, VK_TESSELLATION_DOMAIN_ORIGIN_UPPER_LEFT);
            }
        } else {
            vkCmdBeginRenderPass(command, &render_begin, VK_SUBPASS_CONTENTS_INLINE);
            vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
        }
        vkCmdDraw(command, 3, 1, 0, 0);
        if (objects) {
            vkCmdEndRendering(command);
            VkImageMemoryBarrier image_barrier = { .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
                .srcAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT, .dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT,
                .oldLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, .newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .image = images[image_count - 1], .subresourceRange = range };
            vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                0, 0, NULL, 0, NULL, 1, &image_barrier);
        } else {
            vkCmdEndRenderPass(command);
        }
        VkBufferImageCopy copy = { .imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1}, .imageExtent = {8, 8, 1} };
        vkCmdCopyImageToBuffer(command, images[image_count - 1], VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, buffer, 1, &copy);
        VkMemoryBarrier barrier = { .sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER,
            .srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT, .dstAccessMask = VK_ACCESS_HOST_READ_BIT };
        vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT,
            0, 1, &barrier, 0, NULL, 0, NULL);
        CHECK(vkEndCommandBuffer(command));
        VkSubmitInfo submit = { .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &command };
        CHECK(vkQueueSubmit(queue, 1, &submit, VK_NULL_HANDLE));
        CHECK(vkQueueWaitIdle(queue));
        for (unsigned y = 1; y < 7; ++y) for (unsigned x = 1; x < 7; ++x) {
            float b1 = (x + .5f) / 16, b2 = (y + .5f) / 16, b0 = 1 - b1 - b2;
            int flat = (test == 0) != (pass != 0);
            float expected = test == 4 ? -10 : tes && pass ? .5f * b1 + b2 :
                flat ? (last ? 1 : 0) : (.25f * b1 + .25f * b2) / (b0 + .5f * b1 + .25f * b2);
            if (blend_mode) expected = advanced || dual ? expected * .25f : expected + .25f;
            if (test == 6) {
                float coverage = alpha_coverage || sample_mask != ~0u ? .5f : 1;
                expected *= coverage;
                float expected_alpha = (alpha_one ? 1 : .5f) * coverage;
                if (fabsf(pixels[(y * 8 + x) * 4 + 3] - expected_alpha) > .01f) failed = 1;
            }
            float actual = pixels[(y * 8 + x) * 4];
            if (!isfinite(actual) || fabsf(actual - expected) > (test == 6 ? .025f : image_count == 2 ? .002f : .0001f)) {
                fprintf(stderr, "pixel %u,%u: %f expected %f\n", x, y, actual, expected);
                failed = 1;
                break;
            }
        }
        printf("stage=%s case=%d gpl=%d last=%d samples=%d result=%s\n", argv[3], test, gpl, last,
            sample_count, failed ? "FAIL" : "PASS");
        vkFreeCommandBuffers(device, pool, 1, &command);
    }
    if (alternate_module) vkDestroyShaderModule(device, alternate_module, NULL);
    vkUnmapMemory(device, buffer_memory);
    vkDestroyCommandPool(device, pool, NULL);
    vkDestroyPipeline(device, pipeline, NULL);
    for (unsigned i = 0; i < 4; ++i) if (libraries[i]) vkDestroyPipeline(device, libraries[i], NULL);
    for (unsigned i = 0; i < 5; ++i) if (shader_objects[i]) vkDestroyShaderEXT(device, shader_objects[i], NULL);
    for (unsigned i = 0; i < stage_count; ++i) vkDestroyShaderModule(device, modules[i], NULL);
    vkDestroyPipelineLayout(device, layout, NULL);
    vkDestroyFramebuffer(device, framebuffer, NULL);
    vkDestroyRenderPass(device, render_pass, NULL);
    vkDestroyBuffer(device, buffer, NULL);
    vkFreeMemory(device, buffer_memory, NULL);
    for (unsigned i = 0; i < image_count; ++i) {
        vkDestroyImageView(device, views[i], NULL);
        vkDestroyImage(device, images[i], NULL);
        vkFreeMemory(device, image_memory[i], NULL);
    }
    if (cache_path) {
        size_t size = 0;
        CHECK(vkGetPipelineCacheData(device, pipeline_cache, &size, NULL));
        void *data = malloc(size);
        if (!data) return 1;
        CHECK(vkGetPipelineCacheData(device, pipeline_cache, &size, data));
        FILE *file = fopen(cache_path, "wb");
        if (!file || fwrite(data, 1, size, file) != size) return 1;
        fclose(file);
        free(data);
    }
    vkDestroyPipelineCache(device, pipeline_cache, NULL);
    vkDestroyDevice(device, NULL);
    vkDestroyInstance(instance, NULL);
    dlclose(library);
    return failed;
}
