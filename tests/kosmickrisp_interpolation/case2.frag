#version 450
layout(location=0,component=0) flat in float value;

layout(location=0) out vec4 color;
void main() {
 vec2 xy=gl_FragCoord.xy/16.0;
 vec3 b=vec3(1.0-xy.x-xy.y,xy);
 float expected=0.2;
 bool ok=abs(value-expected)<0.003 ;
 color=ok?vec4(0,1,0,1):vec4(1,0,1,1);
}
