#!/usr/bin/env python3
"""Never convert smoke-test success into an unsupported migration claim."""
import argparse
import json


def blockers(report, platform="macos26"):
    failures = []
    if report.get("schema") != 1 or report.get("passed") is not True:
        failures.append("packaged-runtime validation did not pass")
    for check in (("macos26" if platform == "macos26" else "platform"), "manifest", "host",
                  "loader-override-negative", "loader-override-empty-negative", "loader-missing-negative", "loader-corrupt-negative",
                  "wine-without-vulkan", "wine-x86_64", "wine-i686"):
        if report.get("checks", {}).get(check, {}).get("status") != "passed":
            failures.append(f"missing or failed check: {check}")
    try:
        major = int(report.get("os", "").split(".")[0])
        if (major != 26 if platform == "macos26" else major <= 26):
            failures.append("physical evidence uses the wrong OS lane")
        if report.get("checks", {}).get("platform", {}).get("lane") != platform:
            failures.append("physical evidence is missing its OS lane identity")
    except (ValueError, AttributeError):
        failures.append("physical evidence is missing its OS version")
    for name in ("dxvk", "shader_correctness", "game"):
        result = report.get("migration", {}).get(name, {})
        if result.get("status") != "passed":
            failures.append(f"{name}: {result.get('reason', 'missing evidence')}")
    if report.get("migration", {}).get("dxvk", {}).get("known_missing"):
        failures.append("DXVK has known missing required features")
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("--platform", choices=("macos26", "newer"), default="macos26")
    args = parser.parse_args()
    report = json.load(open(args.report))
    failures = blockers(report, args.platform)
    for failure in failures:
        print(f"::error::{failure}")
    raise SystemExit(bool(failures))
