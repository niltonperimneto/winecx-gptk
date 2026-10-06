#version 450
layout(location = 0) out uvec4 color;
void main()
{
    color = uvec4(65537u, 123456789u, 0xdeadbeefu, 0xfedcba98u);
}
