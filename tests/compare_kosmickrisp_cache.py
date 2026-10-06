import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys


COMPONENT_ORDER = ("vertex_input", "pre_raster", "depth_stencil", "blend",
                   "multisampling", "attachments", "multiview", "features")
SHADER_FIELDS = ("namespace", "precomp", "flags", "partition", "layout", "state", "key")
VARIANT_FIELDS = ("flags", "partition", "layout", "state", "key")
GENERIC_SHADER_STAGE = 6


def read_trace(path):
    events = []
    with Path(path).open() as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error.msg}") from error
            if not isinstance(event, dict) or not isinstance(event.get("event"), str):
                raise ValueError(f"{path}:{line_number}: expected an event object")
            if event["event"] == "shader":
                if (type(event.get("stage")) is not int or event["stage"] < 0
                        or not isinstance(event.get("outcome"), str)
                        or any(not isinstance(event.get(field), str) or not event[field]
                               for field in SHADER_FIELDS)):
                    raise ValueError(f"{path}:{line_number}: incomplete shader event")
                start, end = event.get("start_ns", 0), event.get("end_ns", 0)
                if type(start) is not int or type(end) is not int or start < 0 or end < start:
                    raise ValueError(f"{path}:{line_number}: invalid shader interval")
            elif event["event"] == "state_component":
                if (type(event.get("stages")) is not int or event["stages"] < 0
                        or any(not isinstance(event.get(field), str) or not event[field]
                               for field in ("namespace", "state", "component", "hash"))):
                    raise ValueError(f"{path}:{line_number}: incomplete state component")
            if event["event"] in ("shader", "state_component"):
                events.append(event)
    if not any(event["event"] == "shader" for event in events):
        raise ValueError(f"{path}: no shader trace events; enable MESA_KK_CACHE_LOG")
    return events


def index_trace(events):
    shaders, components = {}, defaultdict(dict)
    outcomes = Counter()
    intervals = set()
    for event in events:
        if event["event"] == "shader":
            if event["stage"] == GENERIC_SHADER_STAGE and event["outcome"] == "cache_deserialize_rejected":
                outcomes[event["outcome"]] += 1
                continue
            identity = (event["stage"],) + tuple(event[field] for field in SHADER_FIELDS)
            shader = shaders.setdefault(identity, {field: event[field] for field in
                                                    ("stage",) + SHADER_FIELDS})
            shader.setdefault("outcomes", Counter())[event["outcome"]] += 1
            outcomes[event["outcome"]] += 1
            if event["outcome"] in ("shaders", "shaders_failed"):
                interval = (event.get("start_ns", 0), event.get("end_ns", 0))
                if interval != (0, 0):
                    intervals.add(interval)
        elif event["event"] == "state_component":
            identity = (event["namespace"], event["state"], event["stages"])
            values = components[identity].setdefault(event["component"], set())
            values.add(event["hash"])
    groups = defaultdict(list)
    for shader in shaders.values():
        shader["outcomes"] = dict(sorted(shader["outcomes"].items()))
        groups[(shader["stage"], shader["precomp"])].append(shader)
    return groups, components, {"shader_events": sum(outcomes.values()),
                                "outcomes": dict(sorted(outcomes.items())),
                                "compiler_shader_events": outcomes["shaders"] + outcomes["shaders_failed"],
                                "compiler_intervals": len(intervals)}


def state_components(shader, components):
    result = defaultdict(set)
    for (namespace, state, stages), values in components.items():
        if namespace == shader["namespace"] and state == shader["state"] and stages & (1 << shader["stage"]):
            for name, hashes in values.items():
                result[name].update(hashes)
    return {name: next(iter(hashes)) for name, hashes in result.items() if len(hashes) == 1}


def describe_change(before, after, before_components, after_components):
    changes = [field for field in ("flags", "partition", "layout") if before[field] != after[field]]
    component_changes = []
    if before["state"] != after["state"]:
        left, right = state_components(before, before_components), state_components(after, after_components)
        component_changes = [name for name in COMPONENT_ORDER if name in left and name in right
                             and left[name] != right[name]]
        component_changes += sorted(name for name in left.keys() & right.keys()
                                    if name not in COMPONENT_ORDER and left[name] != right[name])
        changes.extend("state." + name for name in component_changes)
        if not component_changes:
            changes.append("state (component evidence unavailable)")
    if before["key"] != after["key"] and not changes:
        changes.append("key (unexplained by logged components)")
    if before["namespace"] != after["namespace"]:
        changes.append("namespace")
    return {"stage": before["stage"], "precomp": before["precomp"],
            "before": before, "after": after, "first_difference": changes[0],
            "differences": changes}


def compare_traces(before_events, after_events):
    before, before_components, before_counts = index_trace(before_events)
    after, after_components, after_counts = index_trace(after_events)
    before_namespaces = sorted({event["namespace"] for event in before_events if "namespace" in event})
    after_namespaces = sorted({event["namespace"] for event in after_events if "namespace" in event})
    report = {"schema": 1, "namespace_diff": {"before": before_namespaces, "after": after_namespaces,
              "changed": before_namespaces != after_namespaces},
              "before_counts": before_counts, "after_counts": after_counts,
              "stable_keys": [], "stable_key_misses": [], "key_changes": [],
              "cache_rejects": [], "unpaired_variants": []}
    for group in sorted(before.keys() | after.keys()):
        left, right = list(before.get(group, [])), list(after.get(group, []))
        pairs = []
        for shader in list(left):
            exact = [candidate for candidate in right if all(shader[field] == candidate[field]
                                                              for field in ("namespace",) + VARIANT_FIELDS)]
            if len(exact) == 1:
                pairs.append((shader, exact[0]))
                left.remove(shader)
                right.remove(exact[0])
        for shader in list(left):
            equivalent = [candidate for candidate in right if all(shader[field] == candidate[field]
                                                                   for field in VARIANT_FIELDS)]
            if len(equivalent) != 1:
                continue
            candidate = equivalent[0]
            reciprocal = [item for item in left if all(item[field] == candidate[field] for field in VARIANT_FIELDS)]
            if len(reciprocal) == 1:
                pairs.append((shader, candidate))
                left.remove(shader)
                right.remove(candidate)
        if len(left) == len(right) == 1:
            pairs.append((left.pop(), right.pop()))
        for previous, current in pairs:
            stable = previous["key"] == current["key"]
            if stable:
                report["stable_keys"].append({"stage": group[0], "precomp": group[1], "key": current["key"],
                                               "namespace": current["namespace"]})
                if previous["namespace"] == current["namespace"] and current["outcomes"].get("miss", 0):
                    report["stable_key_misses"].append(current)
            if any(previous[field] != current[field] for field in ("namespace",) + VARIANT_FIELDS):
                report["key_changes"].append(describe_change(previous, current, before_components, after_components))
        if left or right:
            report["unpaired_variants"].append({"stage": group[0], "precomp": group[1],
                                                 "before": left, "after": right,
                                                 "reason": "ambiguous variants" if left and right else "only present in one run"})
    for run, events in (("before", before_events), ("after", after_events)):
        generic_rejects = Counter((event["namespace"], event["key"]) for event in events
                                  if event["event"] == "shader" and event["stage"] == GENERIC_SHADER_STAGE
                                  and event["outcome"] == "cache_deserialize_rejected")
        for (namespace, key), count in sorted(generic_rejects.items()):
            semantic_stages = sorted({event["stage"] for event in events
                                      if event["event"] == "shader" and event["stage"] != GENERIC_SHADER_STAGE
                                      and event["namespace"] == namespace and event["key"] == key})
            report["cache_rejects"].append({"run": run, "namespace": namespace, "key": key,
                                            "shader_stages": semantic_stages,
                                            "rejects": {"cache_deserialize_rejected": count}})
    for run, groups in (("before", before), ("after", after)):
        for variants in groups.values():
            for shader in variants:
                rejects = {name: count for name, count in shader["outcomes"].items()
                           if "reject" in name or "incompatible" in name or name == "deserialize_failed"}
                if rejects:
                    report["cache_rejects"].append({"run": run, **shader, "rejects": rejects})
    report["summary"] = {name: len(report[name]) for name in
                         ("stable_keys", "stable_key_misses", "key_changes", "cache_rejects", "unpaired_variants")}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare KosmicKrisp shader-cache traces without event-order matching")
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        report = compare_traces(read_trace(args.before), read_trace(args.after))
        report["inputs"] = {"before": str(args.before), "after": str(args.after)}
        output = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.out:
            args.out.write_text(output)
        else:
            sys.stdout.write(output)
    except (ValueError, OSError) as error:
        parser.exit(2, f"cache comparison: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
