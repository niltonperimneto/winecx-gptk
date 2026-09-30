#!/usr/bin/env python3
"""Validate the downloaded runtime, with bounded probes and durable evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import shutil
import subprocess
import time
from game import run_game


def verify_manifest(libraries):
    manifest = json.loads((libraries / "RuntimeManifest.json").read_text())
    if manifest.get("formatVersion") != 1 or not manifest.get("files"):
        raise ValueError("missing or unsupported runtime manifest")
    declared = set()
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        path = libraries / relative
        if relative.is_absolute() or ".." in relative.parts or path.is_symlink():
            raise ValueError(f"unsafe manifest path: {relative}")
        if not path.resolve().is_relative_to(libraries.resolve()):
            raise ValueError(f"manifest path escapes runtime: {relative}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["sha256"] or path.stat().st_size != entry["size"]:
            raise ValueError(f"runtime file mismatch: {relative}")
        if str(relative) in declared:
            raise ValueError(f"duplicate manifest entry: {relative}")
        declared.add(str(relative))
    actual = {str(p.relative_to(libraries)) for p in libraries.rglob("*")
              if p.is_file() and not p.is_symlink()
              and str(p.relative_to(libraries)) not in ("RuntimeManifest.json", "WhiskyWineVersion.plist")}
    if actual != declared:
        raise ValueError("runtime contains undeclared or missing files")


def run_probe(command, env, log, timeout=120, cwd=None):
    """A separate process group lets a timeout terminate Wine child processes."""
    started = time.monotonic()
    with log.open("w") as stream:
        process = subprocess.Popen(command, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True, cwd=cwd)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            code = 124
            stream.write(f"\nTimed out after {timeout} seconds\n")
    return code, round(time.monotonic() - started, 2), log.read_text(errors="replace")


def parse_capabilities(text):
    fields = {}
    extensions = []
    for line in text.splitlines():
        if line.startswith("extension="):
            extensions.append(line.partition("=")[2])
        for word in line.split():
            key, separator, value = word.partition("=")
            if separator and key in ("geometryShader", "tessellationShader", "shaderInt64",
                                     "shaderInt8", "descriptorIndexing", "scalarBlockLayout",
                                     "synchronization2", "maxPushConstantsSize", "api",
                                     "conformance", "fillModeNonSolid"):
                fields[key] = value
    fields["extensions"] = extensions
    return fields


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--libraries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--game-config", type=Path, default=Path(__file__).with_name("game.json"))
    args = parser.parse_args()
    libraries, output = args.libraries.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    wine = libraries / "Wine"
    bundle = wine / "lib/kosmickrisp"
    report = {"schema": 1, "commit": os.environ.get("GITHUB_SHA"),
              "os": platform.mac_ver()[0], "machine": platform.machine(), "checks": {},
              "migration": {
                  "dxvk": {"status": "blocked", "reason": "version-specific DXVK validation not yet run"},
                  "game": {"status": "blocked", "reason": "no pinned game benchmark configured"},
                  "shader_correctness": {"status": "blocked", "reason": "compute readback not yet run"}}}
    checks = report["checks"]
    # Keep Wine's z: symlink out of the diagnostics tree. Artifact upload tools
    # can traverse it even when a glob tries to exclude the prefix.
    prefix = output.with_name(output.name + "-prefix")
    env = dict(os.environ, WINEPREFIX=str(prefix), WINEDEBUG="-all",
               WINEDLLOVERRIDES="mscoree,mshtml=")
    for key in ("CX_LIBVULKAN", "CX_ACTIVE_GRAPHICS_BACKEND", "WINE_VULKAN_LIBRARY",
                "VK_ICD_FILENAMES", "VK_ADD_DRIVER_FILES", "VK_DRIVER_FILES",
                "VK_LOADER_DRIVERS_SELECT", "VK_LOADER_DRIVERS_DISABLE"):
        env.pop(key, None)

    def check(name, command, required=(), expected_failure=False):
        code, elapsed, text = run_probe([str(x) for x in command], env, output / f"{name}.log")
        ok = code not in (0, 124) if expected_failure else code == 0
        ok = ok and all(marker in text for marker in required)
        checks[name] = {"status": "passed" if ok else "failed", "exit_code": code, "seconds": elapsed}
        if not ok:
            checks[name]["missing_markers"] = [marker for marker in required if marker not in text]
            print(f"::error::{name} exited {code}; missing markers: {checks[name]['missing_markers']}; log: {name}.log")
        return text

    try:
        if platform.system() != "Darwin" or report["os"].split(".")[0] != "26":
            raise ValueError("this gate must execute on macOS 26, not merely target it")
        if platform.machine() != "arm64":
            raise ValueError("Apple Silicon runner required")
        checks["macos26"] = {"status": "passed"}
        verify_manifest(libraries)
        checks["manifest"] = {"status": "passed"}
        report["manifest_sha256"] = hashlib.sha256((libraries / "RuntimeManifest.json").read_bytes()).hexdigest()
        report["sources"] = (bundle / "SOURCE.txt").read_text()
        check("hardware", ["system_profiler", "SPDisplaysDataType"])
        env["VK_DRIVER_FILES"] = str(bundle / "kosmickrisp_icd.json")
        markers = ("driver=KosmicKrisp id=28", "fillModeNonSolid=1",
                   "KosmicKrisp device creation passed",
                   "geometry rendering and side-effect readback passed",
                   "adjacency-without-gs rendering and side-effect readback passed",
                   "tessellation-geometry rendering and side-effect readback passed")
        check("host", [bundle / "tests/host-probe", bundle / "libvulkan.1.dylib"], markers)

        # This fails if the new patch was omitted, even if a global ICD happened
        # to let positive probes work. No CrossOver legacy loader override is set.
        env["WINE_VULKAN_LIBRARY"] = str(output / "deliberately-missing-loader.dylib")
        env["WINEDEBUG"] = "+vulkan"
        check("loader-override-negative", [wine / "bin/wine64", bundle / "tests/x86_64.exe"],
              required=("Failed to load", "deliberately-missing-loader.dylib"), expected_failure=True)
        env.pop("WINE_VULKAN_LIBRARY")
        env["WINEDEBUG"] = "-all"
        for target in ("x86_64", "i686"):
            text = check(f"wine-{target}", [wine / "bin/wine-kosmickrisp", bundle / f"tests/{target}.exe", "--present"],
                         markers + ("Win32 surface, swapchain, clear, and present passed",
                                    "compute shader readback passed", "presentation-mode=windowed passed",
                                    "presentation-mode=resized passed", "presentation-mode=borderless-fullscreen passed",
                                    "presentation-mode=restored passed"))
            report.setdefault("capabilities", {})[target] = parse_capabilities(text)
        if all(checks[f"wine-{target}"]["status"] == "passed" for target in ("x86_64", "i686")):
            report["migration"]["shader_correctness"] = {
                "status": "passed", "reason": "deterministic compute, geometry, adjacency and tessellation readback; not general shader conformance"}
        caps = report["capabilities"]["x86_64"]
        missing = []
        if caps.get("geometryShader") != "1":
            missing.append("geometryShader")
        if caps.get("fillModeNonSolid") != "1":
            missing.append("fillModeNonSolid")
        optional_missing = []
        if "VK_EXT_transform_feedback" not in caps["extensions"]:
            optional_missing.append("VK_EXT_transform_feedback")
        report["migration"]["dxvk"]["known_missing"] = missing
        # Run stock DXVK with native-only overrides in isolated application dirs.
        # Keeping both the DLLs and EXE there prevents fallback to the shipped fork.
        pins = dict(line.split("=", 1) for line in report["sources"].splitlines()
                    if line and not line.startswith("#") and "=" in line)
        version = pins["DXVK_TEST_VERSION"]
        dxvk_results = {}
        for target, dll_arch in (("x86_64", "x64"), ("i686", "x32")):
            directory = output / f"dxvk-{target}"
            directory.mkdir()
            for dll in (bundle / f"tests/dxvk-{version}/{dll_arch}").glob("*.dll"):
                shutil.copy2(dll, directory)
            dxvk_env = dict(env, WINEDLLOVERRIDES="d3d9,d3d11,dxgi=n;mscoree,mshtml=",
                            DXVK_LOG_LEVEL="info", DXVK_LOG_PATH=str(directory))
            for api, marker in (("d3d9", "RESULT: d3d9 device up"), ("d3d11", "[ ok ] D3D11CreateDevice")):
                executable = directory / f"{api}-{target}.exe"
                shutil.copy2(bundle / "tests" / executable.name, executable)
                code, seconds, text = run_probe([str(wine / "bin/wine-kosmickrisp"), str(executable)],
                    dxvk_env, directory / f"{api}.log", cwd=directory)
                logs = "\n".join(p.read_text(errors="replace") for p in directory.glob(f"{executable.stem}_*.log"))
                ok = code == 0 and marker in text and f"DXVK: v{version}" in logs
                dxvk_results[f"{api}-{target}"] = {"status": "passed" if ok else "failed",
                                                  "exit_code": code, "seconds": seconds}
        dxvk_ok = not missing and all(result["status"] == "passed" for result in dxvk_results.values())
        report["migration"]["dxvk"] = {
            "status": "passed" if dxvk_ok else "blocked", "version": version,
            "known_missing": missing, "optional_missing": optional_missing,
            "probes": dxvk_results,
            "reason": ("missing: " + ", ".join(missing)) if missing else
                "D3D9/D3D11 initialization plus known-feature screen; game coverage is a separate gate"}
        report["migration"]["game"] = run_game(args.game_config, wine / "bin/wine-kosmickrisp", env, output, run_probe)
    except Exception as error:
        checks["validation"] = {"status": "failed", "reason": str(error)}
    finally:
        if prefix.exists():
            try:
                run_probe([str(wine / "bin/wineserver"), "-k"], env, output / "cleanup.log", timeout=15)
            except OSError:
                pass
        report["passed"] = bool(checks) and all(c["status"] == "passed" for c in checks.values())
        (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        summary = ["| KosmicKrisp validation | Result |", "|---|---|"]
        summary.extend(f"| {name} | {result['status']} |" for name, result in checks.items())
        summary.extend(f"| {name} | {result['status']}: {result['reason']} |"
                       for name, result in report["migration"].items())
        text = "\n".join(summary) + "\n"
        (output / "summary.md").write_text(text)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
                stream.write(text)
        print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
