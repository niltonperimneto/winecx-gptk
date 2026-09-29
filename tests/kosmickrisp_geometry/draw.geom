#version 450
layout(triangles) in;
layout(triangle_strip, max_vertices=3) out;
layout(set=0, binding=0, std430) buffer Counts { uint calls; uint ids; uint rawCalls; uint reserved1; } counts;
layout(set=0, binding=1, r32ui) uniform uimage2D image_count;
void main() {
    atomicAdd(counts.rawCalls, 1);
    uint bit = 1u << uint(gl_PrimitiveIDIn);
    uint previous = atomicOr(counts.ids, bit);
    if ((previous & bit) == 0) {
        atomicAdd(counts.calls, 1);
        imageAtomicAdd(image_count, ivec2(0), 1);
        imageStore(image_count, ivec2(gl_PrimitiveIDIn + 1, 0),
                   uvec4(0xc0de0000u | uint(gl_PrimitiveIDIn)));
    }
    for (int i=0; i<3; ++i) {
        gl_Position = gl_in[i].gl_Position;
        EmitVertex();
    }
    EndPrimitive();
}
