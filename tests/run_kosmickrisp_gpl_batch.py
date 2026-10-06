import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time

from run_kosmickrisp_interpolation import shaders


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize(values):
    return {"count": len(values), "median_ms": statistics.median(values) / 1e6,
            "p95_ms": percentile(values, .95) / 1e6, "max_ms": max(values) / 1e6}


def parse_metrics(stdout):
    metrics = [json.loads(line[7:]) for line in stdout.splitlines() if line.startswith("METRIC ")]
    for metric in metrics:
        if (not isinstance(metric, dict) or not isinstance(metric.get("kind"), str)
                or type(metric.get("ns")) is not int or metric["ns"] < 0):
            raise ValueError("Invalid probe timing record")
    return metrics


def parse_compiles(path):
    if not path.exists():
        return None
    events = []
    with path.open() as stream:
        for row in csv.reader(stream):
            if len(row) != 4:
                raise ValueError("Invalid compiler timing row")
            kind, origin, start, end = row
            elapsed = int(end) - int(start)
            if elapsed < 0:
                raise ValueError("Negative compiler timing interval")
            events.append({"kind": kind, "origin": origin, "ns": elapsed})
    return events


def parse_cache_events(path):
    if not path.exists():
        return None
    events = []
    with path.open() as stream:
        for line in stream:
            event = json.loads(line)
            if not isinstance(event, dict) or not isinstance(event.get("event"), str):
                raise ValueError("Invalid cache trace record")
            events.append(event)
    return events


def prewarm_check(events, expectation):
    if events is None:
        return "Missing cache trace for prewarm validation"
    pso = [event for event in events if event["event"] == "pso"]
    if expectation == "match":
        if not any(event.get("outcome") == "prewarm_match" for event in pso):
            return "Default or static prewarm prediction did not match a draw"
    elif expectation == "distinct":
        prewarm = {event.get("key") for event in pso if event.get("origin") == "prewarm"}
        drawn = {event.get("key") for event in pso if event.get("origin") == "draw"
                 and event.get("outcome") != "prewarm_unused"}
        unused = {event.get("key") for event in pso if event.get("outcome") == "prewarm_unused"}
        if not prewarm or not drawn or len(prewarm | drawn) < 2 or unused & drawn:
            return "Non-default dynamic draw did not retain distinct predicted and exact PSO keys"
    return None


def scenario(name, stage="vs", case=1, mode=1, samples=1, options=None):
    return {"name": name, "stage": stage, "case": case, "mode": mode,
            "samples": samples, "options": options or {}}


def correctness_cases():
    cases = []
    for groups in ["1,2,4,8", "3,12", "5,10", "9,6", "7,8", "11,4", "13,2", "14,1"]:
        cases.append(scenario("groups-" + groups.replace(",", "-"), options={"KK_PROBE_GROUPS": groups}))
    for groups in ["1,2,4,8", "3,12", "7,8"]:
        cases.append(scenario("lto-" + groups.replace(",", "-"), options={"KK_PROBE_GROUPS": groups, "KK_PROBE_LTO": "1"}))
    for stage in ["vs", "gs", "tes"]:
        cases.extend([
            scenario(stage + "-reversed", stage, options={"KK_PROBE_REVERSE": "1"}),
            scenario(stage + "-nested", stage, options={"KK_PROBE_NESTED": "1"}),
            scenario(stage + "-lifetime", stage, options={"KK_PROBE_DESTROY_LIBRARIES": "1"}),
            scenario(stage + "-concurrent-link", stage, options={"KK_PROBE_LINK_COUNT": "16", "KK_PROBE_THREADS": "4"}),
        ])
    for name, options in [
            ("separate", {}), ("reversed", {"KK_PROBE_REVERSE": "1"}),
            ("nested", {"KK_PROBE_NESTED": "1"}), ("grouped", {"KK_PROBE_GROUPS": "3,12"}),
            ("lto", {"KK_PROBE_LTO": "1"})]:
        cases.append(scenario("descriptor-sets-" + name, case=11,
                              options=dict(options, KK_PROBE_DESCRIPTOR_SETS="1")))
    cases.extend([
        scenario("dual-source-msaa", case=8, samples=4, options={"KK_PROBE_BLEND": "dual"}),
        scenario("advanced-blend-msaa", case=9, samples=4, options={"KK_PROBE_BLEND": "advanced"}),
        scenario("alpha-coverage-and-mask", case=6, samples=4,
                 options={"KK_PROBE_ALPHA_COVERAGE": "1", "KK_PROBE_SAMPLE_MASK": "5"}),
        scenario("prewarm-no-draw", mode=3),
        scenario("pipeline-cache-merge", options={"KK_PROBE_CACHE_MERGE": "1"}),
        scenario("dynamic-pso-default", options={"KK_PROBE_DYNAMIC_PSO": "all", "KK_PROBE_PREWARM_DELAY_MS": "100"}),
        scenario("dynamic-pso-nondefault", case=6, samples=4,
                 options={"KK_PROBE_DYNAMIC_PSO": "all", "KK_PROBE_SAMPLE_MASK": "5", "KK_PROBE_PREWARM_DELAY_MS": "100"}),
        scenario("dynamic-pso-native-blend", case=7,
                 options={"KK_PROBE_DYNAMIC_PSO": "all", "KK_PROBE_BLEND": "add", "KK_PROBE_PREWARM_DELAY_MS": "100"}),
        scenario("dynamic-pso-mixed", case=7, samples=4,
                 options={"KK_PROBE_DYNAMIC_PSO": "mixed", "KK_PROBE_BLEND": "add", "KK_PROBE_PREWARM_DELAY_MS": "100"}),
        scenario("dynamic-pso-color-write", options={"KK_PROBE_DYNAMIC_PSO": "all", "KK_PROBE_DYNAMIC_COLOR_WRITE": "1", "KK_PROBE_PREWARM_DELAY_MS": "100"}),
    ])
    for case in cases:
        if case["name"] in {"dynamic-pso-default", "dynamic-pso-mixed", "dynamic-pso-color-write"}:
            case["prewarm_expectation"] = "match"
        elif case["name"] in {"dynamic-pso-nondefault", "dynamic-pso-native-blend"}:
            case["prewarm_expectation"] = "distinct"
    return cases


def benchmark_cases():
    return [
        scenario("monolithic", case=7, mode=0, options={"KK_PROBE_BLEND": "add"}),
        scenario("partition", case=7, mode=0, options={"KK_PROBE_BLEND": "add", "MESA_KK_DEBUG": "partition"}),
        scenario("gpl-native", case=7, options={"KK_PROBE_BLEND": "add"}),
        scenario("gpl-lto", case=7, options={"KK_PROBE_BLEND": "add", "KK_PROBE_LTO": "1"}),
        scenario("gpl-prewarm-delay", case=7, options={"KK_PROBE_BLEND": "add", "KK_PROBE_PREWARM_DELAY_MS": "50"}),
        scenario("gpl-dual-source", case=8, options={"KK_PROBE_BLEND": "dual"}),
        scenario("gpl-advanced-blend", case=9, options={"KK_PROBE_BLEND": "advanced"}),
        scenario("gpl-sample-mask", case=6, samples=4, options={"KK_PROBE_SAMPLE_MASK": "5"}),
        scenario("gpl-dynamic-default", options={"KK_PROBE_DYNAMIC_PSO": "all"}),
        scenario("gpl-dynamic-mask", case=6, samples=4,
                 options={"KK_PROBE_DYNAMIC_PSO": "all", "KK_PROBE_SAMPLE_MASK": "5"}),
        scenario("gpl-dynamic-native-blend", case=7,
                 options={"KK_PROBE_DYNAMIC_PSO": "all", "KK_PROBE_BLEND": "add"}),
        scenario("gpl-concurrent-link", case=7,
                 options={"KK_PROBE_BLEND": "add", "KK_PROBE_LINK_COUNT": "16", "KK_PROBE_THREADS": "4"}),
    ]


def prepare(work, headers):
    probe = work / "probe"
    subprocess.run(["clang", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", "-I" + str(headers),
                    str(Path(__file__).with_name("kosmickrisp_interpolation.c")), "-o", str(probe)], check=True)
    for stage in ["vs", "gs", "tes"]:
        for case in [1, 6, 7, 8, 9, 11]:
            sources = shaders(stage, "flat", "smooth")
            if case == 6:
                sources["frag"] = sources["frag"].replace("vec4(v, 0, 0, 1)", "vec4(v, 0, 0, .5)")
            if case == 8:
                sources["frag"] = sources["frag"].replace("layout(location=0) out vec4 color;",
                    "layout(location=0, index=0) out vec4 color; layout(location=0, index=1) out vec4 secondary;").replace(
                    "color = vec4(v, 0, 0, 1);", "color = vec4(v, 0, 0, 1); secondary = vec4(.25);")
            if case == 11:
                sources["vert"] = sources["vert"].replace("void main()", "layout(set=1, binding=0) uniform VS { float scale; } vs_data;\nvoid main()").replace(
                    "v = float(gl_VertexIndex) * .5;", "v = float(gl_VertexIndex) * .5 * vs_data.scale;")
                sources["frag"] = sources["frag"].replace("void main()", "layout(set=0, binding=0) uniform FS { float scale; } fs_data;\nvoid main()").replace(
                    "vec4(v, 0, 0, 1)", "vec4(v * fs_data.scale, 0, 0, 1)")
            sources["alt"] = shaders(stage, "flat", "noperspective" if stage == "tes" else "flat")["frag"]
            for extension, source in sources.items():
                path = work / f"{stage}-{extension}-{case}.{extension}"
                path.write_text(source)
                subprocess.run(["glslangValidator", "-V", "-S", "frag" if extension == "alt" else extension,
                                str(path), "-o", str(work / f"{stage}-{extension}-{case}.spv")],
                               check=True, stdout=subprocess.DEVNULL)
    return probe


def clean_env():
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("KK_PROBE_") or key in {"MESA_KK_DEBUG", "MESA_KK_COMPILE_LOG", "MESA_KK_CACHE_LOG", "MESA_KK_PSO_CACHE_DISABLE", "MESA_SHADER_CACHE_DISABLE", "MESA_SHADER_CACHE_DIR"}:
            del env[key]
    return env


def run_probe(probe, icd, shaders_dir, item, directory, timeout, phase="cold", benchmark=False):
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / (phase + "-compiler.csv")
    cache_log = directory / (phase + "-cache.jsonl")
    env = clean_env()
    env.update({"KK_PROBE_METRICS": "1", "MESA_KK_DEBUG": "" if benchmark else "pso",
                "MESA_SHADER_CACHE_DIR": str(directory / "disk-cache"), "MESA_KK_COMPILE_LOG": str(log), "MESA_KK_CACHE_LOG": str(cache_log),
                "KK_PROBE_CACHE": str(directory / "pipeline.cache")})
    if benchmark:
        env["KK_PROBE_REPEAT_DRAWS"] = "8"
    env.update(item["options"])
    if phase == "disk-warm":
        env["KK_PROBE_CACHE"] = str(directory / "disk-only-pipeline.cache")
    require_cache_hit = phase == "application-warm"
    if phase == "application-warm":
        env["MESA_SHADER_CACHE_DISABLE"] = "true"
        if require_cache_hit:
            env["KK_PROBE_REQUIRE_CACHE"] = "1"
    command = [str(probe), str(icd), str(shaders_dir), item["stage"], str(item["case"]), str(item["mode"]), "0", str(item["samples"])]
    start = time.monotonic_ns()
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout)
        status = "pass" if result.returncode == 0 else "skip" if result.returncode == 77 else "fail"
        stdout, stderr, returncode = result.stdout, result.stderr, result.returncode
        reasons = [] if status != "fail" else ["probe exit " + str(returncode)]
    except subprocess.TimeoutExpired as error:
        status, returncode = "fail", None
        stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout or ""
        stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr or ""
        reasons = ["timeout"]
    elapsed = time.monotonic_ns() - start
    (directory / (phase + "-stdout.log")).write_text(stdout)
    (directory / (phase + "-stderr.log")).write_text(stderr)
    try:
        metrics = parse_metrics(stdout)
        events = parse_compiles(log)
        cache_events = parse_cache_events(cache_log)
        if status == "pass" and not metrics:
            raise ValueError("Missing probe timing records")
    except (ValueError, TypeError) as error:
        metrics, events, cache_events, status = [], None, None, "fail"
        reasons.append(str(error))
    if status == "pass" and item["mode"] == 3 and not any(
            event["kind"] in {"pso", "pso_archive"} and event["origin"] == "prewarm"
            for event in events or []):
        status = "fail"
        reasons.append("missing no-draw prewarm evidence")
    if status == "pass" and item.get("prewarm_expectation"):
        reason = prewarm_check(cache_events, item["prewarm_expectation"])
        if reason:
            status = "fail"
            reasons.append(reason)
    cache_outcomes = {}
    for event in cache_events or []:
        label = event["event"] + "/" + str(event.get("outcome", "")) + "/" + str(event.get("origin", ""))
        cache_outcomes[label] = cache_outcomes.get(label, 0) + 1
    return {"name": item["name"], "phase": phase, "status": status, "returncode": returncode,
            "reasons": reasons, "elapsed_ms": elapsed / 1e6, "metrics": metrics, "compiler_events": events,
            "artifacts": str(directory), "cache_hit_required": require_cache_hit, "cache_events": cache_events,
            "cache_outcomes": cache_outcomes, "cache_trace": str(cache_log), "prewarm_expectation": item.get("prewarm_expectation")}


def benchmark_summary(results):
    buckets = {}
    for result in results:
        if result["status"] != "pass":
            continue
        prefix = result["name"] + "/" + result["phase"] + "/"
        for metric in result["metrics"]:
            kind = metric["kind"]
            if kind in {"draw_record", "command_record", "submit_and_wait"}:
                kind += "/first" if metric["pass"] == 0 else "/reuse"
            elif kind == "library_create":
                kind += "/stages-" + str(metric["stages"])
            buckets.setdefault(prefix + kind, []).append(metric["ns"])
        for event in result["compiler_events"] or []:
            kind = "driver/" + event["kind"] + "/" + event["origin"]
            buckets.setdefault(prefix + kind, []).append(event["ns"])
    return {key: summarize(values) for key, values in sorted(buckets.items())}


def compare_reports(current, previous):
    if current["workload_sha256"] != previous["workload_sha256"]:
        raise ValueError("Comparison report uses a different workload")
    comparisons = {}
    for key, measured in current["benchmarks"].items():
        reference = previous.get("benchmarks", {}).get(key)
        if reference and reference["median_ms"] > 0:
            comparisons[key] = {"median_change_percent": 100 * (measured["median_ms"] / reference["median_ms"] - 1),
                                "p95_change_percent": 100 * (measured["p95_ms"] / reference["p95_ms"] - 1)
                                if reference["p95_ms"] > 0 else None}
    return comparisons


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--icd", required=True, type=Path)
    parser.add_argument("--headers", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--correctness-only", action="store_true")
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    if not shutil.which("clang") or not shutil.which("glslangValidator"):
        parser.error("clang and glslangValidator must be available")
    icd, headers, out = args.icd.resolve(), args.headers.resolve(), args.out.resolve()
    if not icd.is_file() or not (headers / "vulkan/vulkan.h").is_file():
        parser.error("ICD or Vulkan headers do not exist")
    repetitions = args.repetitions if args.repetitions is not None else 2 if args.quick else 5
    if repetitions < 1 or args.timeout <= 0:
        parser.error("repetitions and timeout must be positive")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        parser.error("output directory must be empty to preserve previous evidence")
    out.mkdir(parents=True, exist_ok=True)
    workload = digest(Path(__file__).with_name("kosmickrisp_interpolation.c")) + digest(__file__) + digest(Path(__file__).with_name("run_kosmickrisp_interpolation.py"))
    report = {"schema": 1, "icd": str(icd), "icd_sha256": digest(icd), "workload_sha256": hashlib.sha256(workload.encode()).hexdigest(),
              "repetitions": repetitions, "correctness": [], "performance_runs": [], "benchmarks": {},
              "coverage_gaps": ["Vulkan CTS", "depth/stencil attachments", "integer logic operations", "multiview",
                                "non-native render formats", "compile-required flags", "dynamic-state transitions within one command buffer", "validation-layer execution"],
              "timing_scope": "Host API timings; submit_and_wait includes CPU submission and GPU completion, not isolated GPU execution."}
    probe = prepare(out, headers)
    if not args.skip_existing:
        command = [sys.executable, str(Path(__file__).with_name("run_kosmickrisp_interpolation.py")), "--icd", str(icd), "--headers", str(headers)]
        if args.quick:
            command.append("--quick")
        try:
            result = subprocess.run(command, env=clean_env(), capture_output=True, text=True, timeout=max(600, args.timeout * 10))
        except subprocess.TimeoutExpired:
            result = subprocess.CompletedProcess(command, 1, "", "Existing regression suite timed out")
        (out / "existing-stdout.log").write_text(result.stdout)
        (out / "existing-stderr.log").write_text(result.stderr)
        counts = re.search(r"(\d+)/(\d+) passed", result.stdout)
        report["correctness"].append({"name": "existing-regressions", "status": "pass" if result.returncode == 0 else "fail",
                                      "passed": int(counts[1]) if counts else None, "total": int(counts[2]) if counts else None})
    for item in correctness_cases():
        directory = out / "correctness" / item["name"]
        for phase in ["cold", "application-warm"]:
            result = run_probe(probe, icd, out, item, directory, args.timeout, phase)
            report["correctness"].append(result)
            print(item["name"], phase, result["status"], flush=True)
            if result["status"] != "pass" or item["mode"] == 3:
                break
    if not args.correctness_only:
        for item in benchmark_cases():
            for repetition in range(repetitions):
                directory = out / "performance" / item["name"] / str(repetition)
                for phase in ["cold", "disk-warm", "application-warm"]:
                    result = run_probe(probe, icd, out, item, directory, args.timeout, phase, benchmark=True)
                    report["performance_runs"].append(result)
                    print("benchmark", item["name"], repetition, phase, result["status"], flush=True)
                    if result["status"] != "pass":
                        break
    report["benchmarks"] = benchmark_summary(report["performance_runs"])
    report["compiler_timing_available"] = any(row.get("compiler_events") is not None
                                              for row in report["correctness"] + report["performance_runs"])
    (out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    if args.compare:
        report["comparison"] = compare_reports(report, json.loads(args.compare.read_text()))
    all_results = report["correctness"] + report["performance_runs"]
    report["counts"] = {status: sum(row["status"] == status for row in all_results) for status in ["pass", "fail", "skip"]}
    (out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report["counts"]), "report:", out / "report.json", flush=True)
    return 1 if report["counts"]["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
