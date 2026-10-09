import argparse
import json
import shlex
import subprocess
import time
from pathlib import Path


SCENARIOS = ("race", "failure", "concurrency", "corruption", "disabled")


def compiler_arguments(mesa, build, output):
    commands = json.loads((build / "compile_commands.json").read_text())
    entry = next(
        command
        for name in ("kk_metal_cache.c", "kk_pso_cache.c")
        for command in commands
        if Path(command["file"]).name == name
    )
    directory = Path(entry["directory"])
    source = Path(entry["file"])
    if not source.is_absolute():
        source = (directory / source).resolve()
    original_mesa = source.parents[3]
    arguments = entry.get("arguments") or shlex.split(entry["command"])
    result = []
    skip = False
    for argument in arguments:
        if skip:
            skip = False
            continue
        if argument in ("-o", "-MF", "-MT", "-MQ"):
            skip = True
            continue
        if argument in ("-c", "-MD", "-MMD"):
            continue
        if Path(argument).name in ("kk_metal_cache.c", "kk_pso_cache.c"):
            continue
        if argument.startswith("-I") and len(argument) > 2:
            include = Path(argument[2:])
            if not include.is_absolute():
                include = (directory / include).resolve()
            try:
                argument = "-I" + str(mesa / include.relative_to(original_mesa))
            except ValueError:
                pass
        result.append(argument)
    result.extend(
        [
            str(mesa / "src/kosmickrisp/vulkan/kk_metal_cache.c"),
            str(Path(__file__).with_name("kosmickrisp_metal_cache.c")),
            "-pthread",
            "-UNDEBUG",
            "-o",
            str(output),
        ]
    )
    return result, directory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesa", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--scenario", choices=SCENARIOS, action="append")
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error("--out must be empty")
    out.mkdir(parents=True, exist_ok=True)
    binary = out / "metal-cache-regression"
    arguments, directory = compiler_arguments(
        args.mesa.resolve(), args.build.resolve(), binary
    )
    compile_result = subprocess.run(
        arguments, cwd=directory, capture_output=True, text=True
    )
    (out / "compile.stdout").write_text(compile_result.stdout)
    (out / "compile.stderr").write_text(compile_result.stderr)
    if compile_result.returncode:
        print(compile_result.stderr)
        return 1
    results = []
    for scenario in args.scenario or SCENARIOS:
        start = time.monotonic_ns()
        try:
            completed = subprocess.run(
                [str(binary), scenario],
                capture_output=True,
                text=True,
                timeout=args.timeout,
            )
            result = {
                "scenario": scenario,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        except subprocess.TimeoutExpired as error:
            result = {
                "scenario": scenario,
                "returncode": None,
                "stdout": (error.stdout or b"").decode(errors="replace"),
                "stderr": (error.stderr or b"").decode(errors="replace"),
                "timeout": True,
            }
        result["elapsed_ns"] = time.monotonic_ns() - start
        results.append(result)
        print(f"{scenario}: {'PASS' if result['returncode'] == 0 else 'FAIL'}")
    (out / "report.json").write_text(json.dumps(results, indent=2) + "\n")
    return int(any(result["returncode"] != 0 for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
