#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
NIXPKGS="github:NixOS/nixpkgs/$NIXPKGS_REV"
tools=$(nix build --no-link --print-out-paths \
  "$NIXPKGS#bison" "$NIXPKGS#flex" "$NIXPKGS#pkg-config")
printf "%s\n" $tools > nix-tool-outs.txt
toolpath=""
for t in $tools; do toolpath="$t/bin:$toolpath"; done
echo "NIX_TOOL_PATH=$toolpath" >> "$GITHUB_ENV"

outs=""
# ffmpeg-headless, not ffmpeg: winedmo wants libavutil, libavformat
# and libavcodec and nothing else, and the full build drags in SDL
# and an x11 closure that would be bundled along with it
# glib and orc are pulled in by name because pkg-config resolves
# gstreamer-1.0.pc's Requires: through PKG_CONFIG_PATH and nothing
# here reads nixpkgs' propagated-build-inputs, so without them the
# gstreamer probe fails on a missing glib-2.0 and configure quietly
# drops winegstreamer
for p in freetype gnutls libpng zlib brotli bzip2 nettle libtasn1 libidn2 p11-kit libunistring gmp vulkan-headers ffmpeg-headless \
         glib orc \
         gst_all_1.gstreamer gst_all_1.gst-plugins-base gst_all_1.gst-plugins-good \
         gst_all_1.gst-plugins-bad gst_all_1.gst-libav; do
  # ffmpeg splits its dylibs into a "lib" output that neither dev nor
  # out carries: without it configure finds the headers, fails the
  # link test, and quietly disables ffmpeg. missing outputs on the
  # other packages are skipped by the guard below.
  for o in dev out lib; do
    if path=$(nix build --no-link --print-out-paths \
      "$NIXPKGS#legacyPackages.x86_64-darwin.$p.$o" 2>/dev/null); then
      outs="$outs $path"
    fi
  done
done
echo "$outs" | tr ' ' '\n' | grep . > store-outs.txt
pcp=""
incs=""
ldfs=""
for d in $outs; do
  [ -d "$d/lib/pkgconfig" ] && pcp="$d/lib/pkgconfig:$pcp"
  [ -d "$d/include" ] && incs="$incs -I$d/include"
  [ -d "$d/lib" ] && ldfs="$ldfs -L$d/lib"
done
{
  echo "NIX_PKG_CONFIG_PATH=$pcp"
  echo "NIX_INCS=$incs"
  echo "NIX_LDFS=$ldfs"
} >> "$GITHUB_ENV"
cat store-outs.txt

outs=$(nix build --no-link --print-out-paths \
  "$NIXPKGS#freetype.dev" "$NIXPKGS#freetype.out" \
  "$NIXPKGS#libpng.dev" "$NIXPKGS#zlib.dev" \
  "$NIXPKGS#brotli.dev" "$NIXPKGS#bzip2.dev")
printf "%s\n" $outs > native-store-outs.txt
