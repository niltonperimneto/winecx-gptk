# KosmicKrisp CI failure investigation — 2026-09-29

[Run 36527125517](https://github.com/niltonperimneto/winecx-gptk/actions/runs/36527125517)
built and packaged the experimental runtime on macOS 26. The build job's host
probe printed `vkEnumeratePhysicalDevices(...): -3`, and its 64-bit and 32-bit
Wine probes printed `vkCreateInstance(...): -3`. Those exit codes were masked by
`| tee`, so the build job showed success. The separate validation job correctly
reported host and Wine failures. Its artifact upload then followed Wine's
`prefix/dosdevices/z:` symlink and failed with `EACCES`, hiding the probe logs.
These results do not establish a driver defect: the runner's Metal device
availability was not recorded in that run. GitHub has previously documented
[Metal devices returning nil on hosted runners](https://github.com/actions/runner-images/issues/1779).

The workflow now checks `MTLCreateSystemDefaultDevice` explicitly. If the runner
has no device, the artifact is still built and audited, while GPU execution and
migration readiness are visibly skipped. A runner with a Metal device executes
the probes with `pipefail`; any failed probe fails its build job. The validator
keeps its Wine prefix outside the diagnostics tree and uploads only JSON,
summary, and log files. Its result now records missing expected markers and
exit codes.

The locally built Mesa `fe554882e4f06cdd2579a77b37b04de605111a28`
bundle was installed into the existing Whisky Preview WineCX 4.7.51 runtime in
`Wine/lib/kosmickrisp/`. `Wine/bin/wine-kosmickrisp-legacy` selects it per
process through that runtime's `CX_LIBVULKAN` support. The normal Wine entry
points retain their existing backend. With an isolated prefix, the installed
launcher passed Vulkan 1.4, compute/geometry readback, and four presentation
modes in both x86_64 and i686 Wine. Logs are under
`~/Library/Caches/winecx-kosmickrisp-upstream/integrated-*.log`.
