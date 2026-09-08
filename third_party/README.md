# Pinned source dependencies

Initialize the source dependencies with:

```sh
git submodule update --init --recursive
```

The permitted revisions are enforced by pull-request CI and recorded in
`THIRD_PARTY_NOTICES.md`. Updating a revision requires auditing its license,
transitive dependencies, ABI requirements, and MinGW build status in the same
change.
