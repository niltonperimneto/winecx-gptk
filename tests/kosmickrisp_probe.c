            fprintf(stderr, "KosmicKrisp must expose Vulkan 1.4 or newer\n");
            return 1;
        }
        ++found;
        VkPhysicalDeviceVulkan13Features f13 = {
            .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES };
        VkPhysicalDeviceVulkan12Features f12 = {
            .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES, .pNext = &f13 };
        VkPhysicalDeviceFeatures2 features = {
            .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, .pNext = &f12 };
        vkGetPhysicalDeviceFeatures2(devices[i], &features);
        printf("api=%u.%u.%u maxPushConstantsSize=%u\n",
            VK_API_VERSION_MAJOR(props.properties.apiVersion),
            VK_API_VERSION_MINOR(props.properties.apiVersion),
            VK_API_VERSION_PATCH(props.properties.apiVersion), props.properties.limits.maxPushConstantsSize);
        printf("geometryShader=%u tessellationShader=%u shaderInt64=%u\n",
            features.features.geometryShader, features.features.tessellationShader,
            features.features.shaderInt64);
        printf("fillModeNonSolid=%u\n", features.features.fillModeNonSolid);
        printf("descriptorIndexing=%u scalarBlockLayout=%u shaderInt8=%u synchronization2=%u\n",
            f12.descriptorIndexing, f12.scalarBlockLayout, f12.shaderInt8, f13.synchronization2);

        uint32_t extension_count = 0;