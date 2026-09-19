import sys

def process(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # The compilation line looks like:
    # x86_64-w64-mingw32-clang -shared -O2 -fno-strict-aliasing \
    #   -o Libraries/Wine/lib/gptk-video/d3d12shim.dll \
    #   "$GITHUB_WORKSPACE/gptk-video/d3d12shim.c" \
    #   "$GITHUB_WORKSPACE/gptk-video/d3d12shim.def" \
    #   -I"$GITHUB_WORKSPACE/gptk-video" -luuid -ldxguid

    old_string = '-I"$GITHUB_WORKSPACE/gptk-video" -luuid -ldxguid'
    new_string = '-I"$GITHUB_WORKSPACE/gptk-video" -I"$GITHUB_WORKSPACE/winecx/include" -luuid -ldxguid'
    
    if old_string in content:
        content = content.replace(old_string, new_string)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

process(".github/workflows/build.yml")
print("Patched include path.")
