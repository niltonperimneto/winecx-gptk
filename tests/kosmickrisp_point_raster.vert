#version 450
layout(location = 0) out float value;
void main()
{
    ivec2 pixel = ivec2(gl_VertexIndex % 8, gl_VertexIndex / 8);
    vec2 center = (vec2(pixel) + vec2(0.5)) / 8.0;
    gl_Position = vec4(center * 2.0 - 1.0, 0.0, 1.0);
    gl_PointSize = 1.0;
    value = float(gl_VertexIndex) / 64.0;
}
