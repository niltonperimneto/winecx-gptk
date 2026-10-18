# Cross-repository integration status — 2026-10-17

The merge campaign is not complete. The [initial branch ledger](merge-audit-2026-10-17.json)
records all local/origin branches and their distinct patch-unique commits. Patch
uniqueness alone does not establish missing behavior: squash merges and later
implementations require content reconciliation. Original branches and dirty
worktrees remain preserved; snapshots and raw diffs are local build artifacts.

## Integrated work

| Repository | Result |
| --- | --- |
| WineCX | [PR 6](https://github.com/niltonperimneto/winecx/pull/6), merged as `c4fb531c`: bundled loader, empty override rejection, bounded diagnostics; current Steam startup guards preserved. PR and merged-main CI passed. |
| Relay12 | Lazy initialization was already on main at `95c1703`. [PR 28](https://github.com/niltonperimneto/relay12/pull/28) merged the isolated upload-limit research tool as `fd35bce`. Its PR passed both semaphore and ring builds; merged-main CI passed; the roadmap-only follow-up still awaits its manually dispatched required checks. |
| Whisky | [PR 12](https://github.com/niltonperimneto/Whisky/pull/12) integrates layout-v2 switching, retains PEAK routing, fixes an existing installed-Steam interface recognizer failure, and resolves formatting/lint failures. All required PR CI passed, including UI tests; main merge/pin is being finalized. |
| Mesa | [PR 5](https://github.com/niltonperimneto/mesa/pull/5) ports the transform-feedback series as isolated research. Default GPL/shader-object capability coverage is preserved; capture is not enabled in production. Required CI remains pending. |
| Hub | Integration branch carries layout v2, protected catalog credentials, the GPTK 4 stub/idle-video changes already on main, merged Wine pin, Relay12 lazy-init artifact pin, the missing ARM64 i386 recipe change, and the expanded Metal-cache harness. |

## Historical-change reconciliation

- Wine's two loader branches are versions of the same series; the three-commit
  version is carried by PR 6. Earlier Steam/headless and Wine-version branches
  must be assessed against current main rather than reintroduced wholesale.
- The hub's `kk/01` through `kk/09`, package, investigation, and backup branches
  predate the OCI build split and current component-source pins. Old embedded
  Wine/Mesa patches and Wine/FAudio/DXMT pins must not replace newer inputs.
  The i386 ARM64 change and 19 missing cache scenarios were genuine deltas and
  are included. Native/FEX tooling stays separate from shipped Rosetta payloads.
- Relay12's old telemetry, first-frame, portability, smoke-oracle, and wrapped
  resource series have newer implementations on main. The no-upload-limit
  experiment is represented by an explicit source-copy tool; its gate-skipping
  change is deliberately replaced by a test proving production rejection.
  Roadmap consolidation is carried as a link-preserving index in a follow-up PR.
  Historical log dumps and external log-upload workflow experiments are not
  runtime payloads and must not be restored into production CI.
- Mesa's old geometry/fill-mode/page-size and MSL-helper branches overlap current
  implementations. Worktree-only cache/shader variants and the 35-patch snapshot
  were compared through preserved private snapshot commits and three-way diffs.
  One missing residency-set NSError initialization was recovered in PR 5.
  Older pthread/cache variants are superseded by current C11 workers, bounded
  recapture and rwlock indexing; generator prewarm hooks are represented by
  direct command wrappers, and the old Poly side-effect alias by the current
  lowering API. All original worktrees remain intact.

The machine ledger records an explicit disposition and evidence for every
branch commit and all six dirty Mesa worktrees. Included integration history
is distinguished from merged main; a superseded implementation is not recorded
as a new merge.

## Validation and remaining gates

- Hub integration: 366 Python tests pass, four skips; rerun after final pins.
- Restored cache harness: 31 scenarios pass against the native Mesa candidate.
- Relay12 research: all 200 Python tests pass. Fully prepared production source
  passes the port gate; the copied zero-limit variant fails that gate as intended.
- Whisky: 1,385 XCTest cases pass (three skips), and all 603 Swift Testing cases
  pass, including the installed-client inspection. Current-main's same live
  test failed before the recognizer fix. Steam patch tests use disposable files;
  the live installation was only read.
- Mesa: native build and eight suites pass, including actual-driver production
  and research capability contracts. Research CTS capture, triangle capture,
  and resume pass; two GPL cases report unsupported in this mode. Production
  compute, geometry, adjacency, and tessellation GPU readbacks also pass. Earlier
  ungated GPL capture stalled and is not a successful result.

Before final merge/promotion, update pins to the final merged Mesa, Relay12
artifact, and Whisky revisions; validate the exact assembled archive and complete
consumer suite. Physical macOS 26 and newer Metal 4 game/performance campaigns
remain required. No runner/campaign variables were configured during inspection.
Keep `WHISKY_LAYOUT_V2_AVAILABLE` disabled until a compatible client has shipped
and all existing promotion gates pass. No release-readiness or PEAK memory-savings
claim follows from these component results.
