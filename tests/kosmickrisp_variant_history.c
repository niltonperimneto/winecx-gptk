#include "kosmickrisp/vulkan/kk_variant_history.h"
#include "util/disk_cache.h"
#include "util/disk_cache_os.h"

#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct item {
   cache_key key;
   void *data;
   size_t size;
   struct item *next;
};

struct mock_disk {
   struct disk_cache disk;
   pthread_mutex_t mutex;
   struct item *items;
   unsigned writes;
   unsigned drains;
   bool drop_writes;
};

static _Thread_local bool recording;

void
disk_cache_compute_key(struct disk_cache *disk, const void *data, size_t size,
                       cache_key key)
{
   assert(!recording);
   const uint8_t *bytes = data;
   memset(key, 0, CACHE_KEY_SIZE);
   for (size_t i = 0; i < size; i++)
      key[i % CACHE_KEY_SIZE] = key[i % CACHE_KEY_SIZE] * 33 + bytes[i];
}

void *
disk_cache_get(struct disk_cache *disk, const cache_key key, size_t *size)
{
   assert(!recording);
   struct mock_disk *mock = (struct mock_disk *)disk;
   pthread_mutex_lock(&mock->mutex);
   void *data = NULL;
   for (struct item *item = mock->items; item; item = item->next) {
      if (!memcmp(item->key, key, CACHE_KEY_SIZE)) {
         data = malloc(item->size);
         assert(data);
         memcpy(data, item->data, item->size);
         *size = item->size;
         break;
      }
   }
   pthread_mutex_unlock(&mock->mutex);
   return data;
}

void
disk_cache_put(struct disk_cache *disk, const cache_key key,
               const void *data, size_t size, struct cache_item_metadata *metadata)
{
   assert(!recording);
   struct mock_disk *mock = (struct mock_disk *)disk;
   pthread_mutex_lock(&mock->mutex);
   if (mock->drop_writes) {
      pthread_mutex_unlock(&mock->mutex);
      return;
   }
   struct item *item = mock->items;
   while (item && memcmp(item->key, key, CACHE_KEY_SIZE))
      item = item->next;
   if (!item) {
      item = calloc(1, sizeof(*item));
      assert(item);
      memcpy(item->key, key, CACHE_KEY_SIZE);
      item->next = mock->items;
      mock->items = item;
   }
   if (item->data) {
      pthread_mutex_unlock(&mock->mutex);
      return;
   }
   item->data = malloc(size);
   assert(item->data);
   memcpy(item->data, data, size);
   item->size = size;
   mock->writes++;
   pthread_mutex_unlock(&mock->mutex);
}

void
disk_cache_remove(struct disk_cache *disk, const cache_key key)
{
   assert(!recording);
   struct mock_disk *mock = (struct mock_disk *)disk;
   pthread_mutex_lock(&mock->mutex);
   struct item **previous = &mock->items;
   while (*previous && memcmp((*previous)->key, key, CACHE_KEY_SIZE))
      previous = &(*previous)->next;
   if (*previous) {
      struct item *item = *previous;
      *previous = item->next;
      free(item->data);
      free(item);
   }
   pthread_mutex_unlock(&mock->mutex);
}

void
disk_cache_wait_for_idle(struct disk_cache *disk)
{
   assert(!recording);
   struct mock_disk *mock = (struct mock_disk *)disk;
   mock->drains++;
}

static void
record(struct kk_variant_history *history, const uint8_t family[32], uint32_t value)
{
   recording = true;
   kk_variant_history_record(history, family, &value);
   recording = false;
}

static struct kk_variant_history *
create(struct mock_disk *mock)
{
   struct kk_variant_history *history =
      kk_variant_history_create((struct disk_cache *)mock, sizeof(uint32_t));
   assert(history);
   return history;
}

static void
persistence(struct mock_disk *mock)
{
   uint8_t family[32] = {1};
   struct kk_variant_history *history = create(mock);
   record(history, family, 7);
   record(history, family, 8);
   record(history, family, 7);
   kk_variant_history_destroy(history);
   assert(mock->writes && mock->drains >= 1);
   history = create(mock);
   uint32_t values[32] = {0};
   assert(kk_variant_history_load(history, family, values, 32) == 2);
   assert(values[0] == 7 && values[1] == 8);
   assert(kk_variant_history_load(history, family, values, 1) == 1);
   assert(values[0] == 7);
   kk_variant_history_destroy(history);
}

static void
merge(struct mock_disk *mock)
{
   uint8_t family[32] = {1};
   struct kk_variant_history *history = create(mock);
   record(history, family, 7);
   record(history, family, 8);
   kk_variant_history_destroy(history);
   history = create(mock);
   record(history, family, 9);
   record(history, family, 8);
   kk_variant_history_destroy(history);
   history = create(mock);
   uint32_t values[32] = {0};
   assert(kk_variant_history_load(history, family, values, 32) == 3);
   assert(values[0] == 7 && values[1] == 8 && values[2] == 9);
   kk_variant_history_destroy(history);
}

static void
update(struct mock_disk *mock)
{
   uint8_t family[32] = {1};
   struct kk_variant_history *history = create(mock);
   record(history, family, 15);
   kk_variant_history_destroy(history);
   history = create(mock);
   uint32_t values[32];
   assert(kk_variant_history_load(history, family, values, 32) == 1);
   assert(values[0] == 15);
   record(history, family, 5);
   kk_variant_history_destroy(history);
   history = create(mock);
   assert(kk_variant_history_load(history, family, values, 32) == 2);
   assert(values[0] == 15 && values[1] == 5);
   kk_variant_history_destroy(history);
}

static void
interrupted(struct mock_disk *mock)
{
   uint8_t family[32] = {1};
   struct kk_variant_history *history = create(mock);
   record(history, family, 15);
   kk_variant_history_destroy(history);
   mock->drop_writes = true;
   history = create(mock);
   record(history, family, 5);
   kk_variant_history_destroy(history);
   mock->drop_writes = false;
   history = create(mock);
   uint32_t values[32];
   assert(kk_variant_history_load(history, family, values, 32) == 0);
   record(history, family, 5);
   kk_variant_history_destroy(history);
   history = create(mock);
   assert(kk_variant_history_load(history, family, values, 32) == 1);
   assert(values[0] == 5);
   kk_variant_history_destroy(history);
}

static void
corruption(struct mock_disk *mock)
{
   uint8_t family[32] = {1};
   struct kk_variant_history *history = create(mock);
   record(history, family, 7);
   kk_variant_history_destroy(history);
   struct item *item = mock->items;
   size_t size = item->size;
   uint8_t *original = malloc(size);
   assert(original);
   memcpy(original, item->data, size);
   const unsigned positions[] = {0, 8, 12, 16, 20, 24, 32};
   for (unsigned i = 0; i < sizeof(positions) / sizeof(positions[0]); i++) {
      memcpy(item->data, original, size);
      memset((uint8_t *)item->data + positions[i], positions[i] == 24 ? 0 : 0xff,
             positions[i] >= 24 ? 8 : 4);
      history = create(mock);
      uint32_t values[32];
      assert(kk_variant_history_load(history, family, values, 32) == 0);
      kk_variant_history_destroy(history);
   }
   memcpy(item->data, original, size);
   for (size_t truncated = 0; truncated < size; truncated++) {
      item->size = truncated;
      history = create(mock);
      uint32_t values[32];
      assert(kk_variant_history_load(history, family, values, 32) == 0);
      kk_variant_history_destroy(history);
   }
   item->size = size;
   free(original);
}

static void
duplicate_blob(struct mock_disk *mock)
{
   uint8_t family[32] = {1};
   struct kk_variant_history *history = create(mock);
   record(history, family, 7);
   kk_variant_history_destroy(history);
   struct item *item = mock->items;
   size_t entry_size = item->size - 24;
   item->data = realloc(item->data, item->size + entry_size);
   assert(item->data);
   memcpy((uint8_t *)item->data + item->size,
          (uint8_t *)item->data + 24, entry_size);
   item->size += entry_size;
   ((uint8_t *)item->data)[16] = 2;
   history = create(mock);
   uint32_t values[32];
   assert(kk_variant_history_load(history, family, values, 32) == 1);
   assert(values[0] == 7);
   record(history, family, 8);
   kk_variant_history_destroy(history);
   history = create(mock);
   assert(kk_variant_history_load(history, family, values, 32) == 2);
   assert(values[0] == 7 && values[1] == 8);
   kk_variant_history_destroy(history);
}

static void
capacity(struct mock_disk *mock)
{
   uint8_t family[32] = {1};
   struct kk_variant_history *history = create(mock);
   for (unsigned i = 0; i < 100; i++)
      record(history, family, 999);
   for (unsigned i = 0; i < 1000; i++)
      record(history, family, i);
   kk_variant_history_destroy(history);
   history = create(mock);
   uint32_t values[32];
   unsigned count = kk_variant_history_load(history, family, values, 32);
   assert(count == 32);
   bool found = false;
   for (unsigned i = 0; i < count; i++) {
      found |= values[i] == 999;
      for (unsigned j = 0; j < i; j++)
         assert(values[i] != values[j]);
   }
   assert(found);
   kk_variant_history_destroy(history);
}

struct thread_data {
   struct kk_variant_history *history;
   unsigned index;
};

static void *
concurrent_record(void *arg)
{
   struct thread_data *data = arg;
   uint8_t family[32] = {1};
   for (unsigned i = 0; i < 500; i++) {
      record(data->history, family, data->index);
      uint32_t values[32];
      assert(kk_variant_history_load(data->history, family, values, 32) <= 16);
      uint8_t other[32] = {0};
      uint32_t index = data->index * 500 + i;
      memcpy(other, &index, sizeof(index));
      other[31] = 255;
      record(data->history, other, index);
   }
   return NULL;
}

static void
concurrency(struct mock_disk *mock)
{
   struct kk_variant_history *history = create(mock);
   pthread_t threads[16];
   struct thread_data data[16];
   for (unsigned i = 0; i < 16; i++) {
      data[i] = (struct thread_data){history, i};
      assert(!pthread_create(&threads[i], NULL, concurrent_record, &data[i]));
   }
   for (unsigned i = 0; i < 16; i++)
      assert(!pthread_join(threads[i], NULL));
   kk_variant_history_destroy(history);
   history = create(mock);
   uint8_t family[32] = {1};
   uint32_t values[32];
   assert(kk_variant_history_load(history, family, values, 32) == 16);
   kk_variant_history_destroy(history);
}

static void
disabled(struct mock_disk *mock)
{
   uint8_t family[32] = {1};
   uint32_t value = 1;
   assert(!kk_variant_history_create(NULL, 4));
   assert(!kk_variant_history_create((struct disk_cache *)mock, 0));
   assert(!kk_variant_history_create((struct disk_cache *)mock, 4097));
   mock->disk.type = DISK_CACHE_SINGLE_FILE;
   assert(!kk_variant_history_create((struct disk_cache *)mock, 4));
   mock->disk.type = DISK_CACHE_NONE;
   assert(!kk_variant_history_create((struct disk_cache *)mock, 4));
   mock->disk.type = DISK_CACHE_MULTI_FILE;
   kk_variant_history_record(NULL, family, &value);
   assert(!kk_variant_history_load(NULL, family, &value, 1));
   kk_variant_history_destroy(NULL);
   struct kk_variant_history *history = create(mock);
   kk_variant_history_record(history, NULL, &value);
   kk_variant_history_record(history, family, NULL);
   assert(!kk_variant_history_load(history, NULL, &value, 1));
   assert(!kk_variant_history_load(history, family, NULL, 1));
   assert(!kk_variant_history_load(history, family, &value, 0));
   kk_variant_history_destroy(history);
   assert(!mock->writes);
}

int
main(int argc, char **argv)
{
   assert(argc == 2);
   struct mock_disk mock = {
      .disk.type = DISK_CACHE_MULTI_FILE,
      .mutex = PTHREAD_MUTEX_INITIALIZER,
   };
   if (!strcmp(argv[1], "persistence"))
      persistence(&mock);
   else if (!strcmp(argv[1], "merge"))
      merge(&mock);
   else if (!strcmp(argv[1], "update"))
      update(&mock);
   else if (!strcmp(argv[1], "database_update")) {
      mock.disk.type = DISK_CACHE_DATABASE;
      update(&mock);
   }
   else if (!strcmp(argv[1], "interrupted"))
      interrupted(&mock);
   else if (!strcmp(argv[1], "corruption"))
      corruption(&mock);
   else if (!strcmp(argv[1], "duplicate_blob"))
      duplicate_blob(&mock);
   else if (!strcmp(argv[1], "capacity"))
      capacity(&mock);
   else if (!strcmp(argv[1], "concurrency"))
      concurrency(&mock);
   else if (!strcmp(argv[1], "disabled"))
      disabled(&mock);
   else
      abort();
   while (mock.items) {
      struct item *item = mock.items;
      mock.items = item->next;
      free(item->data);
      free(item);
   }
   pthread_mutex_destroy(&mock.mutex);
   puts("PASS");
   return 0;
}
