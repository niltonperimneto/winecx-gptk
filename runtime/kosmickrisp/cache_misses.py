#!/usr/bin/env python3
"""Classify KosmicKrisp shader cache misses across runs.

Usage: cache_misses.py RUN_DIR [RUN_DIR ...]   (oldest first)

Each RUN_DIR must contain cache.jsonl written via MESA_KK_CACHE_LOG.
"""
import collections
import json
import pathlib
import sys

KEY_PARTS = ("precomp", "flags", "partition", "layout", "state")


def load(run):
    path = pathlib.Path(run) / "cache.jsonl"
    shaders, components = [], collections.defaultdict(dict)
    with open(path) as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "shader":
                shaders.append(e)
            elif e.get("event") == "state_component":
                components[e["state"]][e["component"]] = e["hash"]
    return shaders, components


def main(runs):
    seen_keys = set()
    by_code = collections.defaultdict(list)
    all_components = {}

    for index, run in enumerate(runs):
        shaders, components = load(run)
        all_components.update(components)
        outcomes = collections.Counter(e["outcome"] for e in shaders)
        print(f"== {run}")
        print("   outcomes:", dict(outcomes))

        buckets = collections.Counter()
        state_diff = collections.Counter()
        missed_this_run = set()
        examples = {}
        for e in shaders:
            if e["outcome"] != "miss":
                continue
            if e["key"] in missed_this_run:
                bucket = "repeat miss in same run (never stored)"
            elif e["key"] in seen_keys:
                bucket = "key seen in earlier run (lost from disk cache)"
            else:
                prior = by_code.get((e["stage"], e["precomp"]), [])
                if not prior:
                    bucket = "new precomp (SPIR-V/spec/robustness)"
                else:
                    best = min(prior, key=lambda p: sum(
                        p[k] != e[k] for k in KEY_PARTS))
                    diff = [k for k in KEY_PARTS[1:] if best[k] != e[k]]
                    bucket = "same precomp, differs in " + "+".join(diff)
                    if diff == ["state"]:
                        a = all_components.get(best["state"], {})
                        b = all_components.get(e["state"], {})
                        changed = sorted(c for c in set(a) | set(b)
                                         if a.get(c) != b.get(c))
                        state_diff[",".join(changed) or "unknown"] += 1
            buckets[bucket] += 1
            examples.setdefault(bucket, e["key"])
            missed_this_run.add(e["key"])

        if index > 0:
            for bucket, count in buckets.most_common():
                print(f"   {count:5d}  {bucket}  (e.g. {examples[bucket][:16]})")
            for comps, count in state_diff.most_common():
                print(f"          {count:5d}  state components changed: {comps}")

        for e in shaders:
            seen_keys.add(e["key"])
            by_code[(e["stage"], e["precomp"])].append(e)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1:])
