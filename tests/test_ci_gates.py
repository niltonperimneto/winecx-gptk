#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
#
# Tests for the checks that guard the D3D11On12 work.
#
# These gates used to be heredocs inside .github/workflows/pull-request.yml,
# where nothing could run them but CI and nothing could test them at all.  A
# gate with no test is a gate that passes everything from the day its pattern
# stops matching, and it fails silently: the run stays green, which is exactly
# the signal it exists to withhold.
#
# So each gate is tested for both answers.  Asserting that a correct tree
# passes proves nothing on its own -- an empty check does that too -- so every
# rule a gate claims to enforce is given something that breaks it.
#
# Run: python3 -m unittest discover -s tests -p 'test_*.py'

import pathlib
import subprocess
import sys
import tempfile
import unittest

REPOSITORY = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "scripts"))

import check_ddi_header  # noqa: E402
import check_interface_acquisition  # noqa: E402
import check_pe_audit  # noqa: E402
import gen_ddi_layout  # noqa: E402

DDI_HEADER = REPOSITORY / "relay12-d3d11" / "ddi" / "wine_d3d11ddi.h"

GOOD_GROUP = """\
/*
 * Group: a well formed group
 * Specification: https://learn.microsoft.com/en-us/example
 * Retrieved: 2026-09-07
 */
typedef struct example { void *field; } example;
"""


def written(text, suffix=".h"):
    """A temporary file holding text, returned as a path."""
    handle = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False)
    with handle:
        handle.write(text)
    return pathlib.Path(handle.name)


class DdiHeaderGate(unittest.TestCase):
    def test_a_well_formed_group_passes(self):
        self.assertEqual(check_ddi_header.check_provenance(GOOD_GROUP), [])

    def test_the_committed_headers_pass(self):
        self.assertEqual(
            check_ddi_header.check_provenance(DDI_HEADER.read_text()), [])
        self.assertEqual(
            check_ddi_header.check_no_pragma_pack(DDI_HEADER.read_text()), [])

    def test_the_rules_own_worked_example_is_not_a_group(self):
        """The headers state the required form by showing it, with /### for
        delimiters so the example is not a comment.  Its placeholders are not a
        URL or a date, and the gate must not demand that they be."""
        example = """\
/*
 * Rules:
 *
 *          /###
 *           * Group: <name>
 *           * Specification: <public URL>
 *           * Retrieved: <YYYY-MM-DD>
 *           ###/
 */
"""
        self.assertEqual(check_ddi_header.check_provenance(example), [])

    def test_a_real_group_cannot_hide_behind_the_example(self):
        """Structure decides, not the placeholder text: a group that opens a
        real comment is checked however much it resembles the example."""
        disguised = """\
/*
 * Group: <name>
 * Specification: <public URL>
 * Retrieved: <YYYY-MM-DD>
 */
"""
        errors = check_ddi_header.check_provenance(disguised)
        self.assertTrue(any("not a public URL" in error for error in errors))
        self.assertTrue(any("not a YYYY-MM-DD" in error for error in errors))

    def test_an_empty_citation_is_rejected(self):
        """The hole this gate was rewritten for: the old check tested only
        whether the string appeared, so a group citing nothing passed."""
        empty = GOOD_GROUP.replace(
            "Specification: https://learn.microsoft.com/en-us/example",
            "Specification:")
        errors = check_ddi_header.check_provenance(empty)
        self.assertTrue(any("empty" in error for error in errors), errors)

    def test_a_citation_that_is_not_a_url_is_rejected(self):
        errors = check_ddi_header.check_provenance(GOOD_GROUP.replace(
            "https://learn.microsoft.com/en-us/example", "the WDK header"))
        self.assertTrue(any("not a public URL" in error for error in errors))

    def test_a_malformed_date_is_rejected(self):
        for date in ("2026-13-45", "07/09/2026", "yesterday", ""):
            with self.subTest(date=date):
                errors = check_ddi_header.check_provenance(
                    GOOD_GROUP.replace("2026-09-07", date))
                self.assertTrue(errors, f"{date!r} was accepted as a date")

    def test_a_missing_citation_is_rejected(self):
        for line in ("Specification", "Retrieved"):
            with self.subTest(missing=line):
                stripped = "\n".join(
                    entry for entry in GOOD_GROUP.splitlines()
                    if f"* {line}:" not in entry)
                errors = check_ddi_header.check_provenance(stripped)
                self.assertTrue(errors, f"a group with no {line} passed")

    def test_an_unnamed_group_is_rejected(self):
        errors = check_ddi_header.check_provenance(
            GOOD_GROUP.replace("Group: a well formed group", "Group:"))
        self.assertTrue(any("needs a name" in error for error in errors))

    def test_provenance_may_sit_further_down_the_block(self):
        """The check this replaces inspected a four-line window, so a group
        with prose before its citation failed for no reason."""
        spaced = GOOD_GROUP.replace(
            " * Group: a well formed group\n",
            " * Group: a well formed group\n *\n * Four\n * lines\n * of\n"
            " * prose.\n *\n")
        self.assertEqual(check_ddi_header.check_provenance(spaced), [])

    def test_an_unclosed_block_is_rejected(self):
        errors = check_ddi_header.check_provenance(
            "/*\n * Group: unterminated\n * Specification: https://x/\n")
        self.assertTrue(any("not closed" in error for error in errors))

    def test_pragma_pack_is_rejected_but_naming_it_is_not(self):
        self.assertEqual(check_ddi_header.check_no_pragma_pack(
            " * #pragma pack is prohibited in this header.\n"), [])
        for pragma in ("#pragma pack(1)", "  #pragma  pack(push, 8)",
                       "#\tpragma pack()"):
            with self.subTest(pragma=pragma):
                self.assertTrue(
                    check_ddi_header.check_no_pragma_pack(pragma + "\n"))


class InterfaceAcquisitionGate(unittest.TestCase):
    def test_a_funnelled_acquisition_passes(self):
        source = ("hr = strictResult(device->QueryInterface(iid, out), "
                  "holder);\n")
        self.assertEqual(
            check_interface_acquisition.find_violations(source), [])

    def test_the_committed_sources_pass(self):
        for path in sorted((REPOSITORY / "relay12-d3d11").rglob("*.cpp")):
            with self.subTest(source=path.name):
                self.assertEqual(
                    check_interface_acquisition.find_violations(
                        path.read_text()), [])

    def test_a_bypassed_acquisition_is_rejected(self):
        for source in ("hr = device->QueryInterface(iid, out);\n",
                       "hr = queue->GetDevice(iid, out);\n",
                       "if (FAILED(queue->GetDevice (iid, out)))\n"):
            with self.subTest(source=source.strip()):
                self.assertEqual(
                    len(check_interface_acquisition.find_violations(source)), 1)


# objdump -p output, trimmed to the parts the audit reads.
OBJDUMP = """\
d3d11shim.dll:     file format pei-x86-64

The Export Tables (interpreted .edata section contents)

Export Flags                    0
Ordinal Base                    1
Number in:
\tExport Address Table           \t00000004
\t[Name Pointer/Ordinal] Table   \t00000004

[Ordinal/Name Pointer] Table
\t[   0] D3D11CreateDevice
\t[   1] D3D11CreateDeviceAndSwapChain
\t[   2] D3D11On12CreateDevice
\t[   3] WineD3D11ShimGetStatus

There is an import table in .idata

The Import Tables (interpreted .idata section contents)

\tDLL Name: KERNEL32.dll
\tvma:  Hint/Ord

\tDLL Name: msvcrt.dll
\tvma:  Hint/Ord
"""


class PeAudit(unittest.TestCase):
    def test_exports_are_read_with_the_ordinal_base(self):
        """The name-pointer table is indexed from zero and the base is printed
        separately, so reading the indices as ordinals would pass a module
        whose base was not 1."""
        self.assertEqual(check_pe_audit.parse_exports(OBJDUMP), {
            1: "D3D11CreateDevice",
            2: "D3D11CreateDeviceAndSwapChain",
            3: "D3D11On12CreateDevice",
            4: "WineD3D11ShimGetStatus",
        })
        rebased = OBJDUMP.replace("Ordinal Base                    1",
                                  "Ordinal Base                    7")
        self.assertEqual(min(check_pe_audit.parse_exports(rebased)), 7)

    def test_imports_are_lowercased(self):
        self.assertEqual(check_pe_audit.parse_imports(OBJDUMP),
                         {"kernel32.dll", "msvcrt.dll"})

    def test_the_expected_router_passes(self):
        self.assertEqual(
            check_pe_audit.audit("d3d11shim.dll", OBJDUMP, False), [])

    def test_a_renamed_export_is_rejected(self):
        renamed = OBJDUMP.replace("D3D11On12CreateDevice",
                                  "D3D11On12CreateDeviceEx")
        errors = check_pe_audit.audit("d3d11shim.dll", renamed, False)
        self.assertTrue(any("exports" in error for error in errors), errors)

    def test_a_reordered_export_is_rejected(self):
        """Applications may bind by ordinal, so the order is the contract."""
        reordered = OBJDUMP.replace(
            "\t[   0] D3D11CreateDevice\n"
            "\t[   1] D3D11CreateDeviceAndSwapChain\n",
            "\t[   0] D3D11CreateDeviceAndSwapChain\n"
            "\t[   1] D3D11CreateDevice\n")
        self.assertTrue(check_pe_audit.audit("d3d11shim.dll", reordered, False))

    def test_an_extra_import_is_rejected(self):
        extra = OBJDUMP.replace("\tDLL Name: msvcrt.dll",
                                "\tDLL Name: ntdll.dll\n\tvma:  Hint/Ord\n"
                                "\n\tDLL Name: msvcrt.dll")
        errors = check_pe_audit.audit("d3d11shim.dll", extra, False)
        self.assertTrue(any("imports" in error for error in errors), errors)

    def test_a_cxx_runtime_dependency_is_rejected(self):
        for library in ("libstdc++-6.dll", "libgcc_s_seh-1.dll"):
            with self.subTest(library=library):
                text = OBJDUMP + f"\n\tDLL Name: {library}\n"
                self.assertTrue(check_pe_audit.find_cxx_runtime(text))
                self.assertTrue(
                    check_pe_audit.audit("anything.exe", text, True))

    def test_an_unknown_module_needs_an_expectation(self):
        errors = check_pe_audit.audit("d3d11mystery.dll", OBJDUMP, False)
        self.assertTrue(any("no expected export table" in error
                            for error in errors), errors)


class LayoutModel(unittest.TestCase):
    """gen_ddi_layout.py --check is the second opinion on the header's
    offsets.  Its three fault classes were verified by hand once; this is so
    they stay verified."""

    def setUp(self):
        self.header = DDI_HEADER.read_text()

    def check(self, text):
        return gen_ddi_layout.check(written(text))

    def test_the_committed_header_agrees_with_the_model(self):
        self.assertEqual(self.check(self.header), [])

    def test_a_wrong_offset_is_caught(self):
        broken = self.header.replace(
            "WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, hRTCoreLayer, 56)",
            "WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, hRTCoreLayer, 48)")
        self.assertNotEqual(broken, self.header)
        errors = self.check(broken)
        self.assertTrue(any("the model computes 56" in error
                            for error in errors), errors)

    def test_an_unasserted_field_is_caught(self):
        broken = self.header.replace(
            "WINE_DDI_ASSERT_FIELD(DXGI_DDI_BASE_ARGS, pDXGIBaseCallbacks, 0);\n",
            "")
        self.assertNotEqual(broken, self.header)
        errors = self.check(broken)
        self.assertTrue(any("not asserted anywhere" in error
                            for error in errors), errors)

    def test_an_assertion_for_an_unmodelled_field_is_caught(self):
        broken = self.header.replace(
            "WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, Flags, 72);",
            "WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, Flags, 72);\n"
            "WINE_DDI_ASSERT_FIELD(D3D10DDIARG_CREATEDEVICE, "
            "pWDDM2_2UMCallbacks, 64);")
        self.assertNotEqual(broken, self.header)
        errors = self.check(broken)
        self.assertTrue(any("absent from the model" in error
                            for error in errors), errors)

    def test_a_wrong_size_is_caught(self):
        broken = self.header.replace(
            "WINE_DDI_ASSERT_SIZE(D3D10DDIARG_CREATEDEVICE, 88)",
            "WINE_DDI_ASSERT_SIZE(D3D10DDIARG_CREATEDEVICE, 96)")
        self.assertNotEqual(broken, self.header)
        self.assertTrue(any("88 bytes" in error for error in self.check(broken)))

    def test_the_declared_and_published_arms_agree(self):
        """Dropping the union arms the driver does not read must not move
        anything; this is what makes that a declaration choice."""
        for struct in gen_ddi_layout.GROUPS:
            with self.subTest(struct=struct.name):
                declared = struct.walk(published=False)
                published = struct.walk(published=True)
                self.assertEqual(declared[1], published[1])
                self.assertEqual(declared[2], published[2])
                for name, offset in declared[0].items():
                    if name in published[0]:
                        self.assertEqual(offset, published[0][name])


class GateEntryPoints(unittest.TestCase):
    """Each gate must also work as CI invokes it: from the repository root,
    with an exit status."""

    def run_gate(self, *arguments):
        return subprocess.run(
            [sys.executable, *arguments], cwd=REPOSITORY,
            capture_output=True, text=True)

    def test_the_gates_pass_on_the_committed_tree(self):
        for gate in (["scripts/check_ddi_header.py"],
                     ["scripts/check_interface_acquisition.py"],
                     ["scripts/gen_ddi_layout.py", "--check"]):
            with self.subTest(gate=gate[0]):
                result = self.run_gate(*gate)
                self.assertEqual(result.returncode, 0,
                                 result.stdout + result.stderr)

    def test_a_failing_gate_exits_nonzero(self):
        broken = written("/*\n * Group:\n */\n")
        result = self.run_gate("scripts/check_ddi_header.py", str(broken))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("needs a name", result.stderr)


if __name__ == "__main__":
    unittest.main()
