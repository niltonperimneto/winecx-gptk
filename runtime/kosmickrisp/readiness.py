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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("--platform", choices=("macos26", "newer"), default="macos26")
    args = parser.parse_args(argv)
    # The physical lane uploads no results when its runner is unprovisioned or
    # the job dies early; report that as missing evidence, not a traceback.
    try:
        with open(args.report) as stream:
            report = json.load(stream)
        if not isinstance(report, dict):
            raise TypeError("report is not a JSON object")
    except (OSError, TypeError, ValueError) as error:
        failures = [f"{args.platform}: physical validation results are missing or invalid ({error})"]
    else:
        failures = [f"{args.platform}: {failure}" for failure in blockers(report, args.platform)]
    for failure in failures:
        print(f"::error::{failure}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
