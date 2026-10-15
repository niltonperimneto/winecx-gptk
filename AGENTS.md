# Agent instructions for winecx-gptk

These instructions apply throughout this repository. Read [SKILLS.md](SKILLS.md)
for the workflow relevant to the task and honor more specific instructions in
subdirectories. Explicit user instructions take precedence.

## Priority: QA and no regressions

Quality assurance is the highest priority. Preserve working behavior before
adding features or improving performance. Never knowingly ship a regression,
weaken a quality gate, or describe an unverified change as safe or complete.

- Understand the affected behavior and its existing tests before editing.
  Reproduce a reported failure when possible and identify existing baseline
  failures separately from failures introduced by the change.
- Make the smallest complete fix. Preserve compatibility for existing runtimes,
  bottles, graphics backends, supported architectures and deployment targets.
- Add meaningful regression coverage for behavior changes. Tests must establish
  observable correctness, not repeat the implementation or merely accept output.
- Run the relevant checks after the final edit. Runtime, packaging, dependency
  and CI changes require the affected build and artifact validation as well as
  unit tests. A green unit suite alone does not prove runtime compatibility.
- Never remove assertions, skip failing tests, broaden import allowlists,
  suppress new diagnostics, mask failures or bypass checks to obtain a green run.
  Fix the cause; any intentional change to a gate needs a documented technical
  justification and equivalent coverage.
- Treat a new warning, crash, incorrect image, failed readback, missing payload,
  unsupported architecture or compatibility loss as a regression to investigate.
- When required validation cannot run, report exactly what is missing. Do not
  mark the result release-ready. No claim of "never breaking" replaces evidence.
- If asked to watch CI, follow the exact pushed commit until every required job
  finishes. Diagnose failures, fix them and repeat the affected checks. A queued
  or running build is not a successful build.

## Repository boundaries and invariants

This repository pins, builds, assembles and validates the runtime consumed by
Whisky. Consult the current workflows and pin files rather than copying version
numbers or assumptions from historical reports.

- Build inputs belong in [tools/build/pins.env](tools/build/pins.env) and
  [runtime/kosmickrisp/pins.env](runtime/kosmickrisp/pins.env). Keep source commits,
  release artifacts, digests and dependent metadata consistent and immutable.
- Preserve the consumer contract in
  [contracts/runtime-layout.json](contracts/runtime-layout.json). Coordinate
  intentional contract changes with the consuming Whisky repository.
- Keep compiled runtimes relocatable and independent of the builder's Nix store,
  checkout path and home directory. Preserve architecture slices, dependency
  closure, signatures, required licenses and the pinned macOS deployment floor.
- Keep OCI cache keys consistent with every input affecting a layer. Validate
  the assembled artifact even when all components came from caches.
- Verify the actual graphics backend and driver in logs. Device creation,
  presentation, correct rendered output, level loading and gameplay are distinct
  claims. Performance claims require a controlled, repeatable comparison.
- Use disposable prefixes, game copies and caches for experiments. Preserve
  user data and authentication; stop only processes proven to belong to the
  selected test prefix. Keep environment changes local to launched processes.
- Keep native ARM64/FEX research separate from the working Rosetta runtime;
  never install experimental architecture payloads into a user's live bottle.

## Repository hygiene

- Inspect `git status` and the current branch before making changes. Preserve
  unrelated work, untracked user files and existing authorship.
- Keep diffs focused. Do not mix feature work with unrelated formatting,
  dependency updates, renames, generated files or cleanup.
- Keep build trees, downloaded archives, caches, logs, screenshots, credentials,
  machine-specific files and local game data out of commits. Use appropriate
  ignored locations; verify ignore rules before relying on them.
- Keep maintained documentation and examples consistent with the final behavior.
  Record exact tested revisions and distinguish automated evidence from manual
  user confirmation. Correct conclusions when new evidence supersedes them.
- Review the final staged diff and run `git diff --check` before committing.
  Stage explicit task-related paths rather than sweeping in unrelated files.
- Do not force-push, rewrite shared history, publish a release or change unrelated
  repositories without authorization for that action.

## Relevant comments only

Comments should explain a non-obvious reason, invariant, compatibility constraint,
ownership rule or failure mode. Keep them accurate and close to the code they
explain. Remove stale comments when changing the behavior they describe.

Avoid comments that restate code, narrate the editing process, advertise an
optimization without evidence, or preserve abandoned approaches. Use a TODO only
for a concrete unresolved task with enough context to act on it. Put extensive
investigation history and validation results in documentation, not code comments.

## Commits must carry the owner's sign-off

Every commit an agent creates must include this exact trailer:

```text
Signed-off-by: Nilton Perim Neto <niltonperimneto@gmail.com>
```

Use `git commit --signoff` when the configured committer identity matches that
trailer. Verify the final message with `git log -1 --format=%B`. This requirement
also applies to agent-created fixup, amended and merge commits. Preserve other
valid trailers and authorship; do not rewrite existing commits merely to add a
sign-off unless the user requested that history change. Do not substitute a
co-author trailer for the required sign-off.

Keep commits cohesive and messages specific to the final change. Report what
changed, what was validated, the CI result when applicable, and any remaining
limitations. Never report a test or build as passed without observing its result.
