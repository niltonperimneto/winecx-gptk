#!/bin/bash
# package the arm64 wine build as a whisky runtime.
#
# wine itself comes from the fresh build; everything wine does not build is
# carried over from the previous arm64 runtime: crossover's entitled wine.app
# (the soft pagezero), our FEX, DXMT's arm64ec winemetal/d3d11, and the dylib
# closure staged beside the unix modules. wine-mono is unpacked from upstream.
# FEX_BUNDLE=<dir> takes FEX from build-fex-arm64.sh instead, and
# WINE_APP_PROFILE=<profile> WINE_APP_IDENTITY=<sha1> signs our own wine.app.
#
# usage: package-arm64.sh <version> [base-runtime]
set -euo pipefail

VERSION="${1:?version, e.g. 5.1.0}"
BASE_ID="${2:-whisky-arm64-5.1.1}"
B="${B:-/Volumes/Wine/localdev/build-arm64-1117}"
MONO="${MONO:-/Volumes/Wine/scratch/wine-mono-11.3.0-arm64.tar.xz}"
RUNTIMES="${RUNTIMES_ROOT:-$HOME/Library/Application Support/com.dappermint.WhiskyPreview/Runtimes}"
BASE="$RUNTIMES/$BASE_ID"
OUT="$RUNTIMES/whisky-arm64-$VERSION"
STAGE="${STAGE:-/Volumes/Wine/localdev/stage-arm64-$VERSION}"

[ -d "$BASE/Wine" ] || { echo "no base runtime at $BASE"; exit 1; }
[ ! -e "$OUT" ] || { echo "$OUT exists, remove it first"; exit 1; }
[ ! -e "$OUT.tmp" ] || { echo "$OUT.tmp exists from an earlier package attempt"; exit 1; }

echo "== install"
rm -rf "$STAGE"
B="$B" MAKEFLAGS_EXTRA="DESTDIR=$STAGE" bash "$(dirname "$0")/build-arm64-unix.sh" install >/dev/null
W="$STAGE/opt/whiskywine"
U="$W/lib/wine/aarch64-unix"
P="$W/lib/wine/aarch64-windows"

echo "== carry over from $BASE_ID"
BU="$BASE/Wine/lib/wine/aarch64-unix"
BP="$BASE/Wine/lib/wine/aarch64-windows"
# Opt-in: our own loader in a wine.app signed under an Apple-issued profile
# for the cross-architecture entitlement, instead of CrossOver's.
if [ -n "${WINE_APP_PROFILE:-}" ]; then
    bash "$(dirname "$0")/make-wine-app.sh" "$U/wine" "$U/wine.app" "$WINE_APP_PROFILE" \
        "${WINE_APP_IDENTITY:?set WINE_APP_IDENTITY to the signing identity SHA-1}" ntdll.so=../../../ntdll.so
    rm -f "$U/wine"
else
    rm -f "$U/wine"
    ditto "$BU/wine.app" "$U/wine.app"
fi
ln -s wine.app/Contents/MacOS/wine "$U/wine"
cp -c "$BU"/*.dylib "$U/"
cp -c "$BU/winemetal.so" "$U/"
cp -c "$BP/winemetal.dll" "$P/"
# Opt-in: FEX from build-fex-arm64.sh instead of the base runtime's copy.
if [ -n "${FEX_BUNDLE:-}" ]; then
    bash "$(dirname "$0")/install-fex.sh" "$W" "$FEX_BUNDLE"
else
    cp -c "$BU/libarm64ecfex.so" "$BU/libwow64fex.so" "$U/"
    cp -c "$BP/xtajit.dll" "$BP/xtajit64.dll" "$P/"
fi
ditto "$BASE/DXMT" "$OUT.tmp/DXMT"

echo "== binaries"
find "$P" -name '*.a' -delete
rm -rf "$W/include" "$W/share/man"
for b in wine wine64 wineloader; do
    rm -f "$W/bin/$b"
    ln -s ../lib/wine/aarch64-unix/wine.app/Contents/MacOS/wine "$W/bin/$b"
done

echo "== wine-mono"
mkdir -p "$W/share/wine/mono"
tar -xJf "$MONO" -C "$W/share/wine/mono"

echo "== nix references"
leaks=0
for f in "$U"/*.so; do
    while read -r dep; do
        name=$(basename "$dep")
        if [ -e "$U/$name" ]; then
            install_name_tool -change "$dep" "@loader_path/$name" "$f" 2>/dev/null
        else
            echo "   unresolved $dep in $(basename "$f")"; leaks=1
        fi
    done < <(otool -L "$f" | awk 'NR>1 && $1 ~ /^\/nix\/store/ {print $1}')
done
[ "$leaks" = 0 ] || { echo "nix store references left, not packaging"; exit 1; }

# Opt-in only: the supplied driver must match the native Wine Unix half.
if [ -n "${KOSMICKRISP_BUNDLE:-}" ]; then
    bash "$(dirname "$0")/install-kosmickrisp.sh" "$W" "$KOSMICKRISP_BUNDLE"
fi

echo "== sign"
find "$U" -maxdepth 1 \( -name '*.so' -o -name '*.dylib' \) -exec codesign -f -s - {} \; 2>/dev/null
codesign -f -s - "$W/bin/wineserver"
codesign --verify "$U/wine.app" && echo "   wine.app still carries its signature"

echo "== assemble"
mv "$W" "$OUT.tmp/Wine"
cat > "$OUT.tmp/WhiskyWineVersion.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>dxmtVersion</key>
	<string>$(plutil -extract dxmtVersion raw "$BASE/WhiskyWineVersion.plist")</string>
	<key>gptkCapable</key>
	<false/>
	<key>name</key>
	<string>whisky-arm64</string>
	<key>version</key>
	<dict>
		<key>major</key>
		<integer>${VERSION%%.*}</integer>
		<key>minor</key>
		<integer>$(echo "$VERSION" | cut -d. -f2)</integer>
		<key>patch</key>
		<integer>${VERSION##*.}</integer>
	</dict>
</dict>
</plist>
EOF
mv "$OUT.tmp" "$OUT"
rm -rf "$STAGE"
"$OUT/Wine/bin/wine" --version
echo "== done: $OUT"
