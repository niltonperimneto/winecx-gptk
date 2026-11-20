# Controlled KosmicKrisp comparisons

`runtime/kosmickrisp/benchmark.py` builds separate campaigns for GPL behavior,
compiler threads, maximum frame latency and latency sleep. It extends the
existing stutter harness. At least three repetitions rotate condition order;
each condition/repetition has isolated cold, warm and warm2 caches. Inputs and
configuration files are checksummed before execution.

Prepare a scene JSON with a repeatable recording or saved/input fixture:

```json
{
  "id": "portal2-opening-timedemo",
  "game": "portal2-d3d9",
  "arguments": ["-novid", "-sw", "-w", "1280", "-h", "720", "+mat_vsync", "0", "+timedemo", "winecx_benchmark", "+quit"],
  "skip_seconds": 0,
  "reproduction": "Replay the same recorded opening scene without user input. Confirm timedemo completion and visible rendering.",
  "fixtures": ["/absolute/path/to/Portal 2/portal2/winecx_benchmark.dem"]
}
```

Fixtures must exist before planning. Keep saved configuration and the relevant
input sequence in the fixture list too. The fixture path must correspond to the
recording or save that the copied game actually loads. A fixture hash alone
cannot prove execution of a scene.

```sh
python3 runtime/kosmickrisp/benchmark.py plan \
  --runtime /path/to/Libraries --bundle /path/to/driver \
  --bottle /path/to/test-bottle --game portal2-d3d9 \
  --scene /path/to/scene.json --stage gpl --out /tmp/kk-gpl
python3 runtime/kosmickrisp/benchmark.py run /tmp/kk-gpl/plan.json
python3 runtime/kosmickrisp/benchmark.py analyze /tmp/kk-gpl/plan.json
```

Steam games require Steam running and signed in to the selected test bottle.
Use a disposable bottle for a campaign. The campaign uses cloned game directories
and does not use the stutter harness's optional live-install/Steam-restart mode.
After GPL screening, use `--stage threads --gpl Auto` or `--gpl True` to compare
0 (DXVK's default), 2 and 4 workers while holding GPL behavior fixed. Use
`--stage latency` and `--stage sleep` as independent experiments.

Measurement runs retain present timestamps and DXVK identity/configuration logs
but disable detailed compile/cache/variant telemetry. Make separate diagnostic
runs with `stutter.py run --diagnostics --cache-log` for correlation. Compilation
and hitch overlap is evidence of correlation, not proof of causation.

Reports show medians and ranges per cache state and flag missing results,
backend mismatches, changed input identity and DXVK errors. GPL support and
GPL activation are separate fields. A completed campaign still requires review
of scene execution, window visibility and rendering before selecting defaults.
Startup and loading frames must not be presented as verified gameplay.

The first targets are lower gameplay p99 or fewer hitches beyond control
variability, without an unacceptable mean-FPS, GPU-time or memory regression.
The provisional plan thresholds are 10% lower p99 or 20% fewer hitches with
mean FPS no more than 5% worse; establish actual repeatability before applying
those thresholds.

## Rise of the Tomb Raider startup

A disposable Steam bottle with WineCX 11.19 at `6eb3386d7f97` (a rebuilt
Unix `ntdll` over the existing runtime), DXVK and KosmicKrisp 26.2.99
rendered the Square Enix sign-in screen and issued thousands of Vulkan
presents. Steam was running in the same bottle and Game Mode was off.

The run used `dxvk.enableGraphicsPipelineLibrary = False` and these Wine
DLL overrides under `HKCU\Software\Wine\AppDefaults\ROTTR.exe\DllOverrides`:

- Native, then builtin (`n,b`): `dxgi`, `d3d11`, `d3d10core`.
- Disabled (empty string): `d3d12`, `d3d12core`, `nvapi64`,
  `GFSDK_SSAO_D3D11.win64` (HBAO+) and `GFSDK_VXGI_x64` (VXGI).
- Disabled during earlier input tests: `xinput1_1`, `xinput1_2`,
  `xinput1_3`, `xinput1_4` and `xinput9_1_0`.

The first visible run disabled HBAO+ and VXGI together. Their individual
effects and the smallest required set of overrides remain unverified.
This run verified startup through the sign-in screen. Gameplay and
benchmark completion still need validation.
