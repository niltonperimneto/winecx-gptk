import sys, re

def process(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # insert CROSSCC="x86_64-w64-mingw32-clang" below export CC="ccache /usr/bin/clang -arch x86_64"
    if 'export CROSSCC="x86_64-w64-mingw32-clang"' not in content:
        content = content.replace(
            'export CC="ccache /usr/bin/clang -arch x86_64"',
            'export CC="ccache /usr/bin/clang -arch x86_64"\n          export CROSSCC="x86_64-w64-mingw32-clang"'
        )
    if 'export CROSSCXX="x86_64-w64-mingw32-clang++"' not in content:
        content = content.replace(
            'export CXX="ccache /usr/bin/clang++ -arch x86_64"',
            'export CXX="ccache /usr/bin/clang++ -arch x86_64"\n          export CROSSCXX="x86_64-w64-mingw32-clang++"'
        )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

process(".github/workflows/build.yml")
print("Patched CROSSCC in build.yml")
