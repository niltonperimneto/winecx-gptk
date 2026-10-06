import argparse
import json
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--arch", choices=["arm64", "x86_64"], required=True)
    args = parser.parse_args()
    build = args.build.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    commands = json.loads((build / "compile_commands.json").read_text())
    entry = next(e for e in commands if e["file"].endswith("kk_nir_lower_descriptors.c"))
    command = shlex.split(entry["command"])
    flags = []
    i = 1
    while i < len(command):
        flag = command[i]
        if flag in {"-o", "-c", "-MQ", "-MF"}:
            i += 2
        elif flag == "-MD":
            i += 1
        else:
            flags.append(flag)
            i += 1
    obj = out / "descriptor-replay.o"
    source = Path(__file__).with_name("kosmickrisp_descriptor_replay.c")
    compilation = [command[0], *flags, "-o", str(obj), "-c", str(source)]
    libs = ["src/compiler/nir/libnir.a", "src/compiler/libcompiler.a",
            "src/util/libmesa_util.a", "src/util/blake3/libblake3.a",
            "src/c11/impl/libmesa_util_c11.a"]
    binary = out / "descriptor-replay"
    linking = ["c++", "-arch", args.arch, str(obj),
               str(build / "src/kosmickrisp/vulkan/libkk.a.p/kk_nir_lower_descriptors.c.o"),
               *[str(build / p) for p in libs], "-L/opt/homebrew/lib",
               "-lz", "-lzstd", "-lexpat", "-o", str(binary)]
    for label, cmd in [("compile", compilation), ("link", linking)]:
        result = subprocess.run(cmd, cwd=entry["directory"], capture_output=True, text=True)
        (out / (label + ".log")).write_text(result.stdout + result.stderr)
        if result.returncode:
            print(result.stderr)
            return result.returncode
    rows = []
    for name, options in [("before", []), ("dce", ["dce"])]:
        try:
            result = subprocess.run(["arch", "-" + args.arch, str(binary), *options],
                                    capture_output=True, text=True, timeout=5)
            rows.append({"case": name, "returncode": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        except subprocess.TimeoutExpired:
            rows.append({"case": name, "timeout": 5})
    (out / "report.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))
    return int(rows[1].get("returncode") != 0 or rows[0].get("returncode") == 0)


if __name__ == "__main__":
    raise SystemExit(main())
