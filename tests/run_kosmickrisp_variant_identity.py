import argparse
import json
import subprocess
from pathlib import Path

from run_kosmickrisp_variant_history import compiler_arguments


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesa", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sanitize", choices=("address", "thread"))
    args = parser.parse_args()
    mesa, build, out = args.mesa.resolve(), args.build.resolve(), args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error("--out must be empty")
    out.mkdir(parents=True, exist_ok=True)
    source = (mesa / "src/kosmickrisp/vulkan/kk_shader.c").read_text()
    start = source.index("static void\nkk_identity_scalar(")
    end = source.index("static void\nkk_variant_shader_key(", start)
    extracted = out / "variant-identity.c"
    extracted.write_text(
        '#include "kosmickrisp/vulkan/kk_shader.h"\n'
        '#include "util/u_atomic.h"\n'
        + source[start:end]
    )
    binary = out / "variant-identity-regression"
    arguments, directory = compiler_arguments(mesa, build, binary)
    arguments = [argument for argument in arguments if not argument.endswith("kk_variant_history.c")
                 and not argument.endswith("kosmickrisp_variant_history.c")]
    arguments.extend([
        str(extracted),
        str(Path(__file__).with_name("kosmickrisp_variant_identity.c")),
        str(build / "src/util/libmesa_util.a.p/mesa-blake3.c.o"),
        str(build / "src/util/blake3/libblake3.a"),
        str(build / "src/c11/impl/libmesa_util_c11.a"),
    ])
    if args.sanitize:
        arguments.extend([f"-fsanitize={args.sanitize}", "-fno-omit-frame-pointer"])
    compiled = subprocess.run(arguments, cwd=directory, capture_output=True, text=True)
    (out / "compile.stderr").write_text(compiled.stderr)
    if compiled.returncode:
        print(compiled.stderr)
        return 1
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
    (out / "report.json").write_text(json.dumps({"returncode": result.returncode,
                                                "stdout": result.stdout,
                                                "stderr": result.stderr}, indent=2) + "\n")
    print(result.stdout, end="")
    print(result.stderr, end="")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
