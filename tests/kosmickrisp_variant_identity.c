#include "kosmickrisp/vulkan/kk_shader.h"
#include "util/u_atomic.h"

#include <assert.h>
#include <pthread.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

struct identity_thread {
   struct kk_shader *shader;
   blake3_hash expected;
};

static void *
identity_worker(void *arg)
{
   struct identity_thread *data = arg;
   for (unsigned i = 0; i < 1000; i++) {
      blake3_hash identity;
      kk_shader_variant_identity(data->shader, identity);
      assert(!memcmp(identity, data->expected, sizeof(identity)));
   }
   return NULL;
}

static void
identity_reset(struct kk_shader *shader)
{
   p_atomic_set(&shader->variant_identity_ready, 0);
   memset(shader->variant_identity, 0, sizeof(blake3_hash));
}

int
main(void)
{
   struct kk_shader a = {0}, b = {0};
   mtx_init(&a.variants_lock, mtx_plain);
   mtx_init(&b.variants_lock, mtx_plain);
   a.info.stage = b.info.stage = MESA_SHADER_FRAGMENT;
   a.info.partial = b.info.partial = true;
   memset(a.fast.hash, 1, sizeof(blake3_hash));
   memset(b.fast.hash, 1, sizeof(blake3_hash));
   a.nir_blob = b.nir_blob = "NIR-A";
   a.nir_blob_size = b.nir_blob_size = 5;
   a.msl_data[MESA_SHADER_FRAGMENT] =
      b.msl_data[MESA_SHADER_FRAGMENT] =
         (struct msl_compile_data){"same MSL", "main"};
   blake3_hash first, second;
   kk_shader_variant_identity(&a, first);
   kk_shader_variant_identity(&b, second);
   assert(!memcmp(first, second, sizeof(first)));
   b.nir_blob = "NIR-B";
   identity_reset(&b);
   kk_shader_variant_identity(&b, second);
   assert(memcmp(first, second, sizeof(first)));
   b.nir_blob = a.nir_blob;
   b.msl_data[MESA_SHADER_FRAGMENT].entrypoint_name = "other";
   identity_reset(&b);
   kk_shader_variant_identity(&b, second);
   assert(memcmp(first, second, sizeof(first)));
   b.msl_data[MESA_SHADER_FRAGMENT] = a.msl_data[MESA_SHADER_FRAGMENT];
   b.info.fs.ms_static = true;
   identity_reset(&b);
   kk_shader_variant_identity(&b, second);
   assert(memcmp(first, second, sizeof(first)));
   b.info.fs.ms_static = false;
   b.msl_points = (struct msl_compile_data){"point MSL", "point_main"};
   identity_reset(&b);
   kk_shader_variant_identity(&b, second);
   assert(memcmp(first, second, sizeof(first)));
   b.msl_points = (struct msl_compile_data){0};
   size_t start = offsetof(struct kk_shader_info, rast_point_variant) + sizeof(bool);
   size_t end = offsetof(struct kk_shader_info, rast_outputs_written);
   assert(end > start);
   memset((uint8_t *)&b.info + start, 0xa5, end - start);
   identity_reset(&b);
   kk_shader_variant_identity(&b, second);
   assert(!memcmp(first, second, sizeof(first)));
   identity_reset(&a);
   pthread_t threads[16];
   struct identity_thread data = {.shader = &a};
   memcpy(data.expected, first, sizeof(first));
   for (unsigned i = 0; i < 16; i++)
      assert(!pthread_create(&threads[i], NULL, identity_worker, &data));
   for (unsigned i = 0; i < 16; i++)
      assert(!pthread_join(threads[i], NULL));
   mtx_destroy(&a.variants_lock);
   mtx_destroy(&b.variants_lock);
   puts("PASS NIR, entrypoint, static state, point source, padding, concurrent publication");
   return 0;
}
