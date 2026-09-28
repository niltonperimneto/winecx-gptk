#!/usr/bin/env python3
"""Never convert smoke-test success into an unsupported migration claim."""
import json
import sys


def blockers(report):
    failures = []
    if report.get("schema") != 1 or report.get("passed") is not True:
        failures.append("packaged-runtime validation did not pass")
    for check in ("macos26", "manifest", "host", "loader-override-negative", "wine-x86_64", "wine-i686"):
        if report.get("checks", {}).get(check, {}).get("status") != "passed":
            failures.append(f"missing or failed check: {check}")
    for name in ("dxvk", "shader_correctness", "game"):
        result = report.get("migration", {}).get(name, {})
        if result.get("status") != "passed":
            failures.append(f"{name}: {result.get('reason', 'missing evidence')}")
    if report.get("migration", {}).get("dxvk", {}).get("known_missing"):
        failures.append("DXVK has known missing required features")
    return failures


if __name__ == "__main__":
    report = json.load(open(sys.argv[1]))
    failures = blockers(report)
    for failure in failures:
        print(f"::error::{failure}")
    raise SystemExit(bool(failures))
