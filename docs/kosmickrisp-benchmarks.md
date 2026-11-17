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

## Vertex-input fetch comparison

`--stage vi` measures the cost of KosmicKrisp's runtime-decoded vertex fetch
(`VK_EXT_vertex_input_dynamic_state`) against the static path that bakes each
pipeline's vertex layout into its shader. It needs a driver that understands
`MESA_KK_DEBUG=dynamic_vi` and `no_msl_helpers`.

| condition | `dxvk.enableGraphicsPipelineLibrary` | `MESA_KK_DEBUG` |
| --- | --- | --- |
| `vi-static` | False | (empty) |
| `vi-static-nohelpers` | False | `no_msl_helpers` |
| `vi-dynamic-helpers` | False | `dynamic_vi` |
| `vi-dynamic-inline` | False | `dynamic_vi,no_msl_helpers` |
| `vi-shipping-default` | Auto | (empty) |

GPL is off in the four controlled conditions so every pipeline is compiled
with its vertex-input state, so only the debug flags change the fetch path.
With GPL on, fast-linked pre-rasterization libraries are compiled without
vertex-input state and already use the dynamic fetch until an optimized
pipeline replaces them; `vi-shipping-default` shows that mix.

`no_msl_helpers` also inlines texture helpers, so it is not a pure fetch
change. `report.json` therefore lists `effects` only for matched pairs:
`vi-dynamic-helpers` against `vi-static`, and `vi-dynamic-inline` against
`vi-static-nohelpers`. `MESA_KK_DEBUG` is always passed explicitly, and a run
whose recorded environment differs from its condition is invalid.

Use the warm and warm2 rows for steady-state vertex-shader cost and the cold
row for compile stutter. Before a campaign, make one diagnostic
`stutter.py run --runs cold --env MESA_KK_DEBUG=dynamic_vi,msl` and check that
the emitted vertex MSL reads `attrib_format`, which shows the dynamic path is active.
