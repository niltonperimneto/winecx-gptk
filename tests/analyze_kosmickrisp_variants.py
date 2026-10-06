import argparse
import collections
import json
import pathlib

WAIT_PHASES = ("fs_wait", "raster_wait", "pso_wait", "archive_load")
BLOCKING_PHASES = WAIT_PHASES + ("fs_prepare", "raster_prepare", "pso_create",
                                "archive_lookup", "native_create", "history_load")


def union_and_exclusive(intervals):
    points = sorted({point for start, end, _ in intervals for point in (start, end)})
    exclusive = collections.Counter()
    union = 0
    for start, end in zip(points, points[1:]):
        active = [(right - left, phase) for left, right, phase in intervals
                  if left <= start and right >= end]
        if active:
            _, phase = min(active)
            exclusive[phase] += end - start
            union += end - start
    return union, dict(exclusive)


def analyze(events):
    threads = collections.defaultdict(list)
    counts = collections.Counter()
    requests = collections.defaultdict(list)
    dependencies = collections.defaultdict(set)
    for event in events:
        if event.get("event") != "variant":
            continue
        phase = event["phase"]
        counts[phase] += 1
        requests[event["request_id"]].append(event)
        parent = event.get("parent_id")
        if parent and parent != event["request_id"]:
            dependencies[parent].add(event["request_id"])
        start, end = event["start_ns"], event["end_ns"]
        if end < start:
            raise ValueError("Negative variant interval")
        if event["origin"] == "draw" and phase in BLOCKING_PHASES and end > start:
            threads[str(event["thread_id"])].append((start, end, phase))
    thread_report = {}
    for thread, intervals in sorted(threads.items()):
        union, exclusive = union_and_exclusive(intervals)
        thread_report[thread] = {"blocking_union_ns": union,
                                 "exclusive_ns": exclusive}
    request_report = {}
    for request, values in requests.items():
        values.sort(key=lambda value: value["start_ns"])
        enqueue = next((value["start_ns"] for value in values
                        if value["phase"] == "enqueue"), None)
        worker = next((value["start_ns"] for value in values
                       if value["phase"] == "worker_start"), None)
        completion = next((value["end_ns"] for value in values
                           if value["phase"] == "complete"), None)
        demand = next((value["start_ns"] for value in values
                       if value["phase"] == "first_demand"), None)
        report = {}
        if request in dependencies:
            report["dependencies"] = sorted(dependencies[request])
            report["dependency_work_ns"] = {
                dependency: dict(collections.Counter({
                    phase: sum(value["end_ns"] - value["start_ns"]
                               for value in requests[dependency]
                               if value["phase"] == phase and
                               value.get("parent_id") == request)
                    for phase in {value["phase"] for value in requests[dependency]
                                  if value.get("parent_id") == request}
                })) for dependency in sorted(dependencies[request])
            }
        if enqueue is not None and worker is not None:
            report["queue_delay_ns"] = max(0, worker - enqueue)
        if completion is not None and demand is not None:
            report["ready_at_first_demand"] = completion <= demand
            report["readiness_delay_ns"] = max(0, completion - demand)
        if report:
            request_report[request] = report
    return {"event_counts": dict(counts), "draw_threads": thread_report,
            "requests": request_report,
            "blocking_thread_total_ns": sum(value["blocking_union_ns"]
                                            for value in thread_report.values())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()
    events = [json.loads(line) for line in args.trace.read_text().splitlines()
              if line.strip()]
    result = json.dumps(analyze(events), indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(result)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
