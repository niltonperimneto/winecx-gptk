# kosmickrisp lane (experimental)

an optional second vulkan driver for the same rosetta wine host:
[kosmickrisp](https://docs.mesa3d.org/drivers/kosmickrisp.html), mesa's
conformant vulkan 1.4 driver on metal, in place of moltenvk.

why: moltenvk does not expose the vulkan 1.3 features dxvk 2.x and 3.x require,
which is why whisky keeps dxvk frozen at the 1.10.x macos fork. kosmickrisp does
expose them, so the goal is kosmickrisp + upstream dxvk, and native vulkan games
without moltenvk's translation gaps. nothing changes for a runtime built without
this lane, and `wine`/`wine64` keep moltenvk even in a runtime built with it.

## build

dispatch `build.yml` with the `kosmickrisp` box ticked. the artifact is named
`whiskywine-gptk-libraries-kosmickrisp-experimental`, and publish refuses it, on
`main` too; a push never builds this lane.

`runtime/kosmickrisp/pins.env` pins the shadexternals cross-build recipe, the
mesa commit its submodule must resolve to, and the khronos loader and headers.
`build.sh` builds them for x86_64, because an arm64 icd cannot load into this
wine host. the build fails if a library is not x86_64-only, links anything
outside `/usr/lib` and `/System`, or fails codesign verification. mesa's zlib
fallback stays dynamic despite `--prefer-static`, so it is bundled and relinked
through `@loader_path`. homebrew and xcode are not pinned; `BUILD-TOOLS.txt` in
the bundle records what built it.

## layout and use

`Wine/lib/kosmickrisp/` holds `libvulkan.1.dylib` (khronos loader),
`libvulkan_kosmickrisp.dylib`, `kosmickrisp_icd.json` (relative library path),
zlib when mesa needs it, licenses, and `SOURCE.txt` with the pins.

```sh
WINEPREFIX=/path/to/prefix Libraries/Wine/bin/wine-kosmickrisp program.exe
```

the launcher needs no wine change. crossover's win32u (cw hack 25909) already
loads `CX_LIBVULKAN` as the host vulkan library while
`CX_ACTIVE_GRAPHICS_BACKEND` is `wined3d`, so the launcher sets both, points
`VK_DRIVER_FILES` at the bundled icd, and clears inherited
`VK_ICD_FILENAMES`/`VK_LOADER_DRIVERS_*`. `wined3d` here selects no direct3d
implementation for dxvk or a native vulkan program; it only unlocks the
override. whisky can set the same variables per program.

## Rosetta fallback branch

`kk/08-rosetta` keeps the x86_64 runtime available while native arm64 Wine/FEX
porting continues separately. The launcher explicitly uses
`/usr/bin/arch -x86_64` and clears `WINE_VULKAN_LIBRARY` along with inherited
ICD selection. Rosetta translates the Wine Unix host and the x86_64 driver on
Apple Silicon. The Metal API remains the graphics backend; FEX is not required
for this lane. Windows 32-bit programs use this runtime's existing WoW64 support.

To add the bundle to a staged copy of a compatible CrossOver Wine runtime:

```sh
bash runtime/kosmickrisp/build.sh /path/to/kk-build /path/to/kk-bundle
bash runtime/kosmickrisp/install-rosetta.sh /path/to/staged/Wine /path/to/kk-bundle
WINEPREFIX=/path/to/test-prefix /path/to/staged/Wine/bin/wine-kosmickrisp program.exe
```

The installer verifies x86_64 Wine binaries, the `CX_LIBVULKAN` override,
bundle architecture, signatures, dependency closure and relative ICD path
before installing. It refuses an existing KosmicKrisp installation. Rosetta
must already be available on Apple Silicon. The dispatch-only CI lane uses this
installer and continues testing both PE architectures with native Vulkan and
upstream DXVK. DXVK test DLLs remain beside the probes, outside runtime defaults.

### Local validation — 2026-10-03

A fresh pinned x86_64 driver build was installed into an isolated clone of
`winecx-gptk-4.7.71` (Wine 11.18), relocated into a path containing spaces.
Rosetta availability was confirmed with `sysctl.proc_translated=1`. Installed
runtimes were not modified. The fresh test prefix booted successfully.

Both x86_64 and i686 probes selected KosmicKrisp driver ID 28 on Apple A18 Pro,
reported `geometryShader=1` and `fillModeNonSolid=1`, and passed exact compute
readback plus windowed, resized, borderless and restored presentation. Upstream
DXVK 3.1.1 created D3D9 devices and D3D11 devices at feature level 11_1 for both
architectures. Driver signatures, the three launcher tests, installer rejection
of an arm64 bundle and existing installation, shell syntax and workflow lint
passed. The workflow itself was not dispatched. Transform feedback remains
absent; these device tests do not establish game compatibility or performance.

The runnable staged Wine directory is
`~/Library/Caches/winecx-kosmickrisp-rosetta/relocated runtime/Wine`.
Logs, source pins and `validation.json` are in the parent cache directory.
