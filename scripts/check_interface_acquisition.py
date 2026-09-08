#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
#
# Every COM interface acquisition must pass its holder through strictResult().
#
# A QueryInterface or GetDevice that reports S_OK with a null out-pointer
# breaks the COM contract, and the D3DMetal payload does it.  strictResult is
# the single place that rule lives; a call that checks only the HRESULT is how
# a queue belonging to another device got accepted once already.  This keeps
# the funnel mandatory rather than remembered.
#
# Usage:
#   python3 scripts/check_interface_acquisition.py [PATH ...]

import argparse
import pathlib
import re
import sys

ACQUISITION = re.compile(r"->(QueryInterface|GetDevice)\s*\(")
DEFAULT_ROOTS = ["relay12-d3d11"]


def find_violations(text):
    """(line number, line) for each acquisition that bypasses the funnel."""
    violations = []
    for number, line in enumerate(text.splitlines(), 1):
        if not ACQUISITION.search(line):
            continue
        if "strictResult(" in line:
            continue
        violations.append((number, line))
    return violations


def sources(roots):
    for root in roots:
        path = pathlib.Path(root)
        if path.is_file():
            yield path
        else:
            yield from sorted(path.rglob("*.cpp"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", default=DEFAULT_ROOTS,
                        metavar="PATH")
    args = parser.parse_args()

    errors = []
    scanned = 0
    for path in sources(args.roots):
        scanned += 1
        for number, _ in find_violations(path.read_text()):
            errors.append(f"{path}:{number}: an interface acquisition must "
                          "pass its holder through strictResult()")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"interface acquisition audit: ok ({scanned} sources)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
