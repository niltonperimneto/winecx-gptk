#version 450
layout(push_constant) uniform Mode { int adjacency; } mode;
void main() {
    vec2 positions[3] = vec2[3](vec2(-1,-1), vec2(3,-1), vec2(-1,3));
    int index = mode.adjacency == 1 ? gl_VertexIndex / 2 : gl_VertexIndex % 3;
    if (mode.adjacency == 2) {
        positions[0] = vec2(-0.75, -0.75);
        positions[1] = vec2(0.75, -0.75);
        positions[2] = vec2(0, 0.75);
    }
    gl_Position = vec4(positions[index], 0, 1);
}
