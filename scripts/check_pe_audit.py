#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
#
# Audit the built PE modules' exports, imports and runtime dependencies.
#
# These rules were inline in .github/workflows/pull-request.yml, where they
# could not be run before pushing and could not be tested at all. A gate with
# no test passes everything the day its pattern stops matching, which for an
# export-ordinal check means the router silently stops looking like Apple's
# forwarder.
#
# What each rule is for:
#
#   exports  Apple's d3d11.dll exports exactly three entry points at ordinals
#            1 to 3, and an application may bind to them by ordinal.  The
#            router has to present the same table, with the Wine-private
#            status entry point above it rather than among it.
#   imports  Both modules resolve __wine_dbg_output at run time instead of
#            linking it, which is what keeps their import tables down to
#            kernel32 and msvcrt.  If that ever became a real import, this is
#            what says so.
#   runtime  A libstdc++ or libgcc_s dependency would make these modules
#            undeployable in a Wine prefix, and it appears by accident: one
#            unguarded C++ construct is enough.
#
# Usage:
#   python3 scripts/check_pe_audit.py d3d11shim.dll d3d11on12core.dll
#   python3 scripts/check_pe_audit.py --runtime-only d3d11on12coretest.exe

import argparse
import os
import re
import subprocess
import sys

DEFAULT_OBJDUMP = "x86_64-w64-mingw32-objdump"

# Ordinals 1 to 3 are Apple's exact export table.  The fourth is the
# Wine-private status entry point deployment gates on, because
# DXGI_ERROR_UNSUPPORTED cannot distinguish "unsupported here" from "installed
# wrong".  It is named so it cannot collide with a future Apple export.
EXPECTED_EXPORTS = {
    "d3d11shim.dll": {
        1: "D3D11CreateDevice",
        2: "D3D11CreateDeviceAndSwapChain",
        3: "D3D11On12CreateDevice",
        4: "WineD3D11ShimGetStatus",
    },
    "d3d11on12core.dll": {
        1: "WineD3D11On12GetABIVersion",
        2: "WineD3D11On12CreateDeviceV1",
        3: "WineD3D11On12GetInterface",
    },
}

EXPECTED_IMPORTS = {
    "d3d11shim.dll": {"kernel32.dll", "msvcrt.dll"},
    "d3d11on12core.dll": {"kernel32.dll", "msvcrt.dll"},
}

CXX_RUNTIME = re.compile(r"libstdc\+\+|libgcc_s", re.IGNORECASE)


def parse_exports(text):
    """Ordinal to name, from `objdump -p` output.

    The name-pointer table is indexed from zero and the ordinal base is
    printed separately, so an export's ordinal is the sum.  Reading the
    indices as ordinals would pass a module whose base was not 1.
    """
    base_match = re.search(r"Ordinal Base\s+(\d+)", text)
    if not base_match:
        raise ValueError("no export ordinal base in the objdump output")
    base = int(base_match.group(1))

    _, _, after = text.partition("[Ordinal/Name Pointer] Table")
    if not after:
        raise ValueError("no export name-pointer table in the objdump output")
    table = after.split("\n\n", 1)[0]

    return {
        base + int(index): name
        for index, name in re.findall(r"\[\s*(\d+)\]\s+(\S+)", table)
    }


def parse_imports(text):
    """The set of imported DLL names, lowercased."""
    return {name.lower() for name in re.findall(r"DLL Name:\s+(\S+)", text)}


def find_cxx_runtime(text):
    """The lines naming a C++ runtime dependency, if any."""
    return [line for line in text.splitlines() if CXX_RUNTIME.search(line)]


def audit(path, text, runtime_only):
    module = os.path.basename(path)
    errors = []

    for line in find_cxx_runtime(text):
        errors.append(f"{module}: unexpected C++ runtime dependency: "
                      f"{line.strip()}")

    if runtime_only:
        return errors

    if module not in EXPECTED_EXPORTS:
        return errors + [
            f"{module}: no expected export table is recorded for this module; "
            "add one to scripts/check_pe_audit.py or pass --runtime-only"
        ]

    try:
        exports = parse_exports(text)
    except ValueError as error:
        return errors + [f"{module}: {error}"]

    if exports != EXPECTED_EXPORTS[module]:
        errors.append(f"{module}: exports {exports}, expected "
                      f"{EXPECTED_EXPORTS[module]}")

    imports = parse_imports(text)
    if imports != EXPECTED_IMPORTS[module]:
        errors.append(f"{module}: imports {sorted(imports)}, expected "
                      f"{sorted(EXPECTED_IMPORTS[module])}")

    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modules", nargs="+", metavar="MODULE")
    parser.add_argument("--objdump", default=DEFAULT_OBJDUMP,
                        help=f"objdump to run (default: {DEFAULT_OBJDUMP})")
    parser.add_argument("--runtime-only", action="store_true",
                        help="check only for a C++ runtime dependency")
    args = parser.parse_args()

    errors = []
    for path in args.modules:
        try:
            text = subprocess.check_output([args.objdump, "-p", path],
                                           text=True)
        except (OSError, subprocess.CalledProcessError) as error:
            errors.append(f"{path}: could not read the PE headers: {error}")
            continue
        errors.extend(audit(path, text, args.runtime_only))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    checked = ", ".join(os.path.basename(path) for path in args.modules)
    print(f"pe audit: ok ({checked})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
