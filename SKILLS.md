# Repository workflows

Read [AGENTS.md](AGENTS.md) first. These task-specific workflows describe how to
work on this repository; the live scripts and workflows are authoritative when
commands or build structure change.

## Select the required QA

Use the smallest verification scope that establishes the change is correct.
Expand it when a failure, shared dependency or unresolved risk warrants it.

| Change | Required evidence |
| --- | --- |
| Documentation or instructions only | Accurate claims, valid local links, focused diff and whitespace checks. A full runtime rebuild is unnecessary unless executable behavior also changes. |
| Python or shell behavior | Relevant regression tests and the applicable shared QA checks. Run the full Python suite for changes to shared build/runtime helpers. |
| Workflow, OCI cache, packaging, source patch or dependency pin | Unit/contract tests, applicable lint, affected builds and validation of the assembled artifact. |
| Graphics, loader or architecture behavior | Build and runtime validation on suitable hardware, relevant architectures and backends, plus correctness probes. |
| Performance behavior | Correctness first, then comparable repeated measurements with controlled scene, settings and cache state. |

The baseline is defined by
[qa-common.yml](.github/workflows/qa-common.yml) and
[build.yml](.github/workflows/build.yml). Typical local commands are:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
actionlint
git ls-files -z '*.sh' | xargs -0 shellcheck -S warning
git ls-files -z '*.py' | xargs -0 ruff check --select E9,F63,F7,F82
git diff --check
git diff --cached --check
```

Use the tool versions and exclusions in the current QA workflow. A missing tool
or unsupported host is an unperformed check, not a pass. Use CI or appropriate
hardware to complete required platform checks. Do not create tests that merely
assert the wording of these instruction files.

## Fix a runtime regression

1. Record the failing revision, host, architecture, backend and reproduction.
   Compare against a known working build when available.
2. Find the responsible component and keep the fix at the correct repository
   boundary. Do not hide a Wine defect with an unrelated graphics workaround.
3. Add focused coverage and build the affected code. For runtime changes,
   validate the assembled payload through [tools/run_probes.sh](tools/run_probes.sh)
   and its applicable platform probes.
4. Check relocation, dependency closure, window creation, media, architecture
   integrity and consumer layout wherever the change can affect them.
5. Preserve evidence and report remaining gaps. Follow any requested CI run to
   completion before declaring success.

Start with [the build guide](docs/oci-build-system.md),
[cross-repository CI](docs/ci-integration.md) and the scripts in [tools/](tools/).

## Update a dependency or rebuild an OCI layer

1. Read the authoritative pins and inspect the candidate source changes. For a
   requested "latest" revision, resolve the specified repository and branch to
   an exact commit at the time of the update.
2. Prefer [tools/build/bump_pin.py](tools/build/bump_pin.py) where it supports
   the component. Verify artifact provenance, commit/tag alignment, checksums,
   required submodules, licenses and consumer compatibility.
3. Check [tools/build/cache_key.py](tools/build/cache_key.py) and relevant
   invalidation tests. A pin change must invalidate every affected layer and
   preserve reuse of unrelated layers.
4. Build the changed components, assemble the runtime and run the required
   validation against that exact artifact. Cached components do not exempt the
   combined runtime from QA.
5. Keep publication separate from experimental validation and report the tested
   source and artifact identities.

## Validate graphics or gameplay

1. Use an isolated bottle and keep the installed runtime, configuration, saves,
   DLL overrides and caches recoverable. Verify ownership before sending input
   or stopping processes. Never enter user credentials.
2. Verify driver/backend identity and both 32-bit and 64-bit behavior where
   supported. Use real GPU readbacks and presentation probes; successful API
   calls alone do not prove correct rendered output.
3. For game testing, separately record startup, menu interaction, level loading,
   rendered gameplay and exit behavior. Use visible, focused windows for visual
   checks. Classify lock, sleep, authentication and capture failures as limits of
   the test rather than proof that the game is broken.
4. Preserve user-confirmed manual gameplay as valid evidence and attribute it
   accurately. Failure of automation to verify gameplay does not contradict a
   successful manual test. A normal process exit is not itself a crash.
5. For benchmarks, control scene, resolution, settings, backend and cache state;
   repeat runs and distinguish startup/compilation from steady gameplay. Do not
   publish a startup FPS average as gameplay performance or claim causation from
   overlapping events alone.

Relevant guides:
[KosmicKrisp deployment](docs/kosmickrisp.md),
[benchmarks](docs/kosmickrisp-benchmarks.md),
[bounded investigation](docs/kosmickrisp-investigation.md) and
[ARM64 research](arm64/README.md).

## Prepare the final commit

1. Review `git status`, the full task diff and the staged diff. Exclude unrelated
   user files, temporary artifacts and secrets.
2. Complete the checks required for the change. Resolve new failures; identify
   pre-existing failures and unavailable checks honestly. Do not label a change
   release-ready while required validation remains incomplete.
3. Stage only the intended paths and commit with the exact owner sign-off from
   [AGENTS.md](AGENTS.md). Verify the trailer in the resulting commit message.
4. If pushing and monitoring CI are authorized, verify that the run tests the
   pushed commit and follow all required jobs to their final result. Do not
   bypass branch protection or replace missing GPU evidence with a hosted-only
   build success.
