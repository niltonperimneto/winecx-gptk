#version 450
layout(location=0,component=0) smooth out float value;

void main() {
 vec2 p[3]=vec2[3](vec2(-1,-1),vec2(3,-1),vec2(-1,3));
 float w[3]=float[3](1,2,4);
 float v[3]=float[3](0.2,0.6,1.0);
 int i=gl_VertexIndex%3;
 gl_Position=vec4(p[i]*w[i],0,w[i]); value=v[i];
 
}
