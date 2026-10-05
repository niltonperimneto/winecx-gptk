#!/usr/bin/env python3
"""Exercise KK disk-cache reuse and GPL readback in separate host processes."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


def validate(probe, loader, icd, output):
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema": 1, "checks": {}}
    markers = ("graphicsPipelineLibrary=1", "compute shader readback passed",
               "geometry rendering and side-effect readback passed",
               "adjacency-without-gs rendering and side-effect readback passed",
               "tessellation-geometry rendering and side-effect readback passed",
               "geometry-wireframe rendering and side-effect readback passed")
    env = dict(os.environ, VK_DRIVER_FILES=str(icd), KOSMICKRISP_TEST_GPL="1",
               MESA_SHADER_CACHE_SHOW_STATS="true")
    for key in ("VK_ICD_FILENAMES", "VK_ADD_DRIVER_FILES", "VK_LOADER_DRIVERS_SELECT",
                "VK_LOADER_DRIVERS_DISABLE", "MESA_SHADER_CACHE_DISABLE",
                "MESA_SHADER_CACHE_READ_ONLY", "MESA_SHADER_CACHE_MAX_SIZE",
                "MESA_DISK_CACHE_SINGLE_FILE", "MESA_DISK_CACHE_DATABASE"):
        env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="kk shader cache ") as temporary:
        cache = Path(temporary)
        env["MESA_SHADER_CACHE_DIR"] = str(cache / "enabled")
        for phase in ("cold", "warm", "corrupt", "disabled"):
            if phase == "corrupt":
                entries = [p for p in (cache / "enabled").rglob("*")
                           if p.is_file() and p.name != "index"]
                if not entries:
                    raise RuntimeError("cold run did not persist cache entries")
                for entry in entries:
                    entry.write_bytes(b"deliberately truncated cache entry")
            elif phase == "disabled":
                env["MESA_SHADER_CACHE_DISABLE"] = "true"
                env["MESA_SHADER_CACHE_DIR"] = str(cache / "disabled")
            started = time.monotonic()
            try:
                process = subprocess.run([str(probe), str(loader)], env=env,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, errors="replace", timeout=120)
                code, text = process.returncode, process.stdout
            except subprocess.TimeoutExpired as error:
                code = 124
                text = (error.stdout or b"").decode(errors="replace")
            (output / f"{phase}.log").write_text(text)
            counts = re.findall(r"disk shader cache:\s+hits = (\d+), misses = (\d+)", text)
            hits = sum(int(h) for h, _ in counts)
            misses = sum(int(m) for _, m in counts)
            ok = code == 0 and all(marker in text for marker in markers)
            # Each GPL mode must reach all three graphics readbacks.
            for mode in (1, 2, 3):
                section = text.partition(f"GPL mode={mode}")[2].split("GPL mode=", 1)[0]
                ok = ok and all(marker in section for marker in markers[2:])
            if phase in ("cold", "corrupt"):
                ok = ok and misses > 0
            elif phase == "warm":
                ok = ok and hits > 0 and misses == 0
            else:
                ok = ok and not any(p.is_file() for p in (cache / "disabled").rglob("*"))
            report["checks"][phase] = {"status": "passed" if ok else "failed",
                                       "exit_code": code, "hits": hits, "misses": misses,
                                       "seconds": round(time.monotonic() - started, 3)}
            (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
            if not ok:
                raise RuntimeError(f"shader cache {phase} failed; see {output / (phase + '.log')}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("probe", "loader", "icd", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.probe.resolve(), args.loader.resolve(),
                              args.icd.resolve(), args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
