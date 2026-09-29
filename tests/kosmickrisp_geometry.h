#include "kosmickrisp_geometry/vert_spv.h"
#include "kosmickrisp_geometry/geom_spv.h"
#include "kosmickrisp_geometry/frag_spv.h"
#include "kosmickrisp_geometry/tesc_spv.h"
#include "kosmickrisp_geometry/tese_spv.h"

static int geometry_readback(PFN_vkGetInstanceProcAddr gipa, PFN_vkGetDeviceProcAddr gdpa,
    VkInstance instance, VkPhysicalDevice physical, VkDevice device, uint32_t family)
{
    RESOLVE(vkGetPhysicalDeviceMemoryProperties);
#define DEVICE_PROC(name) PFN_##name name = (PFN_##name)gdpa(device, #name); if (!name) return 1
    DEVICE_PROC(vkCreateBuffer); DEVICE_PROC(vkDestroyBuffer);
    DEVICE_PROC(vkGetBufferMemoryRequirements); DEVICE_PROC(vkBindBufferMemory);
    DEVICE_PROC(vkCreateImage); DEVICE_PROC(vkDestroyImage);
    DEVICE_PROC(vkGetImageMemoryRequirements); DEVICE_PROC(vkBindImageMemory);
    DEVICE_PROC(vkCreateImageView); DEVICE_PROC(vkDestroyImageView);
    DEVICE_PROC(vkAllocateMemory); DEVICE_PROC(vkFreeMemory);
    DEVICE_PROC(vkMapMemory); DEVICE_PROC(vkUnmapMemory);
    DEVICE_PROC(vkCreateDescriptorSetLayout); DEVICE_PROC(vkDestroyDescriptorSetLayout);
    DEVICE_PROC(vkCreateDescriptorPool); DEVICE_PROC(vkDestroyDescriptorPool);
    DEVICE_PROC(vkAllocateDescriptorSets); DEVICE_PROC(vkUpdateDescriptorSets);
    DEVICE_PROC(vkCreateShaderModule); DEVICE_PROC(vkDestroyShaderModule);
    DEVICE_PROC(vkCreatePipelineLayout); DEVICE_PROC(vkDestroyPipelineLayout);
    DEVICE_PROC(vkCreateGraphicsPipelines); DEVICE_PROC(vkDestroyPipeline);
    DEVICE_PROC(vkCreateRenderPass); DEVICE_PROC(vkDestroyRenderPass);
    DEVICE_PROC(vkCreateFramebuffer); DEVICE_PROC(vkDestroyFramebuffer);
    DEVICE_PROC(vkCreateCommandPool); DEVICE_PROC(vkDestroyCommandPool);
    DEVICE_PROC(vkAllocateCommandBuffers); DEVICE_PROC(vkBeginCommandBuffer);
    DEVICE_PROC(vkEndCommandBuffer); DEVICE_PROC(vkCmdPipelineBarrier);
    DEVICE_PROC(vkCmdBindPipeline); DEVICE_PROC(vkCmdBindDescriptorSets);
    DEVICE_PROC(vkCmdPushConstants); DEVICE_PROC(vkCmdDraw);
    DEVICE_PROC(vkCmdBeginRenderPass); DEVICE_PROC(vkCmdEndRenderPass);
    DEVICE_PROC(vkCmdClearColorImage); DEVICE_PROC(vkCmdCopyImageToBuffer);
    DEVICE_PROC(vkGetDeviceQueue); DEVICE_PROC(vkQueueSubmit); DEVICE_PROC(vkQueueWaitIdle);
#undef DEVICE_PROC
    VkPhysicalDeviceMemoryProperties properties;
    vkGetPhysicalDeviceMemoryProperties(physical, &properties);
    VkBufferCreateInfo buffer_info = { .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = 512, .usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT };
    VkBuffer buffer;
    CHECK(vkCreateBuffer(device, &buffer_info, NULL, &buffer));
    VkMemoryRequirements requirements;
    vkGetBufferMemoryRequirements(device, buffer, &requirements);
    uint32_t type;
    VkMemoryPropertyFlags flags = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
    for (type = 0; type < properties.memoryTypeCount; ++type)
        if ((requirements.memoryTypeBits & (1u << type)) &&
            (properties.memoryTypes[type].propertyFlags & flags) == flags) break;
    if (type == properties.memoryTypeCount) return 1;
    VkMemoryAllocateInfo allocation = { .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = requirements.size, .memoryTypeIndex = type };
    VkDeviceMemory memory;
    CHECK(vkAllocateMemory(device, &allocation, NULL, &memory));
    CHECK(vkBindBufferMemory(device, buffer, memory, 0));
    void *mapped;
    CHECK(vkMapMemory(device, memory, 0, 512, 0, &mapped));
    VkImage images[2];
    VkDeviceMemory image_memory[2];
    VkImageView views[2];
    VkImageSubresourceRange range = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 };
    for (unsigned i = 0; i < 2; ++i) {
        VkImageCreateInfo info = { .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
            .imageType = VK_IMAGE_TYPE_2D, .format = i ? VK_FORMAT_R32_UINT : VK_FORMAT_R8G8B8A8_UNORM,
            .extent = { i ? 3 : 8, i ? 1 : 8, 1 }, .mipLevels = 1, .arrayLayers = 1,
            .samples = VK_SAMPLE_COUNT_1_BIT, .tiling = VK_IMAGE_TILING_OPTIMAL,
            .usage = VK_IMAGE_USAGE_TRANSFER_SRC_BIT | (i ?
                VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT : VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) };
        CHECK(vkCreateImage(device, &info, NULL, &images[i]));
        vkGetImageMemoryRequirements(device, images[i], &requirements);
        for (type = 0; type < properties.memoryTypeCount; ++type)
            if (requirements.memoryTypeBits & (1u << type)) break;
        if (type == properties.memoryTypeCount) return 1;
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = type;
        CHECK(vkAllocateMemory(device, &allocation, NULL, &image_memory[i]));
        CHECK(vkBindImageMemory(device, images[i], image_memory[i], 0));
        VkImageViewCreateInfo view_info = { .sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
            .image = images[i], .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = info.format,
            .subresourceRange = range };
        CHECK(vkCreateImageView(device, &view_info, NULL, &views[i]));
    }
    VkDescriptorSetLayoutBinding bindings[] = {
        { .binding = 0, .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
          .descriptorCount = 1, .stageFlags = VK_SHADER_STAGE_GEOMETRY_BIT },
        { .binding = 1, .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE,
          .descriptorCount = 1, .stageFlags = VK_SHADER_STAGE_GEOMETRY_BIT } };
    VkDescriptorSetLayoutCreateInfo set_info = { .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
        .bindingCount = 2, .pBindings = bindings };
    VkDescriptorSetLayout set_layout;
    CHECK(vkCreateDescriptorSetLayout(device, &set_info, NULL, &set_layout));
    VkDescriptorPoolSize sizes[] = { {VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1}, {VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1} };
    VkDescriptorPoolCreateInfo pool_info = { .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
        .maxSets = 1, .poolSizeCount = 2, .pPoolSizes = sizes };
    VkDescriptorPool descriptor_pool;
    CHECK(vkCreateDescriptorPool(device, &pool_info, NULL, &descriptor_pool));
    VkDescriptorSetAllocateInfo set_allocate = { .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
        .descriptorPool = descriptor_pool, .descriptorSetCount = 1, .pSetLayouts = &set_layout };
    VkDescriptorSet set;
    CHECK(vkAllocateDescriptorSets(device, &set_allocate, &set));
    VkDescriptorBufferInfo buffer_binding = { .buffer = buffer, .offset = 256, .range = 16 };
    VkDescriptorImageInfo image_binding = { .imageView = views[1], .imageLayout = VK_IMAGE_LAYOUT_GENERAL };
    VkWriteDescriptorSet writes[] = {
        { .sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstSet = set, .dstBinding = 0,
          .descriptorCount = 1, .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, .pBufferInfo = &buffer_binding },
        { .sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstSet = set, .dstBinding = 1,
          .descriptorCount = 1, .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, .pImageInfo = &image_binding } };
    vkUpdateDescriptorSets(device, 2, writes, 0, NULL);
    VkPushConstantRange push = { VK_SHADER_STAGE_VERTEX_BIT, 0, 4 };
    VkPipelineLayoutCreateInfo layout_info = { .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
        .setLayoutCount = 1, .pSetLayouts = &set_layout, .pushConstantRangeCount = 1, .pPushConstantRanges = &push };
    VkPipelineLayout layout;
    CHECK(vkCreatePipelineLayout(device, &layout_info, NULL, &layout));
    VkAttachmentDescription attachment = { .format = VK_FORMAT_R8G8B8A8_UNORM,
        .samples = VK_SAMPLE_COUNT_1_BIT, .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,
        .storeOp = VK_ATTACHMENT_STORE_OP_STORE, .stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE,
        .stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE,
        .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED, .finalLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL };
    VkAttachmentReference reference = { 0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL };
    VkSubpassDescription subpass = { .pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS,
        .colorAttachmentCount = 1, .pColorAttachments = &reference };
    VkSubpassDependency dependency = { .srcSubpass = 0, .dstSubpass = VK_SUBPASS_EXTERNAL,
        .srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, .dstStageMask = VK_PIPELINE_STAGE_TRANSFER_BIT,
        .srcAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT, .dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT };
    VkRenderPassCreateInfo render_info = { .sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO,
        .attachmentCount = 1, .pAttachments = &attachment, .subpassCount = 1, .pSubpasses = &subpass,
        .dependencyCount = 1, .pDependencies = &dependency };
    VkRenderPass render_pass;
    CHECK(vkCreateRenderPass(device, &render_info, NULL, &render_pass));
    VkFramebufferCreateInfo framebuffer_info = { .sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO,
        .renderPass = render_pass, .attachmentCount = 1, .pAttachments = views, .width = 8, .height = 8, .layers = 1 };
    VkFramebuffer framebuffer;
    CHECK(vkCreateFramebuffer(device, &framebuffer_info, NULL, &framebuffer));
    const uint32_t *codes[] = { kk_vert, kk_tesc, kk_tese, kk_geom, kk_frag };
    size_t code_sizes[] = { sizeof(kk_vert), sizeof(kk_tesc), sizeof(kk_tese), sizeof(kk_geom), sizeof(kk_frag) };
    VkShaderStageFlagBits stage_bits[] = { VK_SHADER_STAGE_VERTEX_BIT, VK_SHADER_STAGE_TESSELLATION_CONTROL_BIT,
        VK_SHADER_STAGE_TESSELLATION_EVALUATION_BIT, VK_SHADER_STAGE_GEOMETRY_BIT, VK_SHADER_STAGE_FRAGMENT_BIT };
    VkShaderModule shaders[5];
    VkPipelineShaderStageCreateInfo stages[5];
    for (unsigned i = 0; i < 5; ++i) {
        VkShaderModuleCreateInfo info = { .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
            .codeSize = code_sizes[i], .pCode = codes[i] };
        CHECK(vkCreateShaderModule(device, &info, NULL, &shaders[i]));
        stages[i] = (VkPipelineShaderStageCreateInfo) { .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .stage = stage_bits[i], .module = shaders[i], .pName = "main" };
    }
    VkPipelineVertexInputStateCreateInfo vertex = { .sType = VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO };
    VkPipelineInputAssemblyStateCreateInfo assembly = { .sType = VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO };
    VkViewport viewport = { 0, 0, 8, 8, 0, 1 };
    VkRect2D scissor = { {0, 0}, {8, 8} };
    VkPipelineViewportStateCreateInfo viewport_info = { .sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO,
        .viewportCount = 1, .pViewports = &viewport, .scissorCount = 1, .pScissors = &scissor };
    VkPipelineRasterizationStateCreateInfo raster = { .sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
        .polygonMode = VK_POLYGON_MODE_FILL, .cullMode = VK_CULL_MODE_NONE, .frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE,
        .lineWidth = 1 };
    VkPipelineMultisampleStateCreateInfo samples = { .sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
        .rasterizationSamples = VK_SAMPLE_COUNT_1_BIT };
    VkPipelineColorBlendAttachmentState blend = { .colorWriteMask = 15 };
    VkPipelineColorBlendStateCreateInfo color = { .sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
        .attachmentCount = 1, .pAttachments = &blend };
    VkPipelineTessellationStateCreateInfo tess = { .sType = VK_STRUCTURE_TYPE_PIPELINE_TESSELLATION_STATE_CREATE_INFO,
        .patchControlPoints = 3 };
    VkCommandPoolCreateInfo command_pool_info = { .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .queueFamilyIndex = family };
    VkCommandPool command_pool;
    CHECK(vkCreateCommandPool(device, &command_pool_info, NULL, &command_pool));
    VkQueue queue;
    vkGetDeviceQueue(device, family, 0, &queue);
    int failed = 0;
    const char *names[] = { "geometry", "adjacency-without-gs", "tessellation-geometry" };
    for (unsigned test = 0; test < 3; ++test) {
        memset(mapped, 0, 512);
        VkPipelineShaderStageCreateInfo selected[5];
        unsigned count = 0;
        selected[count++] = stages[0];
        if (test == 2) { selected[count++] = stages[1]; selected[count++] = stages[2]; }
        if (test != 1) selected[count++] = stages[3];
        selected[count++] = stages[4];
        assembly.topology = test == 2 ? VK_PRIMITIVE_TOPOLOGY_PATCH_LIST :
            test == 1 ? VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST_WITH_ADJACENCY : VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
        VkGraphicsPipelineCreateInfo pipeline_info = { .sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO,
            .stageCount = count, .pStages = selected, .pVertexInputState = &vertex, .pInputAssemblyState = &assembly,
            .pTessellationState = test == 2 ? &tess : NULL, .pViewportState = &viewport_info,
            .pRasterizationState = &raster, .pMultisampleState = &samples, .pColorBlendState = &color,
            .layout = layout, .renderPass = render_pass };
        VkPipeline pipeline;
        CHECK(vkCreateGraphicsPipelines(device, VK_NULL_HANDLE, 1, &pipeline_info, NULL, &pipeline));
        VkCommandBufferAllocateInfo command_allocate = { .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
            .commandPool = command_pool, .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1 };
        VkCommandBuffer command;
        CHECK(vkAllocateCommandBuffers(device, &command_allocate, &command));
        VkCommandBufferBeginInfo begin = { .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO };
        CHECK(vkBeginCommandBuffer(command, &begin));
        VkImageMemoryBarrier image_barrier = { .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
            .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT, .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED,
            .newLayout = VK_IMAGE_LAYOUT_GENERAL, .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .image = images[1], .subresourceRange = range };
        vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
            0, 0, NULL, 0, NULL, 1, &image_barrier);
        VkClearColorValue zero = { .uint32 = {0, 0, 0, 0} };
        vkCmdClearColorImage(command, images[1], VK_IMAGE_LAYOUT_GENERAL, &zero, 1, &range);
        VkMemoryBarrier before = { .sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER,
            .srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT | VK_ACCESS_HOST_WRITE_BIT,
            .dstAccessMask = VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT };
        vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT | VK_PIPELINE_STAGE_HOST_BIT,
            VK_PIPELINE_STAGE_GEOMETRY_SHADER_BIT, 0, 1, &before, 0, NULL, 0, NULL);
        VkClearValue clear = { .color = { .float32 = {1, 0, 0, 1} } };
        VkRenderPassBeginInfo render_begin = { .sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO,
            .renderPass = render_pass, .framebuffer = framebuffer, .renderArea = scissor,
            .clearValueCount = 1, .pClearValues = &clear };
        vkCmdBeginRenderPass(command, &render_begin, VK_SUBPASS_CONTENTS_INLINE);
        vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
        vkCmdBindDescriptorSets(command, VK_PIPELINE_BIND_POINT_GRAPHICS, layout, 0, 1, &set, 0, NULL);
        uint32_t adjacency = test == 1;
        vkCmdPushConstants(command, layout, VK_SHADER_STAGE_VERTEX_BIT, 0, 4, &adjacency);
        vkCmdDraw(command, 6, 1, 0, 0);
        vkCmdEndRenderPass(command);
        VkMemoryBarrier after = { .sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER,
            .srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_TRANSFER_WRITE_BIT,
            .dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT | VK_ACCESS_HOST_READ_BIT };
        vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_GEOMETRY_SHADER_BIT | VK_PIPELINE_STAGE_TRANSFER_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT | VK_PIPELINE_STAGE_HOST_BIT, 0, 1, &after, 0, NULL, 0, NULL);
        VkBufferImageCopy copy = { .imageSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }, .imageExtent = {8, 8, 1} };
        vkCmdCopyImageToBuffer(command, images[0], VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, buffer, 1, &copy);
        copy.bufferOffset = 272;
        copy.imageExtent = (VkExtent3D) {3, 1, 1};
        vkCmdCopyImageToBuffer(command, images[1], VK_IMAGE_LAYOUT_GENERAL, buffer, 1, &copy);
        VkMemoryBarrier host = { .sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER,
            .srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT, .dstAccessMask = VK_ACCESS_HOST_READ_BIT };
        vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT,
            0, 1, &host, 0, NULL, 0, NULL);
        CHECK(vkEndCommandBuffer(command));
        VkSubmitInfo submit = { .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .commandBufferCount = 1, .pCommandBuffers = &command };
        CHECK(vkQueueSubmit(queue, 1, &submit, VK_NULL_HANDLE));
        CHECK(vkQueueWaitIdle(queue));
        int case_failed = 0;
        const unsigned char *pixels = mapped;
        for (unsigned i = 0; i < 64; ++i) {
            if (pixels[i*4] != 0 || pixels[i*4+1] != 255 || pixels[i*4+2] != 0 || pixels[i*4+3] != 255) {
                fprintf(stderr, "%s pixel %u: %u,%u,%u,%u\n", names[test], i,
                    pixels[i*4], pixels[i*4+1], pixels[i*4+2], pixels[i*4+3]);
                case_failed = 1;
                break;
            }
        }
        const uint32_t *counters = (const uint32_t *)((const char *)mapped + 256);
        unsigned expected_calls = test == 1 ? 0 : 2;
        unsigned minimum_invocations = test == 1 ? 0 : test == 2 ? 12 : 2;
        unsigned expected_ids = test == 1 ? 0 : 3;
        if (counters[0] != expected_calls || counters[1] != expected_ids || counters[4] != expected_calls ||
            counters[2] < minimum_invocations || (test == 1 && counters[2] != 0)) {
            fprintf(stderr, "%s side effects: calls=%u ids=0x%x image=%u expected=%u/0x%x/%u\n",
                names[test], counters[0], counters[1], counters[4], expected_calls, expected_ids, expected_calls);
            case_failed = 1;
        }
        for (unsigned i = 0; i < 2; ++i) {
            uint32_t expected = test == 1 ? 0 : (0xc0de0000u | i);
            if (counters[5+i] != expected) {
                fprintf(stderr, "%s image store [%u]: 0x%x expected 0x%x\n",
                    names[test], i, counters[5+i], expected);
                case_failed = 1;
            }
        }
        printf("%s observed geometry invocations=%u\n", names[test], counters[2]);
        if (!case_failed) printf("%s rendering and side-effect readback passed\n", names[test]);
        failed |= case_failed;
        vkDestroyPipeline(device, pipeline, NULL);
    }
    vkDestroyCommandPool(device, command_pool, NULL);
    vkDestroyFramebuffer(device, framebuffer, NULL);
    vkDestroyRenderPass(device, render_pass, NULL);
    for (unsigned i = 0; i < 5; ++i) vkDestroyShaderModule(device, shaders[i], NULL);
    vkDestroyPipelineLayout(device, layout, NULL);
    vkDestroyDescriptorPool(device, descriptor_pool, NULL);
    vkDestroyDescriptorSetLayout(device, set_layout, NULL);
    for (unsigned i = 0; i < 2; ++i) {
        vkDestroyImageView(device, views[i], NULL);
        vkDestroyImage(device, images[i], NULL);
        vkFreeMemory(device, image_memory[i], NULL);
    }
    vkUnmapMemory(device, memory);
    vkDestroyBuffer(device, buffer, NULL);
    vkFreeMemory(device, memory, NULL);
    return failed;
}
