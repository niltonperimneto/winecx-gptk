# Contributing to the runtime hub

A reviewable change connects a concrete problem to a small implementation and
evidence that the resulting runtime still works. Read the
[architecture and ownership guide](docs/architecture.md) before choosing where
to edit, and [AGENTS.md](AGENTS.md) and [SKILLS.md](SKILLS.md) when using an agent.
The [QA guide](docs/qa.md) defines the evidence required for completion.

## 1. Define the change

Describe the trigger, current behavior and expected result. For a regression,
record the failing revision and a known working revision where available. Name
the affected OS, architecture, graphics backend and consumer interface.

Choose a specific acceptance condition: for example, "the relocated archive
loads all bundled libraries" or "the same i686 compute probe returns the four
expected values." "Build succeeds" is insufficient for a renderer correctness
change. Separate an experimental hypothesis from a behavior established by data.

Check the current branch and unrelated work before starting:

```sh
git status --short
git branch --show-current
git switch -c fix/describe-the-problem
```

Use a focused branch from the intended base. Do not reset, stash, delete or
reformat another contributor's work merely to make the checkout look clean.
If the branch has relevant in-progress changes, continue deliberately rather
than silently replacing them.

## 2. Write code at the owning boundary

| Work | Location |
| --- | --- |
| Build/fetch/assembly/package behavior | A focused script in `tools/` |
| Shared build environment, archive handling, cache inputs or pin updates | `tools/build/` |
| Job dependencies, permissions, triggers and artifact references | `.github/workflows/` |
| Consumer layout contract and checker | `contracts/runtime-layout.json`, `tools/check_runtime_layout.py`, and coordinated Whisky changes |
| Hub-specific GPTK video/DXGI adapters | `gptk-video/` |
| Experimental KosmicKrisp integration and validation helpers | `runtime/kosmickrisp/` |
| Native ARM64/FEX experiments | `arm64/` and their explicitly scoped helpers/tests |
| Regression tests and executable probes | `tests/`, next to related test coverage |
| Maintained interfaces, rationale and concise evidence | `docs/` and the root guides |
| Wine, Mesa, Relay12, DXMT or Whisky implementation | The component repository; integrate its tested revision here |

Keep logic testable and shared by local builds and CI. Extend an existing helper
when it owns the behavior; introduce a new module when it has a distinct
responsibility. Avoid a generic framework for one call site or a large unrelated
refactor in a bug fix. Preserve error propagation and deterministic inputs.

For shell changes, quote paths, support spaces, and keep environment changes
scoped to the relevant process. For Python helpers, keep parsing and validation
testable without network access when possible. For native adapters, preserve
the applicable COM/ABI, ownership and concurrency contracts and test failure as
well as success paths. Preserve the PE/Unix compiler separation and deployment
floor configured in the build recipes.

Comments should explain why a constraint or unusual mechanism exists. Do not
narrate obvious operations, leave obsolete explanations, or claim performance
benefits without evidence. Put lengthy investigations in documentation.

## 3. Integrate component changes reproducibly

An edit in an ignored local component checkout is not an integrated fix. Record
the tested component commit in the appropriate pin file and keep archive tags,
hashes, addon versions and related metadata consistent.

For WineCX, Mesa and Relay12, inspect `tools/build/bump_pin.py` before manually
editing pins. It verifies the fields it supports; DXMT and other payload updates
still need their own coordinated pin/artifact verification. Any recipe or pin
change must invalidate every OCI layer affected by it. Add or update cache-key
regression tests when the dependency graph changes.

A cross-repository PR should link the component change, pin update and any
consumer migration in dependency order. Do not rely on an unmerged branch moving
under an immutable-looking artifact or a mutable tag as proof of provenance.

## 4. Validate the final result

Use [the QA matrix](SKILLS.md#select-the-required-qa) and
[QA evidence requirements](docs/qa.md). Run relevant regression tests after the
last code change, then the required build and artifact checks. A module-only
`--fast` build is useful feedback, but is not release validation.

Use the [local build guide](docs/oci-build-system.md) for restoring foundation
and tool layers. Its commands assume prepared sources and the pinned toolchain;
do not substitute a checkout's ambient libraries for those dependencies.

Record commands, outcomes, exact revisions, artifact digests and environment.
Distinguish a new failure from a pre-existing failure or unavailable check. Keep
large artifacts in CI storage or an ignored local directory; check ignore rules
before creating local output. Do not commit authentication data or game saves.

## 5. Make the diff and commit reviewable

One commit should express one coherent, working change. Separate unrelated
cleanup, formatting and dependency updates. Keep a regression test with the fix
when that makes the behavior easiest to review. If a refactor is necessary,
separate the behavior-preserving move from the behavior change where practical.

Review the complete diff, then stage explicit paths and review the staged patch:

```sh
git diff
git diff --check
git add tools/check_runtime_layout.py tests/test_runtime_layout.py
git diff --cached
git diff --cached --check
git config user.name
git config user.email
git commit --signoff -m "fix(packaging): reject missing consumer payloads"
git log -1 --format=full
git status --short
```

The paths and message above illustrate a layout-checker fix; use the actual
paths and final behavior of your task. Do not use `git add .` to collect unrelated
files. Do not include build outputs, local Wine trees, caches, machine paths,
screenshots or logs in a source commit.

Every agent-created commit must carry:

```text
Signed-off-by: Nilton Perim Neto <niltonperimneto@gmail.com>
```

`--signoff` uses the configured committer identity; verify it matches the owner
before relying on that flag. Check the resulting message. Preserve existing
authorship and valid trailers, including during authorized amendments or merges.
A co-author trailer is not a replacement, and a sign-off trailer is distinct
from a cryptographic commit signature. Do not rewrite shared history to retrofit
sign-offs without authorization.

## 6. Submit a reviewable result

Use [the PR template](.github/pull_request_template.md). Lead with the concrete
problem and resulting behavior, not the sequence of editing attempts. Include:

- A before/after example or reproducible trigger and acceptance condition.
- Why this repository/component owns the change and any linked dependencies.
- The mechanism and meaningful compatibility or failure-handling tradeoffs.
- Validation of the exact final commit/artifact, with results and CI links.
- Limitations, evidence still missing, and a practical rollback for runtime,
  pin, contract or publication changes.

Scale the description to the change. Documentation-only edits need accurate
links, examples and claims; a loader or ABI change needs deeper explanation and
runtime evidence. Avoid unrelated implementation history and large raw logs.

Push, open a PR or publish only within the user's authorization. When CI is part
of the task, confirm it tests the pushed commit and watch required jobs through
completion. A green workflow with skipped hardware checks does not establish
GPU compatibility. Branch protection and auto-merge settings are not proof that
all requested QA was performed.

For rollback, identify the last validated pin/artifact and any consumer schema
dependency. Prefer a reviewed revert or a new versioned artifact rather than
rewriting shared history or silently changing the contents of a tested release.
Preserve a failing regression case so the problem does not return.
