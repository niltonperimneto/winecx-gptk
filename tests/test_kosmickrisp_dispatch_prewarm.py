import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class DispatchPrewarmTests(unittest.TestCase):
    def test_primary_and_replay_dispatch(self):
        mesa = Path(os.environ.get('MESA_SOURCE', Path(__file__).resolve().parents[2] / 'mesa'))
        generator = mesa / 'src/kosmickrisp/util/kk_dispatch_cmd_gen.py'
        if not generator.exists():
            self.skipTest('Mesa source is unavailable')
        try:
            import mako
        except ImportError:
            self.skipTest('Mako is unavailable')
        compiler = shutil.which('cc')
        if compiler is None:
            self.skipTest('C compiler is unavailable')
        sys.path.insert(0, str(mesa / 'src/vulkan/util'))
        try:
            spec = importlib.util.spec_from_file_location('kk_dispatch_prewarm_generator', generator)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            names = {'CmdBindPipeline', 'CmdSetPrimitiveTopology', 'CmdDraw'}
            entrypoints = [e for e in module.get_entrypoints_from_xml(
                [str(mesa / 'src/vulkan/registry/vk.xml')], 'false')
                if e.name in names]
            generated = module.TEMPLATE_C.render(entrypoints=entrypoints,
                filename=generator.name, prewarm_commands=module.PREWARM_COMMANDS)
        finally:
            sys.path.pop(0)
        header = r'''
#ifndef TEST_DISPATCH_H
#define TEST_DISPATCH_H
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#define VKAPI_ATTR
#define VKAPI_CALL
#define VK_COMMAND_BUFFER_LEVEL_PRIMARY 0
#define VK_FROM_HANDLE(type, name, handle) struct type *name = (void *)(handle)
typedef struct kk_cmd_buffer *VkCommandBuffer;
typedef uint32_t VkPipelineBindPoint;
typedef uint64_t VkPipeline;
typedef uint32_t VkPrimitiveTopology;
struct vk_device_dispatch_table {
   void (*CmdBindPipeline)(VkCommandBuffer, VkPipelineBindPoint, VkPipeline);
   void (*CmdSetPrimitiveTopology)(VkCommandBuffer, VkPrimitiveTopology);
   void (*CmdDraw)(VkCommandBuffer, uint32_t, uint32_t, uint32_t, uint32_t);
};
struct kk_device { struct { struct vk_device_dispatch_table dispatch_table; } vk; };
struct kk_cmd_buffer { struct { uint32_t level; } vk; bool one_time_submit;
                       struct kk_device *device; uint32_t applied; };
static inline struct kk_device *kk_cmd_buffer_device(struct kk_cmd_buffer *cmd)
{ return cmd->device; }
void kk_cmd_prewarm_pipeline(struct kk_cmd_buffer *cmd);
extern struct vk_device_dispatch_table vk_cmd_enqueue_unless_primary_device_entrypoints;
extern struct vk_device_dispatch_table vk_cmd_enqueue_device_entrypoints;
#endif
'''
        harness = r'''
static uint32_t raw_calls, enqueued, hook_calls;
static void bind(VkCommandBuffer cmd, VkPipelineBindPoint point, VkPipeline pipeline)
{ raw_calls++; cmd->applied = 1; }
static void topology(VkCommandBuffer cmd, VkPrimitiveTopology value)
{ raw_calls++; cmd->applied = 2; }
static void draw(VkCommandBuffer cmd, uint32_t a, uint32_t b, uint32_t c, uint32_t d)
{ raw_calls++; }
static void enqueue_bind(VkCommandBuffer cmd, VkPipelineBindPoint p, VkPipeline pipeline)
{ enqueued++; }
static void enqueue_topology(VkCommandBuffer cmd, VkPrimitiveTopology value)
{ enqueued++; }
static void enqueue_draw(VkCommandBuffer cmd, uint32_t a, uint32_t b, uint32_t c, uint32_t d)
{ enqueued++; }
void kk_cmd_prewarm_pipeline(struct kk_cmd_buffer *cmd)
{ assert(cmd->applied == (hook_calls % 2) + 1); hook_calls++; }
struct vk_device_dispatch_table vk_cmd_enqueue_unless_primary_device_entrypoints = {
   enqueue_bind, enqueue_topology, enqueue_draw
};
struct vk_device_dispatch_table vk_cmd_enqueue_device_entrypoints = {
   enqueue_bind, enqueue_topology, enqueue_draw
};
int main(void)
{
   struct kk_device dev = { .vk.dispatch_table = { bind, topology, draw } };
   struct kk_cmd_buffer cmd = { .device = &dev };
   cmd.vk.level = 1;
   kk_device_cmd_trampolines.CmdBindPipeline(&cmd, 0, 1);
   kk_device_cmd_trampolines.CmdSetPrimitiveTopology(&cmd, 3);
   assert(raw_calls == 0 && hook_calls == 0 && enqueued == 2);
   cmd.vk.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
   kk_device_cmd_trampolines.CmdBindPipeline(&cmd, 0, 1);
   kk_device_cmd_trampolines.CmdSetPrimitiveTopology(&cmd, 3);
   kk_device_cmd_trampolines.CmdDraw(&cmd, 3, 1, 0, 0);
   assert(raw_calls == 3 && hook_calls == 2 && enqueued == 5);
   kk_device_cmd_prewarm_dispatch_table.CmdBindPipeline(&cmd, 0, 1);
   kk_device_cmd_prewarm_dispatch_table.CmdSetPrimitiveTopology(&cmd, 3);
   kk_device_cmd_prewarm_dispatch_table.CmdDraw(&cmd, 3, 1, 0, 0);
   assert(raw_calls == 6 && hook_calls == 4 && enqueued == 5);
   cmd.one_time_submit = true;
   kk_device_cmd_trampolines.CmdBindPipeline(&cmd, 0, 1);
   kk_device_cmd_trampolines.CmdSetPrimitiveTopology(&cmd, 3);
   kk_device_cmd_trampolines.CmdDraw(&cmd, 3, 1, 0, 0);
   assert(raw_calls == 9 && hook_calls == 6 && enqueued == 5);
   return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'common.h').write_text(header)
            for name in ('kk_device.h', 'kk_cmd_buffer.h', 'kk_dispatch_cmd.h', 'vk_cmd_enqueue_entrypoints.h'):
                (out / name).write_text('#include "common.h"\n')
            (out / 'test.c').write_text(generated + harness)
            subprocess.run([compiler, '-std=c11', '-I', str(out), str(out / 'test.c'),
                            '-o', str(out / 'test')], check=True, capture_output=True)
            subprocess.run([str(out / 'test')], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
