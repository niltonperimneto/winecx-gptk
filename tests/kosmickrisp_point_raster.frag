#version 450
layout(location = 0) in float value;
layout(location = 0) out vec4 color;
void main()
{
    color = vec4(value, value * 0.5, 1.0 - value, 1.0);
}
