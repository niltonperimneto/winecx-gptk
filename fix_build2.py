import sys, re

def process(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # The block looks like:
    # command -v x86_64-w64-mingw32-clang >/dev/null || brew install -q llvm-mingw
    # replace with wget and tar
    
    replacement = """command -v x86_64-w64-mingw32-clang >/dev/null || {
            curl -sSL -O https://github.com/mstorsjo/llvm-mingw/releases/download/20240619/llvm-mingw-20240619-ucrt-macos-universal.tar.xz
            tar -xf llvm-mingw-20240619-ucrt-macos-universal.tar.xz
            echo "$PWD/llvm-mingw-20240619-ucrt-macos-universal/bin" >> $GITHUB_PATH
            export PATH="$PWD/llvm-mingw-20240619-ucrt-macos-universal/bin:$PATH"
          }"""

    content = content.replace("command -v x86_64-w64-mingw32-clang >/dev/null || brew install -q llvm-mingw", replacement)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

process(".github/workflows/build.yml")
print("Patched build.yml")
