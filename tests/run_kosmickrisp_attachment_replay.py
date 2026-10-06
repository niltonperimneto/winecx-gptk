import argparse
import json
from pathlib import Path
import shutil
import subprocess

from run_kosmickrisp_gpl_batch import digest, prepare, scenario
from run_kosmickrisp_variant_replay import run_probe


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Attachment harness anchor changed: ' + old[:80])
    return source.replace(old, new, 1)


def attachment_source(source):
    source = replace_once(source,
        '            if (getenv("KK_PROBE_BIND_BEFORE_RENDERING"))\n'
        '                vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);\n'
        '            vkCmdBeginRenderPass(command, &render_begin, VK_SUBPASS_CONTENTS_INLINE);\n'
        '            if (!getenv("KK_PROBE_BIND_BEFORE_RENDERING"))\n'
        '                vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);',
        '            vkCmdBeginRenderPass(command, &render_begin, VK_SUBPASS_CONTENTS_INLINE);\n'
        '            vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);')
    changes = [
        ('    VkPhysicalDeviceColorWriteEnableFeaturesEXT color_write_features = {',
         '    VkPhysicalDeviceDynamicRenderingLocalReadFeaturesKHR local_read = {\n'
         '        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DYNAMIC_RENDERING_LOCAL_READ_FEATURES_KHR };\n'
         '    VkPhysicalDeviceColorWriteEnableFeaturesEXT color_write_features = {'),
        ('        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COLOR_WRITE_ENABLE_FEATURES_EXT };',
         '        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COLOR_WRITE_ENABLE_FEATURES_EXT, .pNext = &local_read };'),
        ('    vkGetPhysicalDeviceFeatures2(physical, &features);',
         '    vkGetPhysicalDeviceFeatures2(physical, &features);\n'
         '    if (!f13.dynamicRendering || !local_read.dynamicRenderingLocalRead) return 77;\n'
         '    int map_before_bind = option("KK_PROBE_MAP_BEFORE_BIND", 0, 1);'),
        ('    const char *extensions[7] = {', '    const char *extensions[8] = {'),
        ('    unsigned extension_count = 3;',
         '    unsigned extension_count = 3;\n'
         '    extensions[extension_count++] = "VK_KHR_dynamic_rendering_local_read";'),
        ('    if (dynamic_pso) {\n        uint32_t available_count = 0;',
         '    {\n        uint32_t available_count = 0;'),
        ('    provoking.pNext = objects ? (void *)&object_features : dynamic_pso ? (void *)&dynamic_features : NULL;',
         '    provoking.pNext = &f13;'),
        ('        .dynamicRendering = objects, .pNext = dynamic_pso ? &dynamic_features : NULL };',
         '        .dynamicRendering = VK_TRUE, .pNext = dynamic_pso ? (void *)&dynamic_features : (void *)&local_read };'),
        ('        .pNext = dynamic_color_write ? &color_write_features : NULL,',
         '        .pNext = dynamic_color_write ? (void *)&color_write_features : (void *)&local_read,'),
        ('    vkGetPhysicalDeviceMemoryProperties(physical, &memory_properties);',
         '    vkCmdBeginRendering = (PFN_vkCmdBeginRendering)gipa(instance, "vkCmdBeginRendering");\n'
         '    vkCmdEndRendering = (PFN_vkCmdEndRendering)gipa(instance, "vkCmdEndRendering");\n'
         '    PFN_vkCmdSetRenderingAttachmentLocationsKHR set_locations =\n'
         '        (PFN_vkCmdSetRenderingAttachmentLocationsKHR)gipa(instance, "vkCmdSetRenderingAttachmentLocationsKHR");\n'
         '    if (!vkCmdBeginRendering || !vkCmdEndRendering || !set_locations) return 77;\n'
         '    vkGetPhysicalDeviceMemoryProperties(physical, &memory_properties);'),
        ('    VkPipelineDynamicStateCreateInfo dynamic_info = {',
         '    VkFormat output_format = VK_FORMAT_R32G32B32A32_SFLOAT;\n'
         '    VkPipelineRenderingCreateInfo rendering_pipeline = {\n'
         '        .sType = VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO,\n'
         '        .colorAttachmentCount = 1, .pColorAttachmentFormats = &output_format };\n'
         '    uint32_t output_location = 1;\n'
         '    VkRenderingAttachmentLocationInfoKHR locations = {\n'
         '        .sType = VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_LOCATION_INFO_KHR,\n'
         '        .pNext = &rendering_pipeline, .colorAttachmentCount = 1,\n'
         '        .pColorAttachmentLocations = &output_location };\n'
         '    VkPipelineDynamicStateCreateInfo dynamic_info = {'),
        ('        .stageCount = stage_count, .pStages = stages, .pVertexInputState = &vertex, .pInputAssemblyState = &assembly,',
         '        .pNext = &locations, .stageCount = stage_count, .pStages = stages, .pVertexInputState = &vertex, .pInputAssemblyState = &assembly,'),
        ('        .pColorBlendState = &color, .pDynamicState = dynamic_count ? &dynamic_info : NULL, .layout = layout, .renderPass = render_pass };',
         '        .pColorBlendState = &color, .pDynamicState = dynamic_count ? &dynamic_info : NULL,\n'
         '        .layout = layout, .renderPass = VK_NULL_HANDLE };'),
        ('    VkGraphicsPipelineLibraryCreateInfoEXT part = { .sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_LIBRARY_CREATE_INFO_EXT };',
         '    VkGraphicsPipelineLibraryCreateInfoEXT part = {\n'
         '        .sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_LIBRARY_CREATE_INFO_EXT, .pNext = &locations };'),
        ('        .libraryCount = group_count, .pLibraries = linked_libraries };',
         '        .pNext = &locations, .libraryCount = group_count, .pLibraries = linked_libraries };'),
        ('            vkCmdBeginRenderPass(command, &render_begin, VK_SUBPASS_CONTENTS_INLINE);',
         '            (void)render_begin;\n'
         '            VkImageMemoryBarrier transition = { .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,\n'
         '                .dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT, .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED,\n'
         '                .newLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,\n'
         '                .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,\n'
         '                .image = images[0], .subresourceRange = range };\n'
         '            vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,\n'
         '                0, 0, NULL, 0, NULL, 1, &transition);\n'
         '            VkRenderingAttachmentInfo attachment = { .sType = VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO,\n'
         '                .imageView = views[0], .imageLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,\n'
         '                .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR, .storeOp = VK_ATTACHMENT_STORE_OP_STORE, .clearValue = clear[0] };\n'
         '            VkRenderingInfo rendering = { .sType = VK_STRUCTURE_TYPE_RENDERING_INFO,\n'
         '                .renderArea = scissor, .layerCount = 1, .colorAttachmentCount = 1, .pColorAttachments = &attachment };\n'
         '            vkCmdBeginRendering(command, &rendering);'),
        ('            vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);',
         '            if (map_before_bind) {\n'
         '                VkRenderingAttachmentLocationInfoKHR command_locations = locations;\n'
         '                command_locations.pNext = NULL;\n'
         '                set_locations(command, &command_locations);\n'
         '            }\n'
         '            vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);'),
        ('        uint64_t draw_start = now_ns();',
         '        VkRenderingAttachmentLocationInfoKHR command_locations = locations;\n'
         '        command_locations.pNext = NULL;\n'
         '        if (!map_before_bind) set_locations(command, &command_locations);\n'
         '        uint64_t draw_start = now_ns();'),
        ('            vkCmdEndRenderPass(command);',
         '            vkCmdEndRendering(command);\n'
         '            VkImageMemoryBarrier transition = { .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,\n'
         '                .srcAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT, .dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT,\n'
         '                .oldLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, .newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,\n'
         '                .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,\n'
         '                .image = images[0], .subresourceRange = range };\n'
         '            vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,\n'
         '                0, 0, NULL, 0, NULL, 1, &transition);'),
    ]
    for old, new in changes:
        source = replace_once(source, old, new)
    first = source.index('        for (unsigned y = 1; y < 7; ++y) for (unsigned x = 1; x < 7; ++x) {')
    last = source.index('        printf("stage=%s case=%d gpl=%d last=%d samples=%d result=%s', first)
    return source[:first] + '''        const float expected[4] = {.25f, .5f, .75f, 1};
        for (unsigned pixel = 0; pixel < 64; ++pixel) for (unsigned channel = 0; channel < 4; ++channel) {
            float actual = pixels[pixel * 4 + channel];
            if (!isfinite(actual) || fabsf(actual - expected[channel]) > .0001f) {
                fprintf(stderr, "attachment pixel %u channel %u: %f expected %f\\n",
                    pixel, channel, actual, expected[channel]);
                failed = 1;
            }
        }
''' + source[last:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--icd', required=True, type=Path)
    parser.add_argument('--headers', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--compile-only', action='store_true')
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    icd, headers, out = args.icd.resolve(), args.headers.resolve(), args.out.resolve()
    if not icd.is_file() or not (headers / 'vulkan/vulkan.h').is_file():
        parser.error('ICD or Vulkan headers do not exist')
    if args.timeout <= 0 or not shutil.which('clang') or not shutil.which('glslangValidator'):
        parser.error('Positive timeout, clang and glslangValidator are required')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        parser.error('Output directory must be empty to preserve evidence')
    out.mkdir(parents=True, exist_ok=True)
    tests = Path(__file__).resolve().parent
    prepare(out, headers)
    source = out / 'attachment-probe.c'
    source.write_text(attachment_source((tests / 'kosmickrisp_interpolation.c').read_text()))
    probe = out / 'attachment-probe'
    subprocess.run(['clang', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
        '-I' + str(headers), '-I' + str(tests), str(source), '-o', str(probe)], check=True)
    fragment = out / 'attachment.frag'
    fragment.write_text('#version 450\nlayout(location=1) out vec4 color;\nvoid main() { color = vec4(.25, .5, .75, 1); }\n')
    subprocess.run(['glslangValidator', '-V', '-S', 'frag', str(fragment),
        '-o', str(out / 'vs-frag-1.spv')], check=True)
    report = {'schema': 1, 'icd_sha256': digest(icd), 'compiled_only': args.compile_only,
        'scope': 'Known mapping uses creation-time drain; command mappings match pipeline state before or after binding.',
        'specification_url': 'https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdSetRenderingAttachmentLocations.html',
        'attachment': 0, 'shader_output_location': 1, 'results': []}
    if not args.compile_only:
        for before_bind in (False, True):
            item = scenario('attachment-map-before-bind' if before_bind else 'attachment-map-after-bind',
                options={'KK_PROBE_MAP_BEFORE_BIND': '1' if before_bind else '0'})
            for phase in ('cold', 'warm', 'warm2'):
                row = run_probe(probe, icd, out, item, out / item['name'], phase,
                    args.timeout, require_zero=phase != 'cold')
                report['results'].append(row)
                (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
                print(item['name'], phase, row['status'], '; '.join(row['reasons']), flush=True)
                if row['status'] != 'pass':
                    break
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return int(any(row['status'] == 'fail' for row in report['results']))


if __name__ == '__main__':
    raise SystemExit(main())
