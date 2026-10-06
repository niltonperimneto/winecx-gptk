import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def shaders(stage, producer, consumer):
    vertex = '''#version 450
const vec2 p[3] = vec2[3](vec2(-1,-1), vec2(3,-1), vec2(-1,3));
const float w[3] = float[3](1,2,4);
void main() {
    gl_Position = vec4(p[gl_VertexIndex] * w[gl_VertexIndex], .5 * w[gl_VertexIndex], w[gl_VertexIndex]);
    VALUE
}
'''
    value = 'v = float(gl_VertexIndex) * .5;'
    output = f'layout(location=0) {producer} out float v;\n'
    if stage == 'vs':
        vertex = vertex.replace('const vec2', output + 'const vec2').replace('VALUE', value)
    else:
        vertex = vertex.replace('VALUE', '')
    result = {'vert': vertex, 'frag': f'''#version 450
layout(location=0) {consumer} in float v;
layout(location=0) out vec4 color;
void main() {{ color = vec4(v, 0, 0, 1); }}
'''}
    if stage.startswith('gs'):
        result['geom'] = f'''#version 450
layout(triangles) in;
layout(triangle_strip, max_vertices=3) out;
{output}
void main() {{
    for (int i=0; i<3; ++i) {{
        gl_Position = gl_in[i].gl_Position;
        v = float(i) * .5;
        EmitVertex();
    }}
    EndPrimitive();
}}
'''
    if stage == 'gs_dynamic':
        result['geom'] = result['geom'].replace('max_vertices=3', 'max_vertices=4').replace(
            'i<3', 'i<3 + (gl_PrimitiveIDIn & 1)').replace('gl_in[i]', 'gl_in[i % 3]')
    if stage in ['gs_strip', 'gs_indexed']:
        extra = 'gl_Position = vec4(24,24,4,8); v = 1.5; EmitVertex();'
        result['geom'] = result['geom'].replace('max_vertices=3', 'max_vertices=7').replace(
            '    EndPrimitive();', '    ' + extra + '\n    EndPrimitive();')
        if stage == 'gs_indexed':
            result['geom'] = result['geom'].replace('    EndPrimitive();',
                '    EndPrimitive();\n    for (int i=0; i<3; ++i) { gl_Position = gl_in[i].gl_Position; v = float(i)*.5; EmitVertex(); }\n    EndPrimitive();')
    if stage == 'tes':
        result['tesc'] = '''#version 450
layout(vertices=3) out;
void main() {
    gl_out[gl_InvocationID].gl_Position = gl_in[gl_InvocationID].gl_Position;
    gl_TessLevelOuter[0] = 1;
    gl_TessLevelOuter[1] = 1;
    gl_TessLevelOuter[2] = 1;
    gl_TessLevelInner[0] = 1;
}
'''
        result['tese'] = f'''#version 450
layout(triangles, equal_spacing, ccw) in;
{output}
void main() {{
    gl_Position = gl_TessCoord.x * gl_in[0].gl_Position +
        gl_TessCoord.y * gl_in[1].gl_Position + gl_TessCoord.z * gl_in[2].gl_Position;
    v = .5 * gl_TessCoord.y + gl_TessCoord.z;
}}
'''
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--icd', required=True, type=Path)
    parser.add_argument('--headers', required=True, type=Path)
    parser.add_argument('--quick', action='store_true')
    parser.add_argument('--extras-only', action='store_true')
    args = parser.parse_args()
    icd = args.icd.resolve()
    cases = [('smooth', 'flat'), ('flat', 'smooth'), ('noperspective', 'smooth'), ('centroid', 'sample'), ('flat', 'smooth'), ('flat', 'smooth'), ('flat', 'smooth'), ('flat', 'smooth'), ('flat', 'smooth'), ('flat', 'smooth')]
    with tempfile.TemporaryDirectory(prefix='kk-interpolation-') as work:
        work = Path(work)
        probe = work / 'probe'
        subprocess.run(['clang', '-Wall', '-Wextra', '-Werror', '-I' + str(args.headers),
                        str(Path(__file__).with_name('kosmickrisp_interpolation.c')), '-o', str(probe)], check=True)
        for stage in ['vs', 'gs', 'gs_dynamic', 'gs_strip', 'gs_indexed', 'tes']:
            for case, (producer, consumer) in enumerate(cases):
                sources = shaders(stage, producer, consumer)
                if case == 6:
                    sources['frag'] = sources['frag'].replace('vec4(v, 0, 0, 1)', 'vec4(v, 0, 0, .5)')
                if case == 8:
                    sources['frag'] = sources['frag'].replace('layout(location=0) out vec4 color;',
                        'layout(location=0, index=0) out vec4 color; layout(location=0, index=1) out vec4 secondary;').replace(
                        'color = vec4(v, 0, 0, 1);', 'color = vec4(v, 0, 0, 1); secondary = vec4(.25);')
                alternate = 'noperspective' if stage == 'tes' else 'smooth' if case == 0 else 'flat'
                sources['alt'] = shaders(stage, producer, alternate)['frag']
                for extension, source in sources.items():
                    path = work / f'{stage}-{extension}-{case}.{extension}'
                    path.write_text(source)
                    subprocess.run(['glslangValidator', '-V', '-S', 'frag' if extension == 'alt' else extension, str(path), '-o',
                                    str(work / f'{stage}-{extension}-{case}.spv')], check=True, stdout=subprocess.DEVNULL)
        failures = []
        total = 0
        for cache_round in range(0 if args.extras_only else 1 if args.quick else 2):
            for stage in ['vs', 'gs', 'gs_dynamic', 'gs_strip', 'gs_indexed', 'tes']:
                for case in range(5):
                    if stage.startswith('gs_') and case not in [0, 1]:
                        continue
                    if stage == 'tes' and case == 0:
                        continue
                    for mode in ['monolithic', 'partition', 'gpl', 'objects']:
                        for last in ([0, 1] if case == 0 else [0]):
                            env = os.environ.copy()
                            env['MESA_SHADER_CACHE_DIR'] = str(work / 'cache')
                            env['MESA_KK_DEBUG'] = 'partition,pso' if mode == 'partition' else 'pso'
                            if mode != 'objects':
                                env['KK_PROBE_CACHE'] = str(work / f'{stage}-{case}-{mode}-{last}.cache')
                                if cache_round:
                                    env['KK_PROBE_REQUIRE_CACHE'] = '1'
                                    env['MESA_SHADER_CACHE_DISABLE'] = 'true'
                            command = [str(probe), str(icd), str(work), stage, str(case),
                                       str(2 if mode == 'objects' else int(mode == 'gpl')), str(last), str(4 if case == 3 else 1)]
                            try:
                                result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
                            except subprocess.TimeoutExpired:
                                failures.append((stage, case, mode, last, 'timeout'))
                                total += 1
                                print(f'TIMEOUT stage={stage} case={case} mode={mode} last={last}', flush=True)
                                continue
                            total += 1
                            print(f'round={cache_round} mode={mode} {result.stdout.strip()}', flush=True)
                            if result.returncode:
                                print(result.stderr, flush=True)
                                failures.append((stage, case, mode, last, result.returncode))
        for mode in [0, 1]:
            env = os.environ.copy()
            env['MESA_KK_DEBUG'] = 'pso,' + os.environ.get('KK_PROBE_DEBUG', '')
            env['MESA_SHADER_CACHE_DIR'] = str(work / 'cache')
            for case, options in [(6, {'KK_PROBE_ALPHA_ONE': '1'}),
                                  (6, {'KK_PROBE_ALPHA_COVERAGE': '1'}),
                                  (6, {'KK_PROBE_SAMPLE_MASK': '5'}),
                                  (7, {'KK_PROBE_BLEND': 'add'}),
                                  (8, {'KK_PROBE_BLEND': 'dual'}),
                                  (9, {'KK_PROBE_BLEND': 'advanced'})]:
                for restart in range(2):
                    if restart and 'KK_PROBE_SAMPLE_MASK' in options:
                        options = dict(options, KK_PROBE_SAMPLE_MASK='3')
                    result = subprocess.run([str(probe), str(icd), str(work), 'vs', str(case), str(mode), '0',
                                             '4' if case == 6 else '1'], env=dict(env, **options),
                                            capture_output=True, text=True, timeout=120)
                    total += 1
                    print(f'blend-ms case={case} mode={mode} restart={restart} {result.stdout}', flush=True)
                    expected_cache = mode == 1 and restart == 1 and (case in [8, 9] or 'KK_PROBE_SAMPLE_MASK' in options)
                    unexpected_variant = mode == 1 and (case == 7 or (case == 6 and 'KK_PROBE_SAMPLE_MASK' not in options)) and 'FS variant compile' in result.stderr
                    if result.returncode or (expected_cache and 'FS variant disk cache hit' not in result.stderr) or unexpected_variant:
                        print(result.stderr, flush=True)
                        failures.append(('blend-ms', case, mode, options, result.returncode))
            result = subprocess.run([str(probe), str(icd), str(work), 'vs', '1', '3', '0', '1'],
                                    env=env, capture_output=True, text=True, timeout=120)
            total += 1
            if result.returncode or 'PSO prewarm started' not in result.stderr or 'PSO compile' not in result.stderr:
                print(result.stderr, flush=True)
                failures.append(('prewarm-no-draw', result.returncode))
        result = subprocess.run([str(probe), str(icd), str(work), 'gs', '5', '0', '0', '1'],
                                capture_output=True, text=True, timeout=120)
        total += 1
        print(result.stdout, flush=True)
        if result.returncode:
            print(result.stderr, flush=True)
            failures.append(('existing-geometry', result.returncode))
        print(f'{total - len(failures)}/{total} passed; failures={failures}')
        return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
