import sys

def process(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Revert it back to without winecx includes
    old_string = '-I"$GITHUB_WORKSPACE/gptk-video" -I"$GITHUB_WORKSPACE/build/include" -I"$GITHUB_WORKSPACE/winecx/include" -luuid -ldxguid'
    new_string = '-I"$GITHUB_WORKSPACE/gptk-video" -luuid -ldxguid'
    
    if old_string in content:
        content = content.replace(old_string, new_string)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

process(".github/workflows/build.yml")
