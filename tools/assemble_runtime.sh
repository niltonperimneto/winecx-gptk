#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
export PATH="$NIX_TOOL_PATH$PATH"

# this step ran 1517s on run 31625185579 against a make of 71s, and
# the obvious suspects all measured small on this machine: the
# per-file python3 13s over 700 files, codesign 10s, the tree copies
# under a second. so the cost is somewhere else and guessing at it
# wasted a round. report each phase and let the build say.
_t0=$SECONDS; _tp=$SECONDS
phase() { echo "::notice::phase $1: $((SECONDS-_tp))s (total $((SECONDS-_t0))s)"; _tp=$SECONDS; }

mkdir -p "$PWD/staging/opt/whiskywine/share/wine/mono" "$PWD/staging/opt/whiskywine/share/wine/gecko"
cp -R "$PWD/addons/mono"/* "$PWD/staging/opt/whiskywine/share/wine/mono/"
cp -R "$PWD/addons/gecko"/* "$PWD/staging/opt/whiskywine/share/wine/gecko/"
mkdir -p Libraries/Wine
cp -R staging/opt/whiskywine/bin Libraries/Wine/bin
cp -R staging/opt/whiskywine/lib Libraries/Wine/lib
cp -R staging/opt/whiskywine/share Libraries/Wine/share
host="Libraries/Wine/libexec/GameModeProcessHost.app"
mkdir -p "$host/Contents/MacOS"
/usr/bin/clang -arch x86_64 -O2 -mmacosx-version-min="$MACOSX_DEPLOYMENT_TARGET" \
  runtime/GameModeProcessHost/main.c -o "$host/Contents/MacOS/GameModeProcessHost"
/usr/bin/clang -arch x86_64 -O2 -mmacosx-version-min="$MACOSX_DEPLOYMENT_TARGET" \
  runtime/GameModeProcessHost/probe.c -o GameModeProcessHostProbe
cp runtime/GameModeProcessHost/Info.plist "$host/Contents/Info.plist"
codesign --force --sign - --timestamp=none "$host"
codesign --verify --strict --verbose=2 "$host"
host_stderr=$(mktemp)
set +e
host_output=$("$host/Contents/MacOS/GameModeProcessHost" "$PWD/GameModeProcessHostProbe" 2>"$host_stderr")
host_status=$?
set -e
[ "$host_status" -eq 37 ] || { echo "::error::Game Mode host lost exit status: $host_status"; exit 1; }
[ "$host_output" = "same-pid" ] || { echo "::error::Game Mode host changed PID"; exit 1; }
grep -Eq '^WHISKY_CHILD_POLICY result=host-entered native-pid=[0-9]+$' "$host_stderr" \
  || { echo "::error::Game Mode host did not report entry"; cat "$host_stderr"; exit 1; }
rm "$host_stderr" GameModeProcessHostProbe
phase "copy staging into Libraries"

# dxmt's wine-side half is ONLY the winemetal bridge. copying the
# whole payload dir in here would overwrite wine's builtin
# d3d11/dxgi with dxmt's, which makes every fresh prefix run dxmt
# silently -- and dxmt refuses the cross-process swapchains steam's
# post-2026-08 webhelper creates, so the login window never maps. it
# would also put nvapi64.dll in the builtins, which must never be
# visible to the webhelper: chromium probes for an nvidia gpu, loads
# d3dmetal, and takes the helper down with it. the d3d frontends stay
# per-bottle in Libraries/DXMT, deployed by whisky's backend picker.
dxmt=payload/$DXMT_COMMIT
cp -R "$dxmt/x86_64-unix/." Libraries/Wine/lib/wine/x86_64-unix/
cp "$dxmt/x86_64-windows/winemetal.dll" Libraries/Wine/lib/wine/x86_64-windows/
if [ -f "$dxmt/i386-windows/winemetal.dll" ]; then
  cp "$dxmt/i386-windows/winemetal.dll" Libraries/Wine/lib/wine/i386-windows/
fi

# and the per-bottle payloads whisky's backend picker offers
dxvk=payload/dxvk-macOS-async-v$DXVK_VERSION-20230507-repack
mkdir -p Libraries/DXVK Libraries/DXMT
cp -R "$dxvk/." Libraries/DXVK/
cp -R "$dxmt/x86_64-windows" Libraries/DXMT/x64
cp -R "$dxmt/i386-windows" Libraries/DXMT/x32

# whisky decides whether a prefix dll is "really" native by reading
# 16 bytes at offset 0x40 and looking for "Wine builtin DLL". dxmt's
# three d3d frontends carry that marker, so whisky's loader ignores
# them in a bottle and silently falls back to wined3d. strip it back
# to the stock DOS stub on exactly those three. nvapi64/nvngx must
# keep their markers: steam's webhelper dies without them.
for arch in x64 x32; do
  for dll in d3d11.dll d3d10core.dll dxgi.dll; do
    f="Libraries/DXMT/$arch/$dll"
    [ -f "$f" ] || continue
    printf '\016\037\272\016\000\264\011\315\041\270\001\114\315\041\220\220' \
      | dd of="$f" bs=1 seek=64 conv=notrunc status=none
  done
done
for arch in x64 x32; do
  for dll in d3d11.dll d3d10core.dll dxgi.dll; do
    f="Libraries/DXMT/$arch/$dll"
    [ -f "$f" ] || continue
    if dd if="$f" bs=1 skip=64 count=16 status=none | grep -q 'Wine builtin'; then
      echo "::error::$f still carries the builtin marker"; exit 1
    fi
  done
done

# gcc emits DWARF and nothing strips it, so ntdll.dll ships at 3.0MB
# against the stock engine's 0.7MB. and the .a import libraries are
# link-time only; the stock engine ships none. together they are
# ~600MB of the tree.
command -v x86_64-w64-mingw32-strip >/dev/null || {
  echo "::error::x86_64-w64-mingw32-strip not on PATH"; exit 1; }
# install-lib does not install these any more, so this should find
# nothing. kept as the guard that says so if that ever changes back
a=$(find Libraries/Wine/lib/wine/*-windows -name '*.a' | wc -l | tr -d ' ')
[ "$a" = 0 ] && echo "import libraries: none installed, as expected" \
             || echo "::warning::install-lib brought in $a import libraries, deleting"
find Libraries/Wine/lib/wine/*-windows -name '*.a' -delete
# batched: gnu strip prints an error for a non-COFF file (.tlb, .nls)
# and keeps going with the rest of the batch, unlike llvm-strip which
# abandoned it, so the old one-file-per-spawn form burned ~10k
# process launches, each taxed by the rosetta analytics daemons
find Libraries/Wine/lib/wine/*-windows -type f -print0 \
  | xargs -0 -P "$(sysctl -n hw.logicalcpu)" -n 64 \
      x86_64-w64-mingw32-strip --strip-debug 2>/dev/null || true
phase "strip the PE half"
# wine 11 installs the loader beside ntdll.so in lib/wine/<arch>-unix
# instead of in bin, and bin now gets only wineserver. that is not
# cosmetic: loader/main.c dlopens "ntdll.so" out of its own
# realpath'd directory, and ntdll computes the loader back the same
# way, as <ntdll_dir>/wine (dlls/ntdll/unix/loader.c). a copy into
# bin looks for bin/ntdll.so and dies, measured on the 26.3 tree:
#   wine: could not load ntdll.so: dlopen(.../bin/ntdll.so)
# symlinks are fine, because realpath resolves them back to the real
# directory before the dirname is taken. verified: bin/wine64 through
# a symlink prints winecx-26.3.0.
#
# whisky invokes bin/wine64, so bin still has to offer these names.
# CW HACK 22144 wants wineloader among them.
loader=Libraries/Wine/lib/wine/x86_64-unix/wine
[ -x "$loader" ] || { echo "::error::no loader at $loader"; exit 1; }
for n in wine wine64 wineloader; do
  ln -sf ../lib/wine/x86_64-unix/wine "Libraries/Wine/bin/$n"
done
./Libraries/Wine/bin/wine64 --version

# bundle the nix dylib closure flat into Wine/lib and rewrite
# store references to loader-relative so the tarball is portable
LIBDIR="$PWD/Libraries/Wine/lib"
scan() { otool -L "$1" 2>/dev/null | awk '/\/nix\/store/{print $1}'; }

# two kinds of dependency, and only one of them is discoverable.
# freetype and gnutls are dlopened by soname so they never
# appear in a load command: they have to be named. everything the
# unix modules link against directly (ffmpeg, and whatever it drags
# in) does appear, so seed from the tree itself rather than from a
# hand-kept list -- that list is what silently dropped a dependency
# every time the configure flags changed.
# gstreamer's plugins are dlopened out of a directory, not linked, so
# they have to be copied in before the closure walk runs -- their own
# dependencies (the codec libraries) are only reachable through them.
# patch 0018 points GStreamer here at run time.
mkdir -p "$LIBDIR/gstreamer-1.0"
for d in $(cat store-outs.txt); do
  [ -d "$d/lib/gstreamer-1.0" ] || continue
  for p in "$d/lib/gstreamer-1.0/"*.dylib; do
    [ -f "$p" ] || continue
    cp -L "$p" "$LIBDIR/gstreamer-1.0/$(basename "$p")"
    chmod u+w "$LIBDIR/gstreamer-1.0/$(basename "$p")"
  done
done
echo "gstreamer plugins: $(ls "$LIBDIR/gstreamer-1.0" | wc -l | tr -d ' ')"
phase "copy gstreamer plugins"

# MoltenVK is the one dlopened library that no longer comes out of the
# nix closure, so it is placed by hand. it needs no closure walk: its
# only dependencies are system frameworks and libc++, nothing in
# /nix/store. fixup() below still gives it a @loader_path id and an
# ad-hoc signature along with everything else in LIBDIR.
[ -f payload/libMoltenVK.dylib ] || {
  echo "::error::no libMoltenVK.dylib in payload, the fetch step did not run"; exit 1; }
cp payload/libMoltenVK.dylib "$LIBDIR/libMoltenVK.dylib"
chmod u+w "$LIBDIR/libMoltenVK.dylib"
echo "moltenvk: $MOLTENVK_VERSION $(lipo -archs "$LIBDIR/libMoltenVK.dylib")"

queue=""
for d in $(cat store-outs.txt); do
  for so in libfreetype.6.dylib libgnutls.30.dylib; do
    [ -f "$d/lib/$so" ] && queue="$queue $d/lib/$so"
  done
done
for f in Libraries/Wine/lib/wine/*-unix/*.so Libraries/Wine/bin/wine \
         "$LIBDIR"/gstreamer-1.0/*.dylib; do
  [ -f "$f" ] || continue
  queue="$queue $(scan "$f" | tr '\n' ' ')"
done
while [ -n "$queue" ]; do
  next=""
  for lib in $queue; do
    base=$(basename "$lib")
    [ -e "$LIBDIR/$base" ] && continue
    cp -L "$lib" "$LIBDIR/$base"
    chmod u+w "$LIBDIR/$base"
    next="$next $(scan "$LIBDIR/$base" | tr '\n' ' ')"
  done
  queue=""
  for l in $next; do
    [ -e "$LIBDIR/$(basename "$l")" ] || queue="$queue $l"
  done
done

phase "nix closure walk"

# two iconvs are needed and they are not interchangeable: _iconv is
# only in macOS's /usr/lib copy, _libiconv only in nix's. ask each
# library which it imports rather than naming names -- the name list
# this replaces had libintl alone, and missed libglib, which failed
# to load and took libgstreamer and every media decoder with it.
fixup() {
  local f="$1"
  local rel
  rel=$(python3 -c "import os,sys; print(os.path.relpath(sys.argv[1], os.path.dirname(sys.argv[2])))" "$LIBDIR" "$f")
  chmod u+w "$f" 2>/dev/null || true
  # the id, not only the dependencies: a dylib that still calls itself
  # /nix/store/... cannot be dlopened off the builder, which silently
  # cost us fonts, vulkan and tls in every build up to rt7
  # *.dylib* and not *.dylib: some libraries carry their version
  # after the extension (libfreeaptx.dylib.0, out of gst-plugins-bad's
  # closure), and the narrower glob left those with a /nix/store id
  case "$f" in
    *.dylib*) install_name_tool -id "@loader_path/$(basename "$f")" "$f" 2>/dev/null || true ;;
  esac
  for ref in $(scan "$f"); do
    if [[ "$(basename "$ref")" == libiconv*.dylib ]] && nm -u "$f" 2>/dev/null | grep -q '^ *_iconv$'; then
      install_name_tool -change "$ref" "/usr/lib/libiconv.2.dylib" "$f" 2>/dev/null || true
    else
      install_name_tool -change "$ref" "@loader_path/$rel/$(basename "$ref")" "$f" 2>/dev/null || true
    fi
  done
  codesign -f -s - "$f" 2>/dev/null || true
}
for f in "$LIBDIR"/*.dylib*; do
  if [ -f "$f" ]; then fixup "$f"; fi
done
# the plugins sit one level down, so fixup's relpath resolves to ".."
for f in "$LIBDIR"/gstreamer-1.0/*.dylib*; do
  if [ -f "$f" ]; then fixup "$f"; fi
done
find Libraries/Wine/bin -type f | while read -r f; do fixup "$f"; done
find Libraries/Wine/lib/wine -name "*.so" | while read -r f; do fixup "$f"; done

phase "fixup: install_name_tool and codesign"

# the reference runtime ships both names; match it
ln -sf libfreetype.6.dylib "$LIBDIR/libfreetype.dylib"

# the unix modules dlopen libgnutls/libfreetype/libMoltenVK by bare
# soname. dlopen searches the caller's rpaths, and lib/wine/<arch>-unix
# is two levels below the bundled dylibs, so without this entry none of
# them resolve: no tls, no fonts, no vulkan. reference runtimes carry it.
for f in Libraries/Wine/lib/wine/*-unix/*.so; do
  install_name_tool -add_rpath "@loader_path/../../" "$f" 2>/dev/null || true
  codesign -f -s - "$f" 2>/dev/null || true
done

# d3dmetal exposes no ID3D12VideoDevice, so a game that decodes video
# itself and asks d3d12 to convert NV12 to RGB gets E_NOINTERFACE and
# falls back to a path no windows machine runs: stalker cop ee draws
# its intro half resolution with the chroma flat, the olive artifact.
# this interposer supplies the missing video processor.
#
# built here but not installed here: it has to sit in the d3d12.dll
# builtin slot with apple's dll renamed alongside it, and apple's dll
# only lands when the gptk payload is deployed on the user's machine.
# install-whiskywine.sh --gptk does the swap.
mkdir -p Libraries/Wine/lib/gptk-video
# -fno-strict-aliasing for the same reason wine builds with it: this is
# com vtable code that puns objects between struct types and swaps
# vtable pointers through void ***, which is exactly what the aliasing
# rules let the compiler assume cannot happen.
x86_64-w64-mingw32-clang -shared -O2 -fno-strict-aliasing \
  -o Libraries/Wine/lib/gptk-video/d3d12shim.dll \
  "$GITHUB_WORKSPACE/gptk-video/d3d12shim.c" \
  "$GITHUB_WORKSPACE/gptk-video/d3d12shim.def" \
  -I"$GITHUB_WORKSPACE/gptk-video" -luuid -ldxguid

# wineserver memcmps "Wine builtin DLL" plus its NUL, 17 bytes, at
# file offset 0x40. without the stamp the loader finds it in
# WINEDLLPATH and ignores it as not a builtin.
python3 - Libraries/Wine/lib/gptk-video/d3d12shim.dll <<'EOF'
import struct, sys
p = sys.argv[1]
d = bytearray(open(p, 'rb').read())
if struct.unpack_from('<I', d, 0x3c)[0] < 0x60:
    raise SystemExit('pe header overlaps the builtin marker')
d[0x40:0x60] = b'Wine builtin DLL' + b'\0' * 16
open(p, 'wb').write(bytes(d))
EOF
phase "gptk-video: d3d12 video processor interposer"

# d3dmetal's IDXGIAdapter::CheckInterfaceSupport returns S_OK and
# writes -1 into the version out-param. engines format that
# LARGE_INTEGER as four words and read "65535.65535.65535.65535",
# which fails their minimum driver check: helldivers 2 puts a modal
# "GPU drivers are out of date" box in front of the game for it.
#
# this cannot live in the d3d12 shim. measured on helldivers 2:
# neither the exe nor game.dll imports d3d12 or dxgi statically, and
# the driver check runs before d3d12 is touched, so the d3d12 shim is
# not in the process yet and there is no import entry to patch.
x86_64-w64-mingw32-clang -shared -O2 -fno-strict-aliasing \
  -o Libraries/Wine/lib/gptk-video/dxgishim.dll \
  "$GITHUB_WORKSPACE/gptk-video/dxgishim.c" \
  "$GITHUB_WORKSPACE/gptk-video/dxgishim.def" \
  -luuid -ldxguid

python3 - Libraries/Wine/lib/gptk-video/dxgishim.dll <<'EOF'
import struct, sys
p = sys.argv[1]
d = bytearray(open(p, 'rb').read())
if struct.unpack_from('<I', d, 0x3c)[0] < 0x60:
    raise SystemExit('pe header overlaps the builtin marker')
d[0x40:0x60] = b'Wine builtin DLL' + b'\0' * 16
open(p, 'wb').write(bytes(d))
EOF
phase "gptk-video: dxgi driver version interposer"

# These shims are built outside Wine's makefiles, so they do not get
# Wine's normal CRT selection checks. Assert the contract on the PE
# import table before the artifacts can enter a runtime archive.
for shim in Libraries/Wine/lib/gptk-video/{d3d12shim,dxgishim}.dll; do
  imports="$(x86_64-w64-mingw32-objdump -p "$shim")"
  if grep -Eiq 'DLL Name: +msvcrt\.dll' <<<"$imports"; then
    echo "::error::$shim imports legacy msvcrt.dll"
    exit 1
  fi
  if ! grep -Eiq 'DLL Name: +api-ms-win-crt-' <<<"$imports"; then
    echo "::error::$shim has no UCRT API-set import"
    exit 1
  fi
done
phase "gptk-video: verified UCRT imports"

# whisky's GPTKImporter deploys apple's payload into this directory
# and symlinks lib/wine/x86_64-unix/{d3d10,d3d11,d3d12,dxgi}.so at
# libd3dshared.dylib. it must exist in the tarball or the importer
# has nowhere to put it; tar drops empty directories, hence the file.
mkdir -p Libraries/Wine/lib/external
cat > Libraries/Wine/lib/external/README <<'EOF'
apple's game porting toolkit payload goes here: D3DMetal.framework
and libd3dshared.dylib, as copies, with lib/wine/x86_64-unix/d3d10.so,
d3d11.so, d3d12.so and dxgi.so as symlinks to ../../external/
libd3dshared.dylib.

symlinks, never copies: libd3dshared resolves the framework through
@rpath/D3DMetal.framework/D3DMetal and its only LC_RPATH is
@loader_path, so a copy into x86_64-unix/ moves @loader_path away
from lib/external and d3dmetal dies on an assertion with no wine
error at all.

not shipped in this artifact: apple's gptk is not redistributable.
whisky's GPTKImporter fills this in from your own gptk install, and
Gaems/install-whiskywine.sh --gptk does the same for a manual
install.
EOF

cat > Libraries/WhiskyWineVersion.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>gptkCapable</key>
  <true/>
  <key>manifestVersion</key>
  <integer>2</integer>
  <key>releaseChannel</key>
  <string>canary</string>
  <key>name</key>
  <string>winecx-gptk</string>
  <key>wineVersion</key>
  <string>11.0</string>
  <key>wineSourceRevision</key>
  <string>WINE_SOURCE_REV</string>
  <key>patchset</key>
  <string>whisky-crossover-26.3-canary</string>
  <key>patchsetRevision</key>
  <string>PATCHSET_REV</string>
  <key>buildArchitecture</key>
  <string>x86_64+i386-wow64</string>
  <key>minimumMacOS</key>
  <string>26.0</string>
  <key>capabilities</key>
  <dict>
    <key>wsarecvmsg</key><true/>
    <key>ipv4ReceiveTOS</key><true/>
    <key>ipv6ReceiveTrafficClass</key><true/>
    <key>overlappedReceiveMessage</key><true/>
    <key>childLaunchPolicies</key><true/>
    <key>childLaunchPolicySchema</key><integer>1</integer>
    <key>gameModeProcessHost</key><true/>
    <key>graphicsClassifiers</key>
    <array>
      <string>d3d11</string><string>dxgi</string><string>d3d12</string>
      <string>d3d12core</string><string>vulkan</string>
    </array>
    <key>dxvk</key><true/>
    <key>dxmt</key><true/>
    <key>wined3d</key><true/>
    <key>wow64</key><true/>
    <key>gptkMajorVersions</key><array><integer>4</integer></array>
  </dict>
  <key>dxvkVersion</key>
  <string>DXVK_VER</string>
  <key>dxmtVersion</key>
  <string>DXMT_VER</string>
  <key>version</key>
  <dict>
    <key>major</key>
    <integer>VER_MAJOR</integer>
    <key>minor</key>
    <integer>VER_MINOR</integer>
    <key>patch</key>
    <integer>VER_PATCH</integer>
  </dict>
</dict>
</plist>
PLIST
# the version was a constant here, so every build stamped 4.0.0 whatever
# it was published as. the app reads this file, not the release tag, so
# a mismatch makes it offer the same update forever.
rv="${RUNTIME_VERSION_OVERRIDE:-}"
series_base=$(git log -1 -G'^  RUNTIME_SERIES: ' --format=%H -- .github/workflows/build.yml)
[ -n "$series_base" ] || { echo "::error::cannot find the series base commit"; exit 1; }
rv="${rv:-$RUNTIME_SERIES.$(git rev-list --count "$series_base..HEAD")}"
case "$rv" in
  [0-9]*.[0-9]*.[0-9]*) ;;
  *) echo "::error::runtime_version '$rv' is not major.minor.patch"; exit 1;;
esac
sed -i '' "s/DXVK_VER/$DXVK_VERSION/; s/DXMT_VER/$DXMT_VERSION/" Libraries/WhiskyWineVersion.plist
sed -i '' "s/WINE_SOURCE_REV/$WINECX_COMMIT/; s/PATCHSET_REV/${GITHUB_SHA}/" Libraries/WhiskyWineVersion.plist
sed -i '' "s/VER_MAJOR/${rv%%.*}/; s/VER_MINOR/$(echo "$rv" | cut -d. -f2)/; s/VER_PATCH/${rv##*.}/" \
  Libraries/WhiskyWineVersion.plist
grep -q VER_ Libraries/WhiskyWineVersion.plist && { echo "::error::version not substituted"; exit 1; }
echo "runtime version stamped: $rv"
# later steps name the release after it; recomputing the commit count
# there would drift the moment someone passes runtime_version
echo "RUNTIME_VERSION=$rv" >> "$GITHUB_ENV"
echo "runtime_version=$rv" >> "$GITHUB_OUTPUT"
set -euo pipefail
export PATH="$NIX_TOOL_PATH$PATH"
# Its own step, not part of install and package: that script sits near
# GitHub's 21000-character limit for one run block.

# Relay12's four modules live in the builtin directory itself: unlike
# the interposers they need nothing from apple's payload, so they ship
# in place. Whisky seeds their system32 placeholders per bottle. Each
# exports under its own file name, so Wine always loads this copy.
# d3d11on12host is built by Wine's own makefiles and is already a
# builtin; the other three are stamped the way the shims are.
relay12_src="payload/relay12-$RELAY12_RELEASE_TAG"
for module in d3d11on12core d3d11on12 d3d11on12host dxilconv; do
  cp "$relay12_src/x86_64-windows/$module.dll" Libraries/Wine/lib/wine/x86_64-windows/
done
python3 - Libraries/Wine/lib/wine/x86_64-windows/{d3d11on12core,d3d11on12,dxilconv}.dll <<'EOF'
import struct, sys
for p in sys.argv[1:]:
    d = bytearray(open(p, 'rb').read())
    if struct.unpack_from('<I', d, 0x3c)[0] < 0x60:
        raise SystemExit(p + ': pe header overlaps the builtin marker')
    d[0x40:0x60] = b'Wine builtin DLL' + b'\0' * 16
    open(p, 'wb').write(bytes(d))
EOF
for module in d3d11on12core d3d11on12 d3d11on12host dxilconv; do
  dll="Libraries/Wine/lib/wine/x86_64-windows/$module.dll"
  [ "$(dd if="$dll" bs=1 skip=64 count=16 2>/dev/null)" = "Wine builtin DLL" ] \
    || { echo "::error::$dll is not marked builtin"; exit 1; }
  if grep -Eiq 'DLL Name: +(d3d11|d3d11mt)\.dll' <<<"$(x86_64-w64-mingw32-objdump -p "$dll")"; then
    echo "::error::$dll imports d3d11: it would bind to apple's forwarder at load"
    exit 1
  fi
done
mkdir -p Libraries/Wine/share/relay12
cp -R "$relay12_src/licenses" "$relay12_src/SOURCE.txt" Libraries/Wine/share/relay12/
echo "::notice::relay12: installed $(ls Libraries/Wine/lib/wine/x86_64-windows/{d3d11on12core,d3d11on12,d3d11on12host,dxilconv}.dll | wc -l | tr -d " ") D3D11On12 modules"
