# Experimental KosmicKrisp runtime

This is the first implementation stage of the migration: an optional x86_64
Vulkan loader and KosmicKrisp ICD, loaded by the existing Rosetta Wine host.
The normal Wine entry points retain MoltenVK and the existing DXVK payload.
Upstream DXVK is not enabled: conformance alone does not establish its required
geometry shader, transform feedback, extension-feature, and limit support.

## Build and run

See [CI gates and game configuration](kosmickrisp-ci.md). Pushes to the
experimental branch run this lane automatically. You can also dispatch
`.github/workflows/build.yml` with the
`kosmickrisp` checkbox enabled. This produces a
`whiskywine-gptk-libraries-kosmickrisp-experimental` artifact (with an additional
suffix for fast builds). The publish job excludes this option even on `main`.
It does not publish a release or update the runtime catalog.

Extract the artifact into a separate directory and use a disposable Wine prefix:

```sh
WINEPREFIX="$HOME/Library/Application Support/winecx-kosmickrisp-test" \
  ./Libraries/Wine/bin/wine-kosmickrisp /absolute/path/to/program.exe
```

The launcher selects the bundled ICD with `VK_DRIVER_FILES` and the host loader
with `WINE_VULKAN_LIBRARY`. An experimental-only Wine patch adds the latter
override without changing CrossOver's graphics-backend identifier. It does not
install DLL overrides, select a Direct3D backend, or change the DXVK payload.
Invoke this launcher by its installed path; external symlinks are not supported.
Use a fresh prefix without application-local Vulkan shims for capability tests.

## Build inputs and package layout

`runtime/kosmickrisp/pins.env` pins the shadexternals cross-build recipe, its
Mesa fork/submodule revision, Khronos Vulkan loader, and Vulkan headers. This
uses the recipe's separate native compiler-tools build and x86_64 target build;
an arm64 ICD cannot be loaded by this Wine host. The deployment target is 26.0.
Python 3.13 is selected explicitly; Mesa requires at least 3.10. Python build
packages are versioned in the workflow. Homebrew build dependencies
and the runner's Xcode are not immutable; `BUILD-TOOLS.txt` records the tool
versions. This is not yet a fully reproducible toolchain.

The self-contained directory `Wine/lib/kosmickrisp/` contains:

- `libvulkan.1.dylib`: the Khronos loader.
- `libvulkan_kosmickrisp.dylib`: the Mesa driver.
- `kosmickrisp_icd.json`: the generated manifest, with a relative library path.
- `libz.1.dylib`: the x86_64 zlib fallback dependency when used by Mesa.
- Source pins, build-tool versions, license notices, and successful probe logs.

The build requires x86_64 libraries, rewrites their install IDs, and signs and
verifies them. Apart from the explicitly bundled zlib, it rejects non-system
dylib dependencies instead of depending on the builder's Homebrew installation.
If a newer Mesa pin adds a
runtime dependency, bundle and validate it explicitly before relaxing that gate.

## Validation and remaining gates

The workflow first copies the bundle into a different path containing spaces
and runs an x86_64 host probe under Rosetta. After packaging Wine, it compiles
and runs the same probe as both x86_64 and i686 Windows executables. Each probe
requires the KosmicKrisp driver ID and a successful graphics-device creation.
The Windows probes also use `--present` to verify compute-shader readback and
present in windowed, resized, borderless-fullscreen, and restored modes.
It records API version, selected Features2 fields, push-constant limits, device
extensions, and transform-feedback features when available. Missing optional
features are reported, not converted to successful DXVK compatibility claims.

These probes do not establish general visual/shader correctness or game
performance. See [local test results](kosmickrisp-test-results.md).
The remaining migration gates are:

1. Complete a clean macOS 26 CI build and review the host and Wine probe logs.
2. Exercise Win32-to-Metal surface creation, presentation, resize, and fullscreen.
3. Audit all required features and limits against one pinned upstream DXVK
   version, including requirements conditional on the requested D3D feature level.
4. Validate D3D9/10/11 rendering, Steam UI, representative games, and performance
   with unmodified DXVK and no feature-masking shim.
5. Only then consider changing the default backend or release metadata.

References: [RPCS3 loader integration](https://github.com/RPCS3/rpcs3/pull/17735),
[RPCS3 experimental builds](https://github.com/RPCS3/rpcs3/pull/17902),
[x86_64 cross-build recipe](https://github.com/shadexternals/mesa-kosmickrisp),
[Mesa documentation](https://docs.mesa3d.org/drivers/kosmickrisp.html), and
[DXVK requirements](https://github.com/doitsujin/dxvk/wiki/Driver-support).
