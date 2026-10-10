#include "kosmickrisp_idle_layer.c"
#include <assert.h>
#include <stdatomic.h>

static atomic_uint idle_count;
static atomic_uint present_count;
static VkResult idle_result = VK_SUCCESS;

static VkResult
fake_instance(const VkInstanceCreateInfo *info, const VkAllocationCallbacks *alloc,
              VkInstance *handle)
{
   (void)info;
   (void)alloc;
   *handle = (VkInstance)(uintptr_t)1;
   return VK_SUCCESS;
}

static void
fake_destroy_instance(VkInstance handle, const VkAllocationCallbacks *alloc)
{
   (void)handle;
   (void)alloc;
}

static VkResult
fake_device(VkPhysicalDevice physical, const VkDeviceCreateInfo *info,
            const VkAllocationCallbacks *alloc, VkDevice *handle)
{
   (void)physical;
   (void)info;
   (void)alloc;
   *handle = (VkDevice)(uintptr_t)2;
   return VK_SUCCESS;
}

static void
fake_destroy_device(VkDevice handle, const VkAllocationCallbacks *alloc)
{
   (void)handle;
   (void)alloc;
}

static void
fake_queue(VkDevice device, uint32_t family, uint32_t index, VkQueue *queue)
{
   (void)device;
   (void)family;
   *queue = (VkQueue)(uintptr_t)(3 + index);
}

static void
fake_queue2(VkDevice device, const VkDeviceQueueInfo2 *info, VkQueue *queue)
{
   fake_queue(device, info->queueFamilyIndex, info->queueIndex, queue);
}

static VkResult
fake_present(VkQueue queue, const VkPresentInfoKHR *info)
{
   (void)queue;
   (void)info;
   present_count++;
   return VK_SUCCESS;
}

static VkResult
fake_idle(VkQueue queue)
{
   (void)queue;
   idle_count++;
   return idle_result;
}

static PFN_vkVoidFunction
fake_gipa(VkInstance handle, const char *name)
{
   (void)handle;
   if (!strcmp(name, "vkCreateInstance")) return (void *)fake_instance;
   if (!strcmp(name, "vkDestroyInstance")) return (void *)fake_destroy_instance;
   if (!strcmp(name, "vkCreateDevice")) return (void *)fake_device;
   return NULL;
}

static PFN_vkVoidFunction
fake_gdpa(VkDevice handle, const char *name)
{
   (void)handle;
   if (!strcmp(name, "vkDestroyDevice")) return (void *)fake_destroy_device;
   if (!strcmp(name, "vkGetDeviceQueue")) return (void *)fake_queue;
   if (!strcmp(name, "vkGetDeviceQueue2")) return (void *)fake_queue2;
   if (!strcmp(name, "vkQueuePresentKHR")) return (void *)fake_present;
   if (!strcmp(name, "vkQueueWaitIdle")) return (void *)fake_idle;
   return NULL;
}

static int
present_thread(void *data)
{
   VkPresentInfoKHR info = {.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR};
   return vkQueuePresentKHR(*(VkQueue *)data, &info);
}

int
main(int argc, char **argv)
{
   assert(argc == 2);
   assert(setenv("KK_TEST_IDLE_TRIGGER", argv[1], 1) == 0);
   unlink(argv[1]);
   VkLayerInstanceLink instance_link = {.pfnNextGetInstanceProcAddr = fake_gipa};
   VkLayerInstanceCreateInfo instance_chain = {
      .sType = VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO,
      .function = VK_LAYER_LINK_INFO, .u.pLayerInfo = &instance_link};
   VkInstanceCreateInfo instance_info = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
                                        .pNext = &instance_chain};
   VkInstance handle;
   assert(vkCreateInstance(&instance_info, NULL, &handle) == VK_SUCCESS);
   instance_chain.u.pLayerInfo = &instance_link;
   VkInstance duplicate;
   assert(vkCreateInstance(&instance_info, NULL, &duplicate) == VK_ERROR_INITIALIZATION_FAILED);
   for (unsigned iteration = 0; iteration < 3; ++iteration) {
      VkLayerDeviceLink device_link = {.pfnNextGetDeviceProcAddr = fake_gdpa};
      VkLayerDeviceCreateInfo device_chain = {
         .sType = VK_STRUCTURE_TYPE_LOADER_DEVICE_CREATE_INFO,
         .function = VK_LAYER_LINK_INFO, .u.pLayerInfo = &device_link};
      VkDeviceCreateInfo device_info = {.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
                                       .pNext = &device_chain};
      VkDevice device;
      assert(vkCreateDevice((VkPhysicalDevice)(uintptr_t)5, &device_info, NULL,
                            &device) == VK_SUCCESS);
      VkQueue queue, queue2;
      vkGetDeviceQueue(device, 0, 0, &queue);
      VkDeviceQueueInfo2 queue_info = {.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_INFO_2,
                                     .queueIndex = 1};
      vkGetDeviceQueue2(device, &queue_info, &queue2);
      VkPresentInfoKHR present = {.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR};
      if (!iteration) {
         assert(vkQueuePresentKHR(queue, &present) == VK_SUCCESS);
         assert(idle_count == 0);
         FILE *trigger = fopen(argv[1], "w");
         assert(trigger);
         fclose(trigger);
      } else if (iteration == 1) {
         idle_result = VK_ERROR_DEVICE_LOST;
      } else {
         idle_result = VK_SUCCESS;
         thrd_t first, second;
         assert(thrd_create(&first, present_thread, &queue) == thrd_success);
         assert(thrd_create(&second, present_thread, &queue2) == thrd_success);
         int first_status, second_status;
         assert(thrd_join(first, &first_status) == thrd_success);
         assert(thrd_join(second, &second_status) == thrd_success);
         assert(first_status == VK_SUCCESS && second_status == VK_SUCCESS);
         assert(idle_count == 3);
         vkDestroyDevice(device, NULL);
         assert(!devices && !queues);
         continue;
      }
      unsigned before = present_count;
      assert(vkQueuePresentKHR(queue, &present) == idle_result);
      assert(idle_count == iteration + 1);
      assert(present_count == before + !iteration);
      assert(vkQueuePresentKHR(queue2, &present) == VK_SUCCESS);
      assert(idle_count == iteration + 1);
      vkDestroyDevice(device, NULL);
      assert(!devices && !queues);
   }
   vkDestroyInstance(handle, NULL);
   assert(!instance);
   unlink(argv[1]);
   puts("idle layer forwarding, single checkpoint, failure and cleanup passed");
   return 0;
}
