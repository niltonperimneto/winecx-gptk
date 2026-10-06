#include <stdio.h>
#include <stdlib.h>
#include "kk_descriptor_set_layout.h"
#include "kk_shader.h"
#include "nir_builder.h"
#include "util/blob.h"
#include "vk_pipeline.h"
#include "nir_serialize.h"
static const nir_shader_compiler_options options = {0};
int main(int argc, char **argv)
{
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_FRAGMENT, &options, "descriptor_replay");
   nir_def *index = nir_vulkan_resource_index(&b, 3, 32, nir_imm_int(&b, 0), .desc_set = 0, .binding = 0, .desc_type = nir_descriptor_type_uniform_buffer);
   nir_def *desc = nir_load_vulkan_descriptor(&b, 4, 32, index, .desc_type = nir_descriptor_type_uniform_buffer);
   nir_store_output(&b, desc, nir_imm_int(&b, 0), .write_mask = 15, .src_type = nir_type_uint32, .io_semantics = { .location = FRAG_RESULT_DATA0, .num_slots = 1 });
   struct kk_descriptor_set_layout *layout = calloc(1, sizeof(*layout) + sizeof(layout->binding[0]));
   layout->binding_count = 1;
   layout->binding[0].type = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
   layout->binding[0].array_size = 1;
   layout->binding[0].stride = 16;
   struct vk_descriptor_set_layout *layouts[] = { &layout->vk };
   struct vk_pipeline_robustness_state rs = {
      .storage_buffers = VK_PIPELINE_ROBUSTNESS_BUFFER_BEHAVIOR_DISABLED,
      .uniform_buffers = VK_PIPELINE_ROBUSTNESS_BUFFER_BEHAVIOR_DISABLED,
      .vertex_inputs = VK_PIPELINE_ROBUSTNESS_BUFFER_BEHAVIOR_DISABLED,
      .images = VK_PIPELINE_ROBUSTNESS_IMAGE_BEHAVIOR_DISABLED,
   };
   kk_nir_lower_descriptors(b.shader, &rs, 1, layouts);
   struct blob blob;
   blob_init(&blob);
   nir_serialize(&blob, b.shader, false);
   struct blob_reader reader;
   blob_reader_init(&reader, blob.data, blob.size);
   nir_shader *replay = nir_deserialize(NULL, &options, &reader);
   if (argc > 1) nir_opt_dce(replay);
   kk_nir_lower_descriptors(replay, &rs, 0, NULL);
   nir_validate_shader(replay, "replayed descriptors");
   puts("descriptor replay passed");
   ralloc_free(replay);
   ralloc_free(b.shader);
   blob_finish(&blob);
   free(layout);
   return 0;
}
