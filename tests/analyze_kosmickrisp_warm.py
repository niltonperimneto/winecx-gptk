import argparse
import collections
import json
from pathlib import Path

from analyze_kosmickrisp_variants import analyze, union_and_exclusive


COMPONENTS = ("flags", "partition", "layout", "state")
ACCEPTED = {"shaders", "disk_hit", "application_hit"}


def shader_ledger(events, previous):
    known = {(e["namespace"], e["key"]): e for e in previous
             if e.get("event") == "shader" and e.get("outcome") in ACCEPTED}
    families = collections.defaultdict(list)
    states = collections.defaultdict(dict)
    for event in previous + events:
        if event.get("event") == "state_component":
            states[event["namespace"], event["state"]][event["component"]] = event["hash"]
    for event in known.values():
        families[event.get("stage"), event.get("precomp")].append(event)
    ledger = []
    lookups = {}
    for event in events:
        if (event.get("event") == "shader" and event.get("outcome") in
                ("disk_hit", "application_hit", "miss", "deserialize_rejected")):
            lookups[event["namespace"], event["key"]] = event["outcome"]
        if event.get("event") != "shader" or event.get("outcome") != "shaders":
            continue
        identity = event["namespace"], event["key"]
        candidates = families[event.get("stage"), event.get("precomp")]
        same_namespace = [e for e in candidates
                          if e["namespace"] == event["namespace"]]
        changed = []
        changed_state = []
        closest = None
        if identity in known:
            reason = ("cached_partition_peer_recompiled"
                      if lookups.get(identity) in ("disk_hit", "application_hit")
                      else "previously_accepted_key_recompiled")
        elif same_namespace:
            closest = min(same_namespace, key=lambda e:
                          sum(e.get(k) != event.get(k) for k in COMPONENTS))
            changed = [k for k in COMPONENTS if closest.get(k) != event.get(k)]
            old_state = states[closest["namespace"], closest["state"]]
            new_state = states[event["namespace"], event["state"]]
            changed_state = sorted(k for k in old_state.keys() | new_state.keys()
                                   if old_state.get(k) != new_state.get(k))
            reason = "new_state" if changed else "unexplained_key_change"
        elif candidates:
            reason = "namespace_change"
        else:
            reason = "new_shader"
        ledger.append({**event, "classification": reason,
                       "lookup_outcome": lookups.get(identity),
                       "changed_components": changed,
                       "changed_state_components": changed_state,
                       "comparison_key": closest["key"] if closest else None})
    failed = [e for e in events if e.get("event") == "shader" and
              e.get("outcome") == "shaders_failed"]
    calls = {(e.get("pid"), e.get("thread_id"), e.get("start_ns"),
              e.get("end_ns")) for e in ledger + failed}
    return {"counts": dict(collections.Counter(e["classification"] for e in ledger)),
            "compilation_events": len(ledger), "failed_events": failed,
            "compilation_calls": len(calls), "ledger": ledger}


def native_ledger(events, previous, persisted_through=None, persisted_from=0):
    accepted = {"compiler_fallback", "compute_fallback", "archive_hit",
                "compute_archive_hit"}
    known = {(e["namespace"], e["key"]) for e in previous
             if e.get("event") == "pso" and e.get("outcome") in accepted}
    checkpointed = {(e["namespace"], e["key"]) for e in previous
                    if e.get("event") == "pso" and e.get("outcome") in accepted
                    and (persisted_through is not None and
                         (e.get("outcome") in ("archive_hit", "compute_archive_hit")
                          or persisted_from <= e.get("time_ns", float("inf"))
                          <= persisted_through))}
    if persisted_through is None:
        checkpointed = known
    ledger = []
    for event in events:
        if (event.get("event") != "pso" or event.get("outcome") not in
                ("compiler_fallback", "compute_fallback")):
            continue
        identity = event["namespace"], event["key"]
        reason = ("new_native_key" if identity not in known else
                  "previous_native_key_not_checkpointed" if identity not in checkpointed
                  else "previous_native_key_without_archive_hit")
        ledger.append({**event, "classification": reason})
    return {"counts": dict(collections.Counter(e["classification"] for e in ledger)),
            "compilation_events": len(ledger), "ledger": ledger}


def wait_ledger(events, begin=None, finish=None):
    requests = collections.defaultdict(list)
    children = collections.defaultdict(set)
    for event in events:
        if event.get("event") == "variant":
            requests[event["request_id"]].append(event)
            if event.get("parent_id"):
                children[event["parent_id"]].add(event["request_id"])
    ledger = []
    for event in events:
        if (event.get("event") != "variant" or event.get("origin") != "draw" or
                event.get("phase") not in ("pso_wait", "fs_wait", "raster_wait")):
            continue
        start, end = event["start_ns"], event["end_ns"]
        start = max(start, begin) if begin is not None else start
        end = min(end, finish) if finish is not None else end
        if end <= start:
            continue
        identity = event["request_id"]
        identities = {identity}
        pending = [identity]
        while pending:
            key = pending.pop()
            owners = {e["parent_id"] for e in requests[key]
                      if e["phase"] == "pso_create" and e.get("parent_id")}
            for child in (children[key] | owners) - identities:
                identities.add(child)
                pending.append(child)
        related = [e for key in identities for e in requests[key]]
        workers = [e for e in requests[identity] if e["phase"] == "worker_start"]
        enqueues = [e for e in requests[identity] if e["phase"] == "enqueue"]
        owner_work = []
        for dependency in related:
            if dependency["origin"] == "draw":
                continue
            left = max(start, dependency["start_ns"])
            right = min(end, dependency["end_ns"])
            if right > left and dependency["phase"] in (
                    "fs_prepare", "raster_prepare", "native_create",
                    "archive_lookup", "archive_load", "history_load", "pso_create"):
                owner_work.append((left, right, dependency["phase"]))
        active_workers = [e for e in workers if e["start_ns"] <= end]
        queue_delay = 0
        if enqueues and active_workers:
            queued = min(e["start_ns"] for e in enqueues)
            begun = min(e["start_ns"] for e in active_workers)
            queue_delay = max(0, min(end, begun) - max(start, queued))
            if queue_delay:
                owner_work.append((max(start, queued), min(end, begun), "queue_delay"))
        explained, exclusive = union_and_exclusive(owner_work)
        ledger.append({**event, "start_ns": start, "end_ns": end,
                       "duration_ns": end - start,
                       "owner_work_ns": exclusive,
                       "queue_delay_during_wait_ns": exclusive.pop("queue_delay", 0),
                       "raw_queue_overlap_ns": queue_delay,
                       "unattributed_ns": max(0, end - start - explained),
                       "worker_threads": sorted({e["thread_id"] for e in related
                                                  if e["origin"] != "draw"})})
    return ledger


def load_jsonl(path):
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--previous-cache", type=Path, action="append", default=[])
    parser.add_argument("--variants", type=Path)
    parser.add_argument("--start-ns", type=int)
    parser.add_argument("--end-ns", type=int)
    parser.add_argument("--persisted-through-ns", type=int)
    parser.add_argument("--persisted-from-ns", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    previous = [e for path in args.previous_cache for e in load_jsonl(path)]
    events = load_jsonl(args.cache)
    report = {"shader_compilations": shader_ledger(events, previous),
              "native_compilations": native_ledger(events, previous,
                                                    args.persisted_through_ns,
                                                    args.persisted_from_ns),
              "cache_outcomes": dict(collections.Counter(
                  f'{e["event"]}/{e.get("outcome", "")}' for e in events
                  if e["event"] != "state_component"))}
    if args.variants:
        variants = load_jsonl(args.variants)
        report["variants"] = analyze(variants)
        report["draw_waits"] = wait_ledger(variants)
        if args.start_ns is not None or args.end_ns is not None:
            report["window_draw_waits"] = wait_ledger(variants, args.start_ns,
                                                       args.end_ns)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
