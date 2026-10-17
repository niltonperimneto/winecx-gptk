#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
# the extracted form, which is what the stock whisky engine ships and
# what mscoree and mshtml load straight out of the datadir. the .msi
# form works too but appwiz then installs a copy into every prefix,
# costing ~180MB per bottle. versions come from winecx's own
# dlls/appwiz.cpl/addons.c, which is what the loaders look for:
# metahost.c wants wine-mono-$MONO_VERSION, nsembed.c wants
# wine-gecko-$GECKO_VERSION-$arch. addons.c only carries .msi hashes,
# so the tarball hashes are pinned here instead.
set -eu
mono_ver=$(sed -n 's/^#define MONO_VERSION "\(.*\)"/\1/p' winecx/dlls/appwiz.cpl/addons.c)
gecko_ver=$(sed -n 's/^#define GECKO_VERSION "\(.*\)"/\1/p' winecx/dlls/appwiz.cpl/addons.c)

# a hash has to be pinned for whatever version winecx asks for, so
# unknown versions still fail. keeping both bases in the table lets
# the wine 10 and wine 11 branches share this file.
case "$mono_ver" in
  9.4.0)  mono_sha=fd772219aacf46b825fa891a647af4a9ddf8439320101c231918b2037bf13858 ;;
  10.4.1) mono_sha=a16606ef0724202e6a6848ece6e0cbba64d11e2f11aefe744af1d93c6d9f99bb ;;
  11.2.0) mono_sha=c9fb2e2823acf30b000b8806177db0f40751786136dd3f8fb2be7897b1643d06 ;;
  11.3.0) mono_sha=54a1b0111c3fe4b785eae688af94d27e64995707ad648b6fee8000381b80d298 ;;
  *) echo "no pinned hash for mono $mono_ver"; exit 1 ;;
esac
case "$gecko_ver" in
  2.47.4) gecko_x86_sha=2cfc8d5c948602e21eff8a78613e1826f2d033df9672cace87fed56e8310afb6
          gecko_x64_sha=fd88fc7e537d058d7a8abf0c1ebc90c574892a466de86706a26d254710a82814 ;;
  *) echo "no pinned hashes for gecko $gecko_ver"; exit 1 ;;
esac
echo "mono $mono_ver, gecko $gecko_ver"

fetch() {
  curl -fsSL -o "$2" "$1"
  got=$(shasum -a 256 "$2" | cut -d' ' -f1)
  [ "$got" = "$3" ] || { echo "hash mismatch for $2: $got != $3"; exit 1; }
}

mkdir -p addons/mono addons/gecko
fetch "https://dl.winehq.org/wine/wine-mono/$mono_ver/wine-mono-$mono_ver-x86.tar.xz" \
      mono.tar.xz "$mono_sha"
fetch "https://dl.winehq.org/wine/wine-gecko/$gecko_ver/wine-gecko-$gecko_ver-x86.tar.xz" \
      gecko-x86.tar.xz "$gecko_x86_sha"
fetch "https://dl.winehq.org/wine/wine-gecko/$gecko_ver/wine-gecko-$gecko_ver-x86_64.tar.xz" \
      gecko-x64.tar.xz "$gecko_x64_sha"

tar -xJf mono.tar.xz -C addons/mono
tar -xJf gecko-x86.tar.xz -C addons/gecko
tar -xJf gecko-x64.tar.xz -C addons/gecko
[ -d "addons/mono/wine-mono-$mono_ver" ] || { echo "mono tarball layout changed"; exit 1; }
[ -d "addons/gecko/wine-gecko-$gecko_ver-x86_64" ] || { echo "gecko tarball layout changed"; exit 1; }
du -sh addons/mono addons/gecko

# a runtime with no d3d11 implementation cannot render chromium:
# wined3d goes through apple's opengl, frozen at 4.1, which gives
# ANGLE feature level 9_3 and a hard "GLES 3.0 > max supported 2.0".
# dxvk and dxmt are what make steam's ui appear.
mkdir -p payload
bash runtime/kosmickrisp/package-dxvk.sh payload/DXVK3
fetch "https://github.com/$DXMT_REPO/releases/download/$DXMT_RELEASE_TAG/$DXMT_ARTIFACT" \
      dxmt.tar.gz "$DXMT_ARTIFACT_SHA256"
tar -xzf dxmt.tar.gz -C payload
fetch "https://github.com/$RELAY12_REPO/releases/download/$RELAY12_RELEASE_TAG/relay12-$RELAY12_RELEASE_TAG.tar.gz" \
      relay12.tar.gz "$RELAY12_ARTIFACT_SHA256"
tar -xzf relay12.tar.gz -C payload
[ -d "payload/relay12-$RELAY12_RELEASE_TAG/x86_64-windows" ] || { echo "relay12 archive layout changed"; exit 1; }

ls payload
