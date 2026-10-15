## Problem and resulting behavior

Describe the concrete trigger and before/after behavior. State the acceptance
condition and link the issue or reproduction when relevant.

## Ownership and implementation

Explain why this change belongs in the hub or link the component fix being
integrated. Describe the mechanism, affected backends/architectures, contract or
cache-key implications, and any meaningful tradeoff. Keep this proportional to
the change.

## Validation

| Check | Final result and evidence |
| --- | --- |
| Applicable static/unit checks | |
| Build and artifact/contract checks | |
| Platform/GPU/game checks, when relevant | |

Include the tested commit and artifact digest for runtime changes, relevant
environment, CI links, and baseline comparison. Mark checks not applicable,
blocked or not run explicitly. Attribute manual gameplay confirmation accurately.
For documentation-only changes, local link/claim review and whitespace results
are sufficient; remove irrelevant rows.

## Risks, remaining gaps and rollback

Describe compatibility risks, required evidence still missing, coordinated
consumer changes and how to restore a known working version. Say when this is
not yet release-ready. Omit implementation history that does not help review.

## Final review

- [ ] The diff contains only relevant source, tests and documentation.
- [ ] Applicable QA passed on the final revision, or gaps are explicit above.
- [ ] No quality gate was weakened to hide a failure.
- [ ] Pins, artifacts, checksums, cache inputs and consumer contracts agree where affected.
- [ ] No generated payloads, local paths, user data or secrets were committed.
- [ ] Every agent-created commit includes the owner's sign-off from AGENTS.md.
