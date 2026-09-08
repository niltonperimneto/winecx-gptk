#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
#
# The two rules the clean-room DDI headers are policed by.
#
# Provenance: every declaration group cites the public specification it was
# authored from and the date it was retrieved.  This cannot check that the
# cited page contains what the group claims -- that stays a discipline, and
# docs/CLEANROOM-DDI.md says so -- but it can insist the citation exists and is
# a citation.  The version this replaces could not: it tested only whether the
# string "* Specification:" appeared within three lines of the group marker, so
# an empty citation passed, a malformed date passed, and a group whose block
# was laid out differently failed for no reason.  Requiring a URL and a real
# date is the difference between a gate and a spell-check.
#
# Packing: the WDK DDI structures are not packed.  pack(1) would break every
# asserted offset and pack(8) would be a no-op that hides the real alignment
# from WINE_DDI_ASSERT_ALIGN.  The match is anchored at the start of the line
# so the headers can state the rule in prose without tripping it.
#
# Usage:
#   python3 scripts/check_ddi_header.py [PATH ...]

import argparse
import datetime
import pathlib
import re
import sys

DEFAULT_ROOTS = ["relay12-d3d11/ddi"]

GROUP = re.compile(r"\*\s*Group:(?P<name>.*)$")
SPECIFICATION = re.compile(r"\*\s*Specification:(?P<value>.*)$")
RETRIEVED = re.compile(r"\*\s*Retrieved:(?P<value>.*)$")
PRAGMA_PACK = re.compile(r"^[ \t]*#[ \t]*pragma[ \t]+pack")


def is_worked_example(lines, index):
    """Whether a group marker is the headers' own example of one.

    The rules state the required form of a provenance block by showing one, and
    write its delimiters as /### and ###/ precisely so the example is not
    itself a comment.  Its placeholders are not a URL or a date, and demanding
    that they be would make stating the rule impossible.

    A marker belongs to a real group when the nearest comment opener above it
    is a real one.  Deciding by structure rather than by recognising the
    placeholder text means a real group cannot exempt itself by resembling the
    example.
    """
    for line in reversed(lines[:index]):
        if "/###" in line:
            return True
        if "/*" in line:
            return False
    return False


def check_provenance(text):
    """One message per group whose provenance is missing or malformed."""
    errors = []
    lines = text.splitlines()

    for number, line in enumerate(lines, 1):
        match = GROUP.search(line)
        if not match:
            continue
        if is_worked_example(lines, number - 1):
            continue

        where = f"line {number}"
        if not match.group("name").strip():
            errors.append(f"{where}: a declaration group needs a name")

        # The group's own comment block, not a fixed window: the provenance
        # belongs to the block, and how many lines of prose sit between the
        # marker and the citation is the author's business.
        block = []
        closed = False
        for following in lines[number - 1:]:
            block.append(following)
            if "*/" in following:
                closed = True
                break
        if not closed:
            errors.append(f"{where}: the group's comment block is not closed, "
                          "so its provenance cannot be located")
            continue

        specifications = [
            specification.group("value").strip()
            for specification in (SPECIFICATION.search(entry)
                                  for entry in block)
            if specification
        ]
        retrievals = [
            retrieved.group("value").strip()
            for retrieved in (RETRIEVED.search(entry) for entry in block)
            if retrieved
        ]

        if not specifications:
            errors.append(f"{where}: a declaration group needs a "
                          "Specification citation")
        for specification in specifications:
            if not specification:
                errors.append(f"{where}: the Specification citation is empty")
            elif not specification.startswith("https://"):
                errors.append(f"{where}: the Specification citation is not a "
                              f"public URL: {specification!r}")

        if not retrievals:
            errors.append(f"{where}: a declaration group needs a Retrieved "
                          "date")
        for retrieved in retrievals:
            try:
                datetime.date.fromisoformat(retrieved)
            except ValueError:
                errors.append(f"{where}: the Retrieved date is not a "
                              f"YYYY-MM-DD date: {retrieved!r}")

    return errors


def check_no_pragma_pack(text):
    """One message per line that changes the packing."""
    return [
        f"line {number}: #pragma pack is prohibited in the DDI declarations"
        for number, line in enumerate(text.splitlines(), 1)
        if PRAGMA_PACK.search(line)
    ]


def headers(roots):
    for root in roots:
        path = pathlib.Path(root)
        if path.is_file():
            yield path
        else:
            yield from sorted(path.rglob("*.h"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", default=DEFAULT_ROOTS,
                        metavar="PATH")
    args = parser.parse_args()

    errors = []
    groups = 0
    for path in headers(args.roots):
        text = path.read_text()
        lines = text.splitlines()
        groups += sum(
            1 for number, line in enumerate(lines, 1)
            if GROUP.search(line) and not is_worked_example(lines, number - 1)
        )
        for message in check_provenance(text) + check_no_pragma_pack(text):
            errors.append(f"{path}:{message}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"ddi header gate: ok ({groups} declaration groups)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
