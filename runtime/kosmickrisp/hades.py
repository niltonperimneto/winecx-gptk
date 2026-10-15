#!/usr/bin/env python3
"""Launch an installed Windows Hades with isolated saves and local diagnostics."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import time


MARKER = ".hades-kosmickrisp-prefix"
SELECTION = ("CX_LIBVULKAN", "CX_ACTIVE_GRAPHICS_BACKEND", "WINE_VULKAN_LIBRARY",
             "VK_ICD_FILENAMES", "VK_ADD_DRIVER_FILES", "VK_DRIVER_FILES",
             "VK_LOADER_DRIVERS_SELECT", "VK_LOADER_DRIVERS_DISABLE",
             "VK_INSTANCE_LAYERS", "VK_LAYER_PATH", "WINEDLLOVERRIDES",
             "WINEARCH", "WINESERVER", "WINELOADER", "WINEDLLPATH")


def environment(prefix, backend, bundle=None, debug="-all"):
    env = {k: v for k, v in os.environ.items() if k not in SELECTION}
    env.update(WINEPREFIX=str(prefix), WINEDEBUG=debug, WINEDLLOVERRIDES="mshtml,nvapi,nvapi64=",
               VK_LOADER_DEBUG="error,warn,driver")
    if backend == "legacy-kosmickrisp":
        env.update(CX_LIBVULKAN=str(bundle / "libvulkan.1.dylib"),
                   CX_ACTIVE_GRAPHICS_BACKEND="wined3d",
                   VK_DRIVER_FILES=str(bundle / "kosmickrisp_icd.json"))
    elif backend == "moltenvk":
        env["CX_ACTIVE_GRAPHICS_BACKEND"] = "wined3d"
    return env


def claim_prefix(prefix):
    if prefix.is_symlink():
        raise ValueError("prefix must not be a symlink")
    marker = prefix / MARKER
    if prefix.exists() and any(prefix.iterdir()) and not marker.is_file():
        raise ValueError("refusing an existing prefix not created by this harness")
    prefix.mkdir(parents=True, exist_ok=True)
    lock = marker.open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        raise ValueError("another Hades harness owns this prefix")
    return lock


def isolate_saves(prefix):
    users = prefix / "drive_c/users"
    for user in users.iterdir():
        if user.is_symlink():
            raise ValueError(f"unexpected linked user directory: {user}")
        if not user.is_dir():
            continue
        for name in ("Documents", "My Documents", "Saved Games"):
            directory = user / name
            if directory.is_symlink():
                directory.unlink()
            directory.mkdir(exist_ok=True)
        saves = user / "Documents/Saved Games"
        if saves.is_symlink():
            saves.unlink()
        saves.mkdir(exist_ok=True)
        hades = saves / "Hades"
        if hades.is_symlink():
            raise ValueError("Hades save directory must be local to the prefix")
        hades.mkdir(exist_ok=True)


def run_bounded(command, env, log, timeout=60):
    with log.open("w") as stream:
        return subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT,
                              timeout=timeout, check=True)


def sample_process(pid, output, label):
    try:
        with (output / f"sample-{label}.log").open("w") as stream:
            subprocess.run(["/usr/bin/arch", "-x86_64", "/usr/bin/sample", str(pid), "2", "-file",
                            str(output / f"sample-{label}.txt")], stdout=stream,
                           stderr=subprocess.STDOUT, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        (output / f"sample-{label}-error.txt").write_text(str(error))


def stop_prefix(wine, env, output):
    with (output / "cleanup.log").open("w") as stream:
        subprocess.run([str(wine / "bin/wineserver"), "-k"], env=env,
                       stdout=stream, stderr=subprocess.STDOUT, timeout=15, check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--wine", type=Path, required=True, help="Wine directory containing bin/")
    parser.add_argument("--prefix", type=Path, required=True, help="new or harness-owned prefix")
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory per run")
    parser.add_argument("--backend", choices=("kosmickrisp", "legacy-kosmickrisp", "moltenvk"),
                        default="kosmickrisp")
    parser.add_argument("--bundle", type=Path, help="required for legacy diagnostic override")
    parser.add_argument("--interactive", action="store_true", help="no automatic timeout")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--debug", default="-all", help="use -all,+vulkan,+loaddll for API diagnostics")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.timeout < 10:
        parser.error("timeout must be at least 10 seconds")
    wine, game = args.wine.resolve(), args.game_dir.resolve()
    prefix = args.prefix.absolute()
    output = args.output.resolve()
    executable = game / "x64Vk/Hades.exe"
    launcher = wine / "bin" / ("wine-kosmickrisp" if args.backend == "kosmickrisp" else "wine64")
    bundle = args.bundle.resolve() if args.bundle else wine / "lib/kosmickrisp"
    required = [executable, game / "Content", launcher, wine / "bin/wineserver"]
    if args.backend != "moltenvk":
        required += [bundle / name for name in
                     ("libvulkan.1.dylib", "libvulkan_kosmickrisp.dylib", "kosmickrisp_icd.json")]
    for path in required:
        if not path.exists():
            parser.error(f"missing required component: {path}")
    if args.backend == "kosmickrisp" and args.bundle:
        parser.error("packaged launcher selects its own bundle; --bundle is for legacy diagnostics")
    try:
        lock = claim_prefix(prefix)
    except ValueError as error:
        parser.error(str(error))
    output.mkdir(parents=True, exist_ok=False)
    env = environment(prefix, args.backend, bundle, args.debug)
    arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    command = [str(launcher), str(executable), *arguments]
    report = {"game": "Hades", "backend": args.backend, "command": command,
              "cwd": str(executable.parent), "prefix": str(prefix),
              "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
              "os": platform.mac_ver()[0], "mode": "interactive" if args.interactive else "diagnostic",
              "environment": {k: env[k] for k in (*SELECTION, "WINEPREFIX", "WINEDEBUG", "VK_LOADER_DEBUG") if k in env},
              "status": "starting", "gameplay_verified": False}
    process = None
    started = time.monotonic()
    try:
        report["wine_version"] = subprocess.check_output([str(wine / "bin/wine64"), "--version"],
                                                         env=env, text=True, timeout=15).strip()
        if (bundle / "SOURCE.txt").exists() and args.backend != "moltenvk":
            shutil.copyfile(bundle / "SOURCE.txt", output / "driver-source.txt")
        setup_env = dict(env, WINEDEBUG="-all", WINEDLLOVERRIDES="mscoree,mshtml=")
        ready = prefix / ".hades-runtime-ready"
        runtime_identity = str(wine) + "\n" + report["wine_version"]
        if not ready.exists() or ready.read_text() != runtime_identity:
            run_bounded([str(wine / "bin/wine64"), "wineboot.exe", "-u"], setup_env,
                        output / "prefix-setup.log", timeout=120)
            run_bounded([str(wine / "bin/wineserver"), "-w"], setup_env, output / "prefix-wait.log")
            ready.write_text(runtime_identity)
        isolate_saves(prefix)
        with (output / "wine.log").open("w") as stream:
            process = subprocess.Popen(command, cwd=executable.parent, env=env,
                                       stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            report.update(pid=process.pid, status="running")
            (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
            print(f"Hades PID {process.pid}; evidence: {output}", flush=True)
            launched = time.monotonic()
            sampled = False
            while process.poll() is None:
                elapsed = time.monotonic() - launched
                if not args.interactive and elapsed >= min(30, args.timeout / 2) and not sampled:
                    sample_process(process.pid, output, "startup")
                    sampled = True
                if not args.interactive and elapsed >= args.timeout:
                    sample_process(process.pid, output, "timeout")
                    report.update(status="timed_out", exit_code=124)
                    break
                time.sleep(0.5)
            else:
                report.update(status="exited", exit_code=process.returncode)
    except KeyboardInterrupt:
        report.update(status="interrupted", exit_code=130)
    except Exception as error:
        report.update(status="failed", error=str(error), exit_code=1)
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            except ProcessLookupError:
                pass
        try:
            stop_prefix(wine, env, output)
        except (OSError, subprocess.TimeoutExpired) as error:
            report["cleanup_error"] = str(error)
        for log in (prefix / "drive_c/users").glob("*/Documents/Saved Games/Hades/Hades.log"):
            shutil.copyfile(log, output / f"Hades-{log.relative_to(prefix / 'drive_c/users').parts[0]}.log")
        report["seconds"] = round(time.monotonic() - started, 2)
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        lock.close()
    print(json.dumps(report, indent=2))
    return report.get("exit_code", 1)


if __name__ == "__main__":
    raise SystemExit(main())
