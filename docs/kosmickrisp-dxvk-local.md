# Local KosmicKrisp + upstream DXVK profile

This page describes the earlier 4.7.51 local installation. The imported
4.7.54 runtime also lacks the fill-mode patch; see
[the Mesa fill-mode port](kosmickrisp-fillmode-port.md) for the rebuilt driver
and its passing DXVK 3.1.1 device probes. Neither runtime import adds a
selectable backend to the current Whisky client.

The Whisky Preview WineCX 4.7.51 runtime now has the locally built KosmicKrisp
loader and ICD in `Wine/lib/kosmickrisp/` and upstream DXVK 3.1.1 in
`DXVK-Upstream/`. The DXVK archive is the official
[doitsujin release](https://github.com/doitsujin/dxvk/releases/tag/v3.1.1),
verified with SHA-256
`40565b4a724aadc4433fa4e010b4b23916d9b1f1baeee64e17186db94f54e608`.
The existing `DXVK/` directory remains the normal Whisky payload.

`Wine/bin/wine-kosmickrisp-dxvk` selects KosmicKrisp for a process and sets
native DLL overrides for D3D8/9/10/11 and DXGI. DXVK's Windows DLLs must also
be present in a Wine prefix; `WINEDLLPATH` alone did not make Wine load them.
This profile therefore requires an initialized **selected prefix**:

```sh
runtime="$HOME/Library/Application Support/com.dappermint.WhiskyPreview/Runtimes/winecx-gptk-4.7.51"
prefix="$HOME/Library/Caches/winecx-kosmickrisp-dxvk/integration-prefix"
WINEPREFIX="$prefix" "$runtime/Wine/bin/wine-kosmickrisp-dxvk" --install-prefix
WINEPREFIX="$prefix" "$runtime/Wine/bin/wine-kosmickrisp-dxvk" /absolute/path/to/game.exe
WINEPREFIX="$prefix" "$runtime/Wine/bin/wine-kosmickrisp-dxvk" --restore-prefix
```

The installer saves the ten original DLL entries in the prefix, refuses an
unrecognized or changed installation, and restores those originals exactly.
Do not run it against an active bottle. The local installation and restoration
were verified in a disposable prefix; the user's Steam bottle was not changed.
That disposable prefix has been left with the upstream DXVK DLLs installed for
further testing.

This is an **experimental integration, not a working Direct3D backend yet**.
In both 64-bit and 32-bit D3D9/D3D11 probes, the DXVK 3.1.1 log confirms its
DLLs loaded, then reports `Device does not support required feature
'fillModeNonSolid'` and rejects the KosmicKrisp adapter. The driver also lacks
`VK_EXT_transform_feedback`. The current Whisky Preview app's normal DXVK
switch uses `DXVK/` and reconciles `dxgi.dll` for its existing DXVK-macOS
payload, so it does not select this upstream profile. Upstream DXVK's
[installation instructions](https://github.com/doitsujin/dxvk) likewise
require copying the DLLs into a Wine prefix and setting native overrides.

Evidence is under `~/Library/Caches/winecx-kosmickrisp-dxvk/probes/`.
