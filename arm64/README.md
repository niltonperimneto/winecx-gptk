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

## Experimental KosmicKrisp package

The native Wine Unix half requires an arm64 loader and driver. Build the bundle
with `KK_ARCH=arm64`, then opt into packaging it:

```sh
KK_ARCH=arm64 bash runtime/kosmickrisp/build.sh /path/to/kk-build /path/to/kk-bundle
bash arm64/build-arm64-unix.sh all
KOSMICKRISP_BUNDLE=/path/to/kk-bundle bash arm64/package-arm64.sh <new-version> <base-runtime>
```

`install-kosmickrisp.sh` checks the native win32u architecture and its
`CX_LIBVULKAN` override, checks the bundle architecture, signatures and
its dylib dependency closure, and installs the arm64 launcher as
`Wine/bin/wine-kosmickrisp`. The launcher invokes `wine` through `arch -arm64`
and selects the bundled ICD using the CrossOver loader override. Windows
executable translation remains the runtime's FEX responsibility.

`.github/workflows/kosmickrisp-arm64.yml` provides dispatch-only packaging on a
self-hosted runner labeled `winecx-arm64`. It uses the provisioned upstream
`/Volumes/Wine` sources, build, llvm-mingw, Nix dependencies, wine-mono tarball,
and base runtime required by the existing recipe. Allocate a new version for
every dispatch. It uploads an experimental artifact and does not publish it.
The build directory must already correspond to the intended arm64 Wine source
revision: the underlying recipe reuses its existing configure state.

This lane has launcher and packaging-guard tests using stand-ins, plus a
native driver probe with exact compute readback. Native Wine,
FEX-to-Vulkan calls, surface creation, game rendering and performance have not
been validated for this package. A driver-only host result cannot establish
those outcomes. The arm64 workflow has not been executed. The branch is
prepared on top of the upstream KosmicKrisp PR-series tree; these changes have
not been submitted as an upstream PR or merged by dappermint.


### Local validation — 2026-10-03

A fresh `KK_ARCH=arm64` build on macOS 27.2 / Apple A18 Pro completed from the
pins above. The driver, loader and bundled zlib are arm64 and their signatures
verify. A native arm64 probe ran from a path containing spaces, selected driver
ID 28, created a device, and passed exact compute-shader readback. It reported
Vulkan 1.4.363, `geometryShader=1` and `fillModeNonSolid=1`. Transform feedback
remains absent. The shared probe also compiles for both existing PE targets.

All 13 launcher/packaging unit tests, shell syntax checks and workflow lint
passed. These unit tests use stand-in Wine and inspection tools. The dispatch
job now runs the real native driver probe before attempting Wine packaging.

Full Wine/FEX execution is blocked locally: installed Wine runtimes 4.7.54 and
4.7.71 have x86_64 Unix modules; `/Volumes/Wine`, Nix and the
`whisky-arm64-5.1.1` base runtime are unavailable. A controlled packaging attempt
with an empty runtime root failed before creating a staging directory, as
expected. No installed runtime was modified. This does not test Win32 surfaces,
PE translation, DXVK through native Wine, or game rendering.

Evidence is under `~/Library/Caches/winecx-kosmickrisp-arm64-lane/`:
`build.log`, `bundle/SOURCE.txt`, `host-probe.log`, `results.json`,
`package-preflight.log` and `preflight.json`.

### Supplied FEX and DXMT sources

The `3Shain/dxmt` `ci/arm64x` branch has a successful CI run
([35185728279](https://github.com/3Shain/dxmt/actions/runs/35185728279), head
`7c8dee1c2d73415301ceb7d1fa810861cef4cd67`). Its
`clang-release-arm64ec-windows-cross` artifact was downloaded locally.
`llvm-readobj` identifies all six PE DLLs as `COFF-ARM64X`; `winemetal.so` is a
native arm64 Mach-O library. It still links against native `winemac.so` and
`ntdll.so`. Those dependencies and runtime compatibility have not been tested.
The files remain in the test cache, outside installed runtimes.

The supplied [FEX-2609 release](https://github.com/FEX-Emu/FEX/releases/tag/FEX-2609)
has no prebuilt release assets. A checkout at
`395b132f346b1a45def246d10c52245edba1ef02` was configured with Apple Clang.
Configuration exited 1 at the platform check: `Unsupported system type Darwin`.
The release supports Linux and Windows builds; its Windows translation DLLs
are a separate build target from the native Unix helpers carried by this recipe.
No FEX source was changed.

DXMT's CI Wine dependency is also not a replacement base runtime: the
[wine-11.2 release](https://github.com/3Shain/wine/releases/tag/wine-11.2)
explicitly says it does not work yet and is intended for linking DXMT.
An entitled native Wine loader and compatible macOS FEX integration remain
required before Wine/FEX execution can be tested. Evidence is in
`fex-configure.log` and `supplied-sources-assessment.json` beside the earlier logs.

### Native FEX helper bootstrap

The first macOS FEX builds came from dappermint/FEX `4efc3abc`, using two
unpinned scripts (in history at `1297731`). Its Unix helpers built natively
with Apple clang, and passed eight callback checks each. Its PE translators
cross-built with llvm-mingw 20260616: `COFF-ARM64EC` and `COFF-ARM64`,
importing only Wine's `ntdll.dll` (and `wow64.dll` for WoW64). The pinned
build below replaces both scripts. Its evidence is under
`fex-helper-recipe/`, `fex-pe-arm64ec-*` and `fex-pe-wow64-*` in the cache
directory above.

## Pinned FEX build

`build-fex-arm64.sh` builds all four FEX files from upstream
[FEX-2609](https://github.com/FEX-Emu/FEX/releases/tag/FEX-2609)
(`395b132f346b1a45def246d10c52245edba1ef02`) plus the patches in `fex/patches`,
then packages them opt-in.

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
The entitlement is a hard requirement, not just packaging. A probe on macOS
27.2 with SIP enabled reproduced arm64-1117's `free_pagezero`. Without the
entitlement, `mach_vm_deallocate` of the 4 GiB pagezero reports success, but
fixed `mmap`/`mach_vm_allocate` at `0x7ffe0000` (`KUSER_SHARED_DATA`) and
`0x10000` still fail with "invalid address". An ad-hoc signature claiming
`com.apple.developer.cross-architecture-support` is killed at launch (SIGKILL),
because the entitlement is restricted. So a smoke run needs CrossOver's entitled
`wine.app` or an Apple-issued provisioning profile for that entitlement.
The same kill happens when an Apple Development identity signs with the
entitlement but no profile.

### Signing our own loader

`make-wine-app.sh` wraps an arm64 executable in a `wine.app` that is signed
with the entitlement, embedding the provisioning profile. Before signing, it
checks that the profile grants the entitlement, is for macOS, has not expired,
names an explicit App ID, was issued for the signing certificate, and covers
this Mac. A mismatch fails there with a reason, instead of as a kill at exec.
`package-arm64.sh` uses it when `WINE_APP_PROFILE` and `WINE_APP_IDENTITY`
(the identity's SHA-1) are set. It wraps the freshly built loader and adds
`Contents/MacOS/ntdll.so -> ../../../ntdll.so`, because the loader looks for
`ntdll.so` beside its resolved path. Otherwise it still carries CrossOver's
`wine.app`.

Getting the profile is up to Apple and the team's Account Holder. Apple's
public documentation does not list this entitlement, so the request may have
to go through Apple directly rather than the Capability Requests tab:

1. Register an explicit macOS App ID (for example `org.example.wine`) and
   request the cross-architecture support capability for it.
2. Register this Mac under Devices, using the provisioning UDID from
   `system_profiler SPHardwareDataType | grep 'Provisioning UDID'`.
3. Create a macOS development profile for that App ID, with the Apple
   Development certificate (`security find-identity -v -p codesigning`) and
   this Mac.

Test the profile with the probe before building Wine:

```sh
clang -arch arm64 -o /tmp/pagezero_probe tests/pagezero_probe.c
bash arm64/make-wine-app.sh /tmp/pagezero_probe /tmp/probe.app <profile> <identity-sha1>
/tmp/probe.app/Contents/MacOS/wine    # must print "low 4GB usable"
```

### Smoke run

`smoke-fex.sh WINE_DIR WORK` builds `tests/x86_smoke.c` as x86_64 and i686
and runs both in a fresh prefix. It passes only if each reports the arm64
host (`IsWow64Process2` native `0xaa64`) and matches exact FNV-1a, SSE2,
`sqrt` and exception-dispatch results. With `WINE_APP_PROFILE` and
`WINE_APP_IDENTITY` set, it first wraps the tree's loader with
`make-wine-app.sh`. Both test programs pass under the Rosetta x86_64 runtime,
which confirms their expected values (there `native` reads `0x8664`).

Without `/Volumes/Wine` or Nix, arm64-1117 builds with Homebrew's `bison`,
`flex`, `pkg-config`, `freetype`, `gnutls` and `molten-vk`. Put the keg-only
`bison` and `flex` and the shared llvm-mingw first on `PATH`, add
`LDFLAGS=-L$(brew --prefix molten-vk)/lib`, and use the configure options in
`build-arm64-unix.sh`. Then:

```sh
make install-lib DESTDIR=<stage>
bash arm64/install-fex.sh <stage>/opt/whiskywine <fex-bundle>
LLVM_MINGW=<llvm-mingw> bash arm64/smoke-fex.sh <stage>/opt/whiskywine <work>
```

Result on 2026-10-03, without a profile: arm64-1117 (`c8ef487`) built cleanly
and `wine --version` reports `wine-11.17`. Both programs stop at the same
point, before FEX loads: Wine logs `released the pagezero`, then
`failed to map the shared user data: c0000017` at `0x7ffe0000`. This matches
the probe. Logs are in `smoke-run/` in the cache directory above.
FEX on macOS has no hardware TSO switch, so x86 memory ordering
stays on FEX's software path. 16 KiB pages (FEX issue #1221) do not affect the
build, but runtime testing must cover them. ARM64EC assembly emits five
upstream X23/W23 warnings.
