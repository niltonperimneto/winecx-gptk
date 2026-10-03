#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
outs=$(cat native-store-outs.txt)
pcp=""
for d in $outs; do
  [ -d "$d/lib/pkgconfig" ] && pcp="$d/lib/pkgconfig:$pcp"
done
export PATH="$NIX_TOOL_PATH$PATH"
SDKROOT=$(/usr/bin/xcrun --show-sdk-path)
export SDKROOT
export CC="ccache /usr/bin/clang"
export PKG_CONFIG_PATH="$pcp"
mkdir -p build-tools && cd build-tools
# this configure runs natively, so without an explicit arch list wine
# defaults to aarch64 and stops on "PE cross-compilation is required
# for aarch64". only __tooldeps__ is ever built here, so the list only
# has to name archs a PE compiler exists for -- the same two the real
# build uses.
../winecx/configure \
  --enable-archs=i386,x86_64 \
  --without-x --without-wayland --without-gstreamer \
  --without-oss --without-alsa --without-pulse --without-sane \
  --without-usb --without-v4l2 --without-pcap --without-capi \
  --without-opencl --without-ffmpeg --without-cups \
  --disable-tests
make -j"$(sysctl -n hw.ncpu)" __tooldeps__
# wrc resolves its nls data relative to its own binary
# (tools/wrc/../../nls, see get_nlsdir in tools/tools.h), and
# __tooldeps__ never populates an out-of-tree nls dir. a persistent
# workspace can carry one from an earlier full make, which is why
# this only surfaces on a fresh hosted runner: the main build's
# first .res file dies with "unable to load locale.nls".
# link the file, not the dir: if configure already made nls/ a real
# directory, a dir symlink silently lands inside it as nls/nls,
# which is how the first attempt at this fix failed. same shape as
# the main build's own locale.nls rule. then prove it resolves, so
# a regression fails here and not two minutes into make.
rm -rf nls && mkdir nls && cp ../winecx/nls/locale.nls nls/locale.nls
test -r nls/locale.nls || { echo "::error::tools nls dir does not resolve"; exit 1; }
