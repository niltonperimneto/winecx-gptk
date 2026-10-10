#include <vulkan/vk_layer.h>
#include "c11/threads.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

struct device_entry {
   VkDevice device;
   PFN_vkGetDeviceProcAddr gdpa;
   PFN_vkDestroyDevice destroy;
   PFN_vkGetDeviceQueue get_queue;
   PFN_vkGetDeviceQueue2 get_queue2;
   PFN_vkQueuePresentKHR present;
   PFN_vkQueueWaitIdle idle;
   bool checkpoint;
   struct device_entry *next;
};

struct queue_entry {
   VkQueue queue;
   struct device_entry *device;
   struct queue_entry *next;
};

static once_flag once = ONCE_FLAG_INIT;
static mtx_t lock;
static VkInstance instance;
static bool creating_instance;
static PFN_vkGetInstanceProcAddr next_gipa;
static struct device_entry *devices;
static struct queue_entry *queues;

static void
initialize(void)
{
   if (mtx_init(&lock, mtx_plain) != thrd_success)
      abort();
}

static uint64_t
clock_ns(void)
{
   struct timespec ts;
   clock_gettime(CLOCK_MONOTONIC, &ts);
   return (uint64_t)ts.tv_sec * 1000000000 + ts.tv_nsec;
}

static struct device_entry *
find_device(VkDevice device)
{
   struct device_entry *entry = devices;
   while (entry && entry->device != device)
      entry = entry->next;
   return entry;
}

static void
record_queue(VkQueue queue, struct device_entry *device)
{
   mtx_lock(&lock);
   for (struct queue_entry *entry = queues; entry; entry = entry->next) {
      if (entry->queue == queue) {
         mtx_unlock(&lock);
         return;
      }
   }
   struct queue_entry *entry = calloc(1, sizeof(*entry));
   if (!entry)
      abort();
   *entry = (struct queue_entry){queue, device, queues};
   queues = entry;
   mtx_unlock(&lock);
}

VKAPI_ATTR VkResult VKAPI_CALL
vkCreateInstance(const VkInstanceCreateInfo *info,
                 const VkAllocationCallbacks *allocator, VkInstance *result)
{
   call_once(&once, initialize);
   VkLayerInstanceCreateInfo *chain = (void *)info->pNext;
   while (chain && (chain->sType != VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO ||
                    chain->function != VK_LAYER_LINK_INFO))
      chain = (void *)chain->pNext;
   if (!chain)
      return VK_ERROR_INITIALIZATION_FAILED;
   mtx_lock(&lock);
   if (instance || creating_instance) {
      mtx_unlock(&lock);
      return VK_ERROR_INITIALIZATION_FAILED;
   }
   creating_instance = true;
   mtx_unlock(&lock);
   next_gipa = chain->u.pLayerInfo->pfnNextGetInstanceProcAddr;
   PFN_vkCreateInstance create = (void *)next_gipa(VK_NULL_HANDLE, "vkCreateInstance");
   chain->u.pLayerInfo = chain->u.pLayerInfo->pNext;
   VkResult status = create(info, allocator, result);
   mtx_lock(&lock);
   if (status == VK_SUCCESS)
      instance = *result;
   creating_instance = false;
   mtx_unlock(&lock);
   return status;
}

VKAPI_ATTR void VKAPI_CALL
vkDestroyInstance(VkInstance handle, const VkAllocationCallbacks *allocator)
{
   PFN_vkDestroyInstance destroy = (void *)next_gipa(handle, "vkDestroyInstance");
   destroy(handle, allocator);
   mtx_lock(&lock);
   instance = VK_NULL_HANDLE;
   mtx_unlock(&lock);
}

VKAPI_ATTR VkResult VKAPI_CALL
vkCreateDevice(VkPhysicalDevice physical, const VkDeviceCreateInfo *info,
               const VkAllocationCallbacks *allocator, VkDevice *result)
{
   VkLayerDeviceCreateInfo *chain = (void *)info->pNext;
   while (chain && (chain->sType != VK_STRUCTURE_TYPE_LOADER_DEVICE_CREATE_INFO ||
                    chain->function != VK_LAYER_LINK_INFO))
      chain = (void *)chain->pNext;
   if (!chain)
      return VK_ERROR_INITIALIZATION_FAILED;
   PFN_vkGetDeviceProcAddr gdpa = chain->u.pLayerInfo->pfnNextGetDeviceProcAddr;
   PFN_vkCreateDevice create = (void *)next_gipa(instance, "vkCreateDevice");
   chain->u.pLayerInfo = chain->u.pLayerInfo->pNext;
   struct device_entry *entry = calloc(1, sizeof(*entry));
   if (!entry)
      return VK_ERROR_OUT_OF_HOST_MEMORY;
   VkResult status = create(physical, info, allocator, result);
   if (status != VK_SUCCESS) {
      free(entry);
      return status;
   }
   entry->device = *result;
   entry->gdpa = gdpa;
   entry->destroy = (void *)gdpa(*result, "vkDestroyDevice");
   entry->get_queue = (void *)gdpa(*result, "vkGetDeviceQueue");
   entry->get_queue2 = (void *)gdpa(*result, "vkGetDeviceQueue2");
   entry->present = (void *)gdpa(*result, "vkQueuePresentKHR");
   entry->idle = (void *)gdpa(*result, "vkQueueWaitIdle");
   mtx_lock(&lock);
   entry->next = devices;
   devices = entry;
   mtx_unlock(&lock);
   fprintf(stderr, "KK_TEST_IDLE_LAYER device_created\n");
   return status;
}

VKAPI_ATTR void VKAPI_CALL
vkGetDeviceQueue(VkDevice device, uint32_t family, uint32_t index, VkQueue *queue)
{
   mtx_lock(&lock);
   struct device_entry *entry = find_device(device);
   mtx_unlock(&lock);
   entry->get_queue(device, family, index, queue);
   record_queue(*queue, entry);
}

VKAPI_ATTR void VKAPI_CALL
vkGetDeviceQueue2(VkDevice device, const VkDeviceQueueInfo2 *info, VkQueue *queue)
{
   mtx_lock(&lock);
   struct device_entry *entry = find_device(device);
   mtx_unlock(&lock);
   entry->get_queue2(device, info, queue);
   if (*queue)
      record_queue(*queue, entry);
}

VKAPI_ATTR VkResult VKAPI_CALL
vkQueuePresentKHR(VkQueue queue, const VkPresentInfoKHR *info)
{
   const char *trigger = getenv("KK_TEST_IDLE_TRIGGER");
   mtx_lock(&lock);
   struct queue_entry *entry = queues;
   while (entry && entry->queue != queue)
      entry = entry->next;
   if (!entry) {
      mtx_unlock(&lock);
      return VK_ERROR_INITIALIZATION_FAILED;
   }
   struct device_entry *device = entry->device;
   bool checkpoint = !device->checkpoint && trigger && access(trigger, F_OK) == 0;
   device->checkpoint |= checkpoint;
   mtx_unlock(&lock);
   if (checkpoint) {
      uint64_t start = clock_ns();
      VkResult status = device->idle(queue);
      fprintf(stderr, "KK_TEST_IDLE_LAYER checkpoint start_ns=%llu end_ns=%llu result=%d\n",
              (unsigned long long)start, (unsigned long long)clock_ns(), status);
      if (status != VK_SUCCESS)
         return status;
   }
   return device->present(queue, info);
}

VKAPI_ATTR void VKAPI_CALL
vkDestroyDevice(VkDevice device, const VkAllocationCallbacks *allocator)
{
   mtx_lock(&lock);
   struct device_entry **link = &devices;
   while (*link && (*link)->device != device)
      link = &(*link)->next;
   struct device_entry *entry = *link;
   if (entry)
      *link = entry->next;
   for (struct queue_entry **q = &queues; *q;) {
      if ((*q)->device == entry) {
         struct queue_entry *old = *q;
         *q = old->next;
         free(old);
      } else {
         q = &(*q)->next;
      }
   }
   mtx_unlock(&lock);
   if (entry) {
      entry->destroy(device, allocator);
      free(entry);
   }
}

VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
vkGetDeviceProcAddr(VkDevice device, const char *name)
{
#define RETURN_PROC(n) if (strcmp(name, #n) == 0) return (PFN_vkVoidFunction)n
   RETURN_PROC(vkGetDeviceProcAddr);
   RETURN_PROC(vkGetDeviceQueue);
   RETURN_PROC(vkGetDeviceQueue2);
   RETURN_PROC(vkQueuePresentKHR);
   RETURN_PROC(vkDestroyDevice);
#undef RETURN_PROC
   mtx_lock(&lock);
   struct device_entry *entry = find_device(device);
   mtx_unlock(&lock);
   return entry ? entry->gdpa(device, name) : NULL;
}

VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
vkGetInstanceProcAddr(VkInstance handle, const char *name)
{
#define RETURN_PROC(n) if (strcmp(name, #n) == 0) return (PFN_vkVoidFunction)n
   RETURN_PROC(vkGetInstanceProcAddr);
   RETURN_PROC(vkGetDeviceProcAddr);
   RETURN_PROC(vkCreateInstance);
   RETURN_PROC(vkDestroyInstance);
   RETURN_PROC(vkCreateDevice);
   RETURN_PROC(vkGetDeviceQueue);
   RETURN_PROC(vkGetDeviceQueue2);
   RETURN_PROC(vkQueuePresentKHR);
   RETURN_PROC(vkDestroyDevice);
#undef RETURN_PROC
   return next_gipa ? next_gipa(handle, name) : NULL;
}

VKAPI_ATTR VkResult VKAPI_CALL
vkNegotiateLoaderLayerInterfaceVersion(VkNegotiateLayerInterface *version)
{
   if (version->loaderLayerInterfaceVersion > 2)
      version->loaderLayerInterfaceVersion = 2;
   version->pfnGetInstanceProcAddr = vkGetInstanceProcAddr;
   version->pfnGetDeviceProcAddr = vkGetDeviceProcAddr;
   version->pfnGetPhysicalDeviceProcAddr = NULL;
   return VK_SUCCESS;
}
