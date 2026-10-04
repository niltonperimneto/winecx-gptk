#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
# every build up to rt7 shipped dylibs whose own id was a /nix/store
# path that exists only on the runner, so they could not be dlopened
# anywhere else and the runtime silently lost fonts, vulkan and tls.
: > /tmp/badrefs
find Libraries -type f ! -type l -print0 | while IFS= read -r -d '' f; do
  file -b "$f" | grep -q Mach-O || continue
  # only absolute paths are a problem. @loader_path and bare names
  # both relocate; the reference runtime uses bare names throughout.
  otool -D "$f" 2>/dev/null | sed -n '2p' | grep -E '^/' \
    | grep -vE '^(/usr/lib/|/System/)' \
    | sed "s|^|id $f -> |" >> /tmp/badrefs || true
  otool -L "$f" 2>/dev/null | tail -n +3 | awk '{print $1}' \
    | grep -E '^/' | grep -vE '^(/usr/lib/|/System/)' \
    | sed "s|^|dep $f -> |" >> /tmp/badrefs || true
done
if [ -s /tmp/badrefs ]; then
  sed 's/^/::error::not relocatable: /' /tmp/badrefs
  echo "$(wc -l < /tmp/badrefs) absolute reference(s); refusing to ship"
  exit 1
fi
echo "relocatable: ok"

# v4.0.0 shipped minos 27.0 and dyld refuses that below 27. older is
# fine, newer is unloadable, and no other gate can see it.
floor="${MACOSX_DEPLOYMENT_TARGET%%.*}"
: > /tmp/toonew
find Libraries -type f ! -type l -print0 | while IFS= read -r -d '' f; do
  file -b "$f" | grep -q Mach-O || continue
  minos=$(otool -l "$f" 2>/dev/null | awk '/LC_BUILD_VERSION/{v=1} v && /minos/{print $2; exit}')
  [ -n "$minos" ] || continue
  if [ "${minos%%.*}" -gt "$floor" ]; then
    echo "$f minos $minos" >> /tmp/toonew
  fi
done
if [ -s /tmp/toonew ]; then
  sed 's/^/::error::built too new: /' /tmp/toonew
  echo "$(wc -l < /tmp/toonew) binary(s) above macOS $floor; refusing to ship"
  exit 1
fi
echo "deployment target: nothing newer than macOS $floor"

# v4.5.0 shipped an ntdll.so with an undefined pipe2 (#3): the macos
# 27 sdk declared it, the 26.0 floor does not have it, and the dlopen
# sweep below cannot see a lazily bound import on a host that has the
# symbol. so audit the artifact itself: every undefined symbol in
# every bundled mach-o must exist in the sdk's stubs or in something
# we bundle. weak imports count, a weak import is how the compiler
# links an api it knows is above the floor. authoritative only when
# the sdk matches the floor; wider than that the pass proves little,
# which the summary line says.
sdkpath=$(xcrun --sdk macosx --show-sdk-path)
sdkver=$(xcrun --sdk macosx --show-sdk-version)
python3 - "$sdkpath" "$sdkver" <<'PYEOF'
import os, re, subprocess, sys

sdk = sys.argv[1]
sdkver = sys.argv[2]
floor = int(os.environ['MACOSX_DEPLOYMENT_TARGET'].split('.')[0])

universe = set()
pat_list = re.compile(
    r"(symbols|weak-symbols|thread-local-symbols|objc-classes|objc-eh-types|objc-ivars)"
    r":\s*\[([^\]]*)\]", re.S)
for root, dirs, files in os.walk(sdk):
    for name in files:
        if not name.endswith('.tbd'):
            continue
        try:
            text = open(os.path.join(root, name), errors='ignore').read()
        except OSError:
            continue
        for kind, body in pat_list.findall(text):
            for tok in body.split(','):
                tok = tok.strip().strip("'\"")
                if not tok:
                    continue
                if kind in ('objc-classes', 'objc-eh-types'):
                    universe.add('_OBJC_CLASS_$_' + tok)
                    universe.add('_OBJC_METACLASS_$_' + tok)
                    universe.add('_OBJC_EHTYPE_$_' + tok)
                elif kind == 'objc-ivars':
                    universe.add('_OBJC_IVAR_$_' + tok)
                else:
                    universe.add(tok)

MAGICS = (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca')
machos = []
for root, dirs, files in os.walk('Libraries'):
    for name in files:
        p = os.path.join(root, name)
        if os.path.islink(p):
            continue
        try:
            with open(p, 'rb') as fh:
                magic = fh.read(4)
        except OSError:
            continue
        if magic in MAGICS:
            machos.append(p)

def nm(args, path):
    r = subprocess.run(['nm'] + args + [path], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ''

for p in machos:
    for line in nm(['-gUj'], p).splitlines():
        line = line.strip()
        if line and not line.endswith(':'):
            universe.add(line)

bad = {}
for p in machos:
    for line in nm(['-m'], p).splitlines():
        if '(undefined)' not in line:
            continue
        m = re.search(r'external (\S+)', line)
        if not m:
            continue
        sym = m.group(1)
        if sym not in universe:
            kind = 'weak, so the compiler knew' if ' weak ' in line else 'strong'
            bad.setdefault(p, set()).add('%s (%s)' % (sym, kind))

if bad:
    for p in sorted(bad):
        for s in sorted(bad[p]):
            print('::error::unresolvable at the floor: %s needs %s' % (p, s))
    total = sum(len(v) for v in bad.values())
    print('::error::%d undefined symbol(s) outside the sdk and the bundle' % total)
    sys.exit(1)

sdk_major = int(sdkver.split('.')[0])
if sdk_major > floor:
    print('undefined-symbol audit: clean against the %s sdk, but the floor is %d; '
          'only a matching sdk makes this a proof' % (sdkver, floor))
else:
    print('undefined-symbol audit: clean against the %s sdk, floor %d' % (sdkver, floor))
print('%d mach-o files, %d symbols in the universe' % (len(machos), len(universe)))
PYEOF

# a 64-bit-only tree cannot load syswow64\ntdll.dll, so every 32-bit
# program dies with c0000135. one build shipped with this empty.
i386=$(ls Libraries/Wine/lib/wine/i386-windows 2>/dev/null | wc -l | tr -d ' ')
[ "$i386" -gt 500 ] || { echo "::error::i386-windows has $i386 files"; exit 1; }
echo "i386 PE half: $i386 files"

# an unstripped PE half is ~600MB of DWARF nobody can use, and it is
# silent: everything still runs, the download is just twice the size.
# ntdll is 0.7MB stripped in the stock engine and 3.0MB unstripped here
# wc -c, not stat -f%z: the self-hosted runner puts nix coreutils
# ahead of /usr/bin, and GNU stat has no -f
ntdll=$(wc -c < Libraries/Wine/lib/wine/x86_64-windows/ntdll.dll | tr -d ' ')
[ "$ntdll" -lt 1500000 ] || {
  echo "::error::ntdll.dll is $ntdll bytes, the PE half did not get stripped"
  exit 1
}

# the extracted addons the stock engine also ships. without them a new
# prefix stops on a modal wine-mono dialog and waits for a click.
# globbed rather than pinned: which versions to fetch is already
# decided by winecx's addons.c, and asserting them twice means every
# bump breaks here too
for d in Libraries/Wine/share/wine/mono/wine-mono-* \
         Libraries/Wine/share/wine/gecko/wine-gecko-*-x86 \
         Libraries/Wine/share/wine/gecko/wine-gecko-*-x86_64; do
  [ -d "$d" ] || { echo "::error::missing $d"; exit 1; }
  echo "addons: $(basename "$d")"
done

# without a d3d11 implementation steam paints nothing: wined3d goes
# through apple's opengl, frozen at 4.1, and ANGLE reports feature
# level 9_3 against chromium's hard GLES 3.0 requirement
[ -f Libraries/DXVK/x64/d3d11.dll ] || { echo "::error::no dxvk payload"; exit 1; }
[ -f Libraries/Wine/lib/wine/x86_64-unix/winemetal.so ] || {
  echo "::error::no dxmt builtin"; exit 1; }
[ -d Libraries/Wine/lib/external ] || {
  echo "::error::no lib/external for the gptk payload"; exit 1; }
# the builtin d3d must be wine's own: a dxmt-flavoured builtin
# hijacks every fresh prefix and then refuses steam's cross-process
# swapchains, so the login window never maps
for d in d3d11 dxgi d3d10core; do
  if strings "Libraries/Wine/lib/wine/x86_64-windows/$d.dll" 2>/dev/null \
     | grep -q 'DXMT_\|dxmt\.con'; then
    echo "::error::builtin $d.dll is dxmt, not wine"; exit 1
  fi
done
# and nvapi64 must not be a builtin at all
if [ -f Libraries/Wine/lib/wine/x86_64-windows/nvapi64.dll ]; then
  echo "::error::nvapi64.dll is in the builtins; the webhelper dies on it"
  exit 1
fi
echo "graphics payloads: ok"

# and the media half: winedmo builds whether or not ffmpeg was there,
# it just does nothing without it
otool -L Libraries/Wine/lib/wine/x86_64-unix/winedmo.so \
  | grep -q 'libavcodec' || {
  echo "::error::winedmo.so has no ffmpeg; video decode would be dead"
  exit 1
}
otool -L Libraries/Wine/lib/wine/x86_64-unix/winegstreamer.so \
  | grep -q 'libgstreamer-1.0' || {
  echo "::error::no winegstreamer; wmvcore, quartz and the mfplat decoders would be dead"
  exit 1
}
plugins=$(ls Libraries/Wine/lib/gstreamer-1.0 2>/dev/null | wc -l | tr -d ' ')
[ "$plugins" -gt 50 ] || {
  echo "::error::only $plugins gstreamer plugins bundled"
  exit 1
}
echo "media: ok, $plugins gstreamer plugins"

# the three gates above inspect the tree; none of them runs anything,
# which is how a build that could not create a single top-level window
# passed all of them. the display driver failing to init is invisible
# short of asking for a window: wine falls back to nodrv, keeps going,
# and only CreateWindowEx tells you, with ERROR_INVALID_WINDOW_HANDLE.
export PATH="$NIX_TOOL_PATH$PATH"
x86_64-w64-mingw32-clang -O2 -o winmsg.exe tests/winmsg.c -luser32

export WINEPREFIX="$PWD/smoke-prefix"
export DYLD_FALLBACK_LIBRARY_PATH="$PWD/Libraries/Wine/lib"
export WINEDLLOVERRIDES="mscoree=d;mshtml=d"
WINEDEBUG=-all ./Libraries/Wine/bin/wine64 wineboot -u >/dev/null 2>&1 || true

WINEDEBUG=+winediag ./Libraries/Wine/bin/wine64 winmsg.exe > smoke.log 2>&1 || true
grep -E '^\[|^RESULT|^FAIL' smoke.log | tee -a "$GITHUB_STEP_SUMMARY"

if grep -q "nodrv_CreateWindow" smoke.log; then
  echo "::error::the display driver did not load; the runtime fell back to nodrv"
  sed -n 's/^.*winediag:/  /p' smoke.log | head -5
  exit 1
fi
grep -q "RESULT: windows ok" smoke.log || {
  echo "::error::the runtime cannot create a window"
  tail -20 smoke.log
  exit 1
}
echo "windows: ok"


# and media foundation, which is the only way to tell whether the
# bundled gstreamer plugins were actually found: a wrong plugin path
# still starts, still answers MFStartup, and just has no decoders
x86_64-w64-mingw32-clang -O2 -o mfprobe.exe tests/mfprobe.c -lmfplat -lole32
WINEDLLOVERRIDES="mscoree=d;mshtml=d" WINEDEBUG=-all \
  ./Libraries/Wine/bin/wine64 mfprobe.exe > mf.log 2>&1 || true
grep -E '^\[|^RESULT|^FAIL' mf.log | tee -a "$GITHUB_STEP_SUMMARY"
grep -q "RESULT: media foundation has decoders" mf.log || {
  echo "::error::media foundation has no h264 decoder; gstreamer found no plugins"
  tail -20 mf.log
  exit 1
}
echo "media foundation: ok"


# the check above runs on the builder, where the /nix/store originals
# satisfy anything the bundled copies cannot, so it passed for months
# while the shipped libglib could not load at all. load the bundled
# files by path instead. x86_64 like the bundle, which is the same
# rosetta exposure the smoke tests above already take.
/usr/bin/clang -arch x86_64 -O2 -o dlopenall tests/dlopenall.c
file ./dlopenall | grep -q 'Mach-O 64-bit executable x86_64' || {
  echo "::error::dlopenall is not a native x86_64 Mach-O executable"
  file ./dlopenall
  exit 1
}
find Libraries/Wine/lib -name '*.dylib*' -o -name '*.so' \
  | sort | tr '\n' '\0' | xargs -0 ./dlopenall > dlopen.log 2>&1 || true
grep '^FAIL' dlopen.log | head -20 || true
tail -1 dlopen.log | tee -a "$GITHUB_STEP_SUMMARY"
grep -q "RESULT: 0 of" dlopen.log || {
  echo "::error::bundled libraries do not load; the runtime is broken for anyone without this nix store"
  exit 1
}

set -euo pipefail
x86_64-w64-mingw32-clang -O2 -Wall -Werror -o wsarecvmsg.exe tests/wsarecvmsg.c -lws2_32

# Keep this probe out of the window/media smoke prefix and always stop
# its wineserver.  On a freshly-created prefix wine64 can report 1
# after the child has returned 0 (during background prefix teardown),
# so the probe's explicit RESULT line is the authoritative verdict.
export WINEPREFIX="$PWD/network-smoke-prefix"
export DYLD_FALLBACK_LIBRARY_PATH="$PWD/Libraries/Wine/lib"
export WINEDLLOVERRIDES="mscoree=d;mshtml=d"
cleanup_network_prefix() {
  WINEDEBUG=-all ./Libraries/Wine/bin/wine64 wineboot -k >/dev/null 2>&1 || true
}
trap cleanup_network_prefix EXIT
WINEDEBUG=-all ./Libraries/Wine/bin/wine64 wineboot -u >/dev/null 2>&1 || true

set +e
WINEDEBUG=-all ./Libraries/Wine/bin/wine64 wsarecvmsg.exe | tee wsarecvmsg.log
pipeline_status=("${PIPESTATUS[@]}")
set -e
[ "${pipeline_status[1]}" -eq 0 ] || {
  echo "::error::tee could not write the network verification log"
  exit "${pipeline_status[1]}"
}
if [ "${pipeline_status[0]}" -ne 0 ]; then
  echo "::warning::wine64 returned ${pipeline_status[0]} after the network probe; validating the probe result"
fi

# MinGW programs may emit CRLF even when Wine forwards stdout to a
# Unix pipe. Store a deterministic receipt and match it exactly.
tr -d '\r' < wsarecvmsg.log > wsarecvmsg.normalized.log
mv wsarecvmsg.normalized.log wsarecvmsg.log
grep -q '^RESULT: WSARecvMsg IPv4 TOS, IPv6 traffic class, and overlapped receive verified$' wsarecvmsg.log
cp wsarecvmsg.log Libraries/RuntimeNetworkVerification.txt
cleanup_network_prefix
trap - EXIT

set -euo pipefail
# The shipped, builtin-stamped shim runs against tests/d3d12shim_mock.c
# built as d3dmt.dll, the name the shim loads Apple's d3d12 under.
# That checks what reaches d3dmetal: the tight-alignment answer, the
# zero-copy barrier path, and that batches over 32 barriers are kept.
mkdir -p d3d12shim-test
cp Libraries/Wine/lib/gptk-video/d3d12shim.dll d3d12shim-test/
x86_64-w64-mingw32-clang -shared -O2 -Wall -Werror -o d3d12shim-test/d3dmt.dll \
  tests/d3d12shim_mock.c tests/d3d12shim_mock.def -luuid
x86_64-w64-mingw32-clang -O2 -Wall -Werror -o d3d12shim-test/d3d12shim_test.exe \
  tests/d3d12shim.c -luuid -ldxguid
# For the Relay12 route: Apple's exact D3D11On12CreateDevice stub as
# d3d11.dll, and a d3d11on12core.dll that proves the call arrived.
x86_64-w64-mingw32-clang -shared -O2 -Wall -Werror -o d3d12shim-test/d3d11.dll \
  tests/d3d11_on12stub_mock.c tests/d3d11_on12stub_mock.def
x86_64-w64-mingw32-clang -shared -O2 -Wall -Werror -o d3d12shim-test/d3d11on12core.dll \
  tests/d3d11on12core_mock.c tests/d3d11on12core_mock.def

export WINEPREFIX="$PWD/d3d12shim-prefix"
export DYLD_FALLBACK_LIBRARY_PATH="$PWD/Libraries/Wine/lib"
export WINEDLLOVERRIDES="mscoree=d;mshtml=d"
cleanup_shim_prefix() {
  WINEDEBUG=-all ./Libraries/Wine/bin/wine64 wineboot -k >/dev/null 2>&1 || true
}
trap cleanup_shim_prefix EXIT
WINEDEBUG=-all ./Libraries/Wine/bin/wine64 wineboot -u >/dev/null 2>&1 || true

# As with the network probe, the RESULT line is the verdict, not
# wine64's exit status during prefix teardown.
(cd d3d12shim-test && WINEDEBUG=-all ../Libraries/Wine/bin/wine64 d3d12shim_test.exe) \
  > d3d12shim.log 2>&1 || true
tr -d '\r' < d3d12shim.log | grep -E '^\[|^RESULT' | tee -a "$GITHUB_STEP_SUMMARY"
tr -d '\r' < d3d12shim.log | grep -q '^RESULT: d3d12shim ok$' || {
  echo "::error::the d3d12 interposer forwarded something d3dmetal must not see"
  exit 1
}

# The Relay12 route decides once per process, so each case is its own
# run. Native d3d11 and d3d11on12core load the mocks beside the test.
# on12-launcher runs the same test as steamwebhelper.exe, one of the
# launcher processes the route must never touch.
cp d3d12shim-test/d3d12shim_test.exe d3d12shim-test/steamwebhelper.exe
for mode in on12-off on12-on on12-foreign on12-listed on12-unlisted on12-skipped on12-launcher; do
  exe=d3d12shim_test.exe
  [ "$mode" = on12-launcher ] && exe=steamwebhelper.exe
  (cd d3d12shim-test && env -u RELAY12_EXPERIMENTAL_FRAME -u RELAY12_EXPERIMENTAL_FRAME_APPS \
    -u RELAY12_EXPERIMENTAL_FRAME_SKIP WINEDEBUG=-all \
    WINEDLLOVERRIDES="d3d11,d3d11on12core=n;mscoree,mshtml=d" \
    ../Libraries/Wine/bin/wine64 "$exe" "$mode") > "d3d12shim-$mode.log" 2>&1 || true
  tr -d '\r' < "d3d12shim-$mode.log" | grep -E '^\[|^RESULT' | tee -a "$GITHUB_STEP_SUMMARY"
  tr -d '\r' < "d3d12shim-$mode.log" | grep -q "^RESULT: d3d12shim $mode ok\$" || {
    echo "::error::the d3d12 interposer's Relay12 route failed its $mode case"
    exit 1
  }
done
