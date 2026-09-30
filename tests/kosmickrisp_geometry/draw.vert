#version 450
layout(push_constant) uniform Mode { int adjacency; } mode;
void main() {
    vec2 positions[3] = vec2[3](vec2(-1,-1), vec2(3,-1), vec2(-1,3));
    int index = mode.adjacency != 0 ? gl_VertexIndex / 2 : gl_VertexIndex % 3;
    gl_Position = vec4(positions[index], 0, 1);
}
