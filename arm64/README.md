# arm64 runtime

local recipe for `whisky-arm64-<ver>`: wine arm64 (arm64ec + aarch64, native
unix half), our FEX, DXMT arm64ec, wine-mono, on CrossOver's entitled
`wine.app` until we have our own `cross-architecture-support` entitlement.

sources, all pushed:

| piece | repo | branch |
|---|---|---|
| wine | dappermint/winecx | `arm64-<wine>` (e.g. `arm64-1117`) |
| DXMT | dappermint/dxmt | `arm64-1117` |
| FEX | dappermint/FEX | `main` (carried in the base runtime) |
| FEX, opt-in | FEX-Emu/FEX + `fex/patches` | `FEX-2609`, pinned in `fex/pins.env` |

order:

1. `build-arm64-unix.sh all` builds wine (SRC/B env to override)
2. `build-llvm15.sh` once, airconv needs llvm 15 exactly
3. `build-dxmt-arm64.sh` builds DXMT against the wine build tree
4. `package-arm64.sh <ver> <base-runtime>` installs wine, carries FEX, the
   loader and dylibs from the base runtime, adds wine-mono. With
   `FEX_BUNDLE=<dir>` FEX comes from `build-fex-arm64.sh` instead (below)
5. `install-dxmt-arm64.sh <runtime> [dxmt-build]` swaps in the fresh DXMT
6. `verify-runtime.sh <runtime-id> <label>` boots a clone of the arm64 bottle,
   compiles and runs a .NET exe, runs casualties unknown

wine-mono comes from the upstream `wine-mono-<ver>-arm64.tar.xz` release, the
version in `dlls/mscoree/mscoree_private.h`.

## Pinned FEX build

`build-fex-arm64.sh` builds all four FEX files from upstream
[FEX-2609](https://github.com/FEX-Emu/FEX/releases/tag/FEX-2609)
(`395b132f346b1a45def246d10c52245edba1ef02`) plus the patches in `fex/patches`,
then packages them opt-in. It supersedes `build-fex-unixlib.sh` and
`build-fex-translators.sh`, which build an unpinned dappermint/FEX checkout.

```sh
bash arm64/build-fex-arm64.sh /path/to/fex-work /path/to/fex-bundle
FEX_BUNDLE=/path/to/fex-bundle bash arm64/package-arm64.sh <new-version> <base-runtime>
```

Upstream's "Unsupported system type Darwin" check is about the target, not
the host. The PE translators use `toolchain_mingw.cmake`
(`CMAKE_SYSTEM_NAME Windows`), so they cross-build on macOS with llvm-mingw and
no CMake change. They are built with the same options as upstream's
`wine_build` action, using the llvm-mingw release `build-arm64-unix.sh` uses
(checksum pinned; downloaded into the work directory unless
`/Volumes/Wine/toolchains` or `LLVM_MINGW` provides it). The Unix helpers are
a separate CMake project and are built natively with Apple clang for arm64,
macOS 26.0.

| output | built from | loaded by |
|---|---|---|
| `aarch64-windows/xtajit64.dll` | `libarm64ecfex.dll` | ntdll's ARM64EC default (`HKLM\Software\Microsoft\Wow64\amd64`) |
| `aarch64-windows/xtajit.dll` | `libwow64fex.dll` | wow64's default x86 CPU DLL on arm64 |
| `aarch64-unix/libarm64ecfex.so` | `Source/Windows/UnixLib` | FEX, by name (`MemoryWineLoadUnixLibByName`) |
| `aarch64-unix/libwow64fex.so` | `Source/Windows/UnixLib` | FEX, by name |

These names come from dappermint/winecx `arm64-1117` (`dlls/ntdll/loader.c`,
`dlls/wow64/syscall.c`, `dlls/ntdll/unix/loader.c`). Because FEX loads its
helpers by name, renaming the PE files does not change the helper names.

Patches, each written so it could be offered upstream (`__APPLE__` / `APPLE`
only, with no Linux change):

- `0001` is dappermint's `4efc3abc` ported onto FEX-2609, with authorship kept.
  Hardware TSO and kernel unaligned-atomic control return
  `STATUS_NOT_SUPPORTED`, VMA naming is a no-op, madvise maps Linux advice
  values and drops the rest (including the only values FEX sends,
  `MADV_[NO]HUGEPAGE`), and the SHM stats are stubbed. `MapFile`, which is
  newer than the fork, is kept as is: macOS accepts
  `MAP_SHARED | MAP_NORESERVE`.
- `0002` drops `-lrt` on Apple; without it the link fails with
  `ld: library 'rt' not found`.

The build fails if a patch does not apply, or if any of these checks fails:
`xtajit64.dll` is `COFF-ARM64EC`/`ARM64X` and `xtajit.dll` is `COFF-ARM64`
(`llvm-readobj`), both carry the `wine_builtin.bin` marker,
the helpers are arm64-only with minos ≥ 26.0, export
`__wine_unix_call_funcs`, depend only on `/usr/lib` and `/System/Library`, and
verify after ad-hoc signing. `SOURCE.txt` records the pins and each patch's
sha256, `BUILD-TOOLS.txt` the compilers, and `licenses/fex.txt` the license.
`install-fex.sh` checks the bundle again at packaging time before replacing
the carried files: the PE machine (an ARM64EC image has the AMD64 machine plus
CHPE metadata in its load config, which the check reads), the builtin marker,
and the helpers' architecture and signature. It
puts `SOURCE.txt` under `Wine/lib/fex/`, and `verify-runtime.sh` prints it.

`tests/fex_unixlib_smoke.c` loads each helper natively, without Wine, and
calls the handlers whose macOS behaviour the port defines, including a real
`MapFile` round trip. `tests/test_fex_arm64.py` covers `install-fex.sh` and
both `package-arm64.sh` paths with stand-in files.

Local validation, 2026-10-03 (macOS 27.2, Apple A18 Pro): a clean work
directory built all four files, and every gate passed. Independent checks
agree: `xtajit64.dll` is `COFF-ARM64EC` and `xtajit.dll` is `COFF-ARM64`, both
with the builtin marker. Both helpers are arm64 with minos 26.0, depend only on
`libc++` and `libSystem`, and pass `codesign --verify --strict`. The smoke test
passed 10 checks per helper. `install-fex.sh` accepted the real bundle
(`FEX_TEST_BUNDLE=<bundle>` runs that as a unit test). All 29 unit tests passed.
llvm-mingw 20260616 linked the ARM64EC DLL without the `ld.lld` failures
reported for other macOS-hosted builds. Evidence is in `fex-arm64-build.log` and
`fex-arm64-bundle/` under `~/Library/Caches/winecx-kosmickrisp-arm64-lane/`.

Known gaps: no x86 code has run through these files. Wine execution needs an
arm64 Wine build and the entitled base runtime, and neither is available here.
FEX on macOS has no hardware TSO switch, so x86 memory ordering
stays on FEX's software path. 16 KiB pages (FEX issue #1221) do not affect the
build, but runtime testing must cover them. ARM64EC assembly emits five
upstream X23/W23 warnings.
