#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
export PATH="$PWD/ccache-bin:$NIX_TOOL_PATH$PATH"
SDKROOT=$(/usr/bin/xcrun --show-sdk-path)
export SDKROOT
export CC="ccache /usr/bin/clang -arch x86_64"
export CROSSCC="x86_64-w64-mingw32-clang"
export CXX="ccache /usr/bin/clang++ -arch x86_64"
export CROSSCXX="x86_64-w64-mingw32-clang++"
export PKG_CONFIG_PATH="$NIX_PKG_CONFIG_PATH"
# -O2 unless asked otherwise: that is what wine itself ships and
# where a push build should stay. -O3 is opt-in for the runtimes we
# release; configure already adds -fno-strict-aliasing, the flag
# wine depends on, which is what makes raising it safe. -O0 roughly
# halves clang's time, for runs whose only job is to answer whether
# a patch works
case "$OPT_LEVEL" in
  release)
    OPT="-O3"
    ;;
  fast)
    OPT="-O0 -g0"
    echo "::warning::fast build, -O0 and no debug info; do not publish this artifact"
    ;;
  *)
    OPT="-O2"
    ;;
esac
echo "optimisation: $OPT" | tee -a "$GITHUB_STEP_SUMMARY"
# -Werror=unguarded-availability-new is the floor's enforcement: the
# builder's SDK is newer than MACOSX_DEPLOYMENT_TARGET, and clang's
# answer to an API above the target is a weak link, so the call is a
# null pointer on the older OS instead of a link error anyone would
# notice. as an error it stops at the line. host flags only, mingw
# does not know it.
export CFLAGS="$OPT -Wno-error=implicit-function-declaration -Werror=unguarded-availability-new $NIX_INCS"
export CROSSCFLAGS="$OPT"
export LDFLAGS="$NIX_LDFS"
# the one API that is already above the floor. all three call sites
# sit behind #ifdef HAVE_PIPE2 with a pipe + fcntl fallback next to
# them, so refusing the detection costs two syscalls per pipe and
# makes the self hosted lane's binaries loadable on the floor.
export ac_cv_func_pipe2=no
export ac_cv_lib_soname_freetype="libfreetype.6.dylib"
export ac_cv_lib_soname_gnutls="libgnutls.30.dylib"
# wine dlopens MoltenVK by soname; the bundled copy is found via
# the loader fallback path whisky already sets for its runtime
export ac_cv_lib_soname_MoltenVK="libMoltenVK.dylib"
mkdir -p build && cd build
../winecx/configure \
  --host=x86_64-apple-darwin24 \
  --with-wine-tools=../build-tools \
  --enable-archs=i386,x86_64 \
  --disable-tests \
  --without-x --without-wayland \
  --without-oss --without-alsa --without-pulse --without-sane \
  --without-usb --without-v4l2 --without-pcap --without-capi \
  --without-opencl --without-cups \
  --prefix=/opt/whiskywine || {
    echo "==== core tests section ===="
    sed -n '100,500p' config.log
    exit 1
  }

# wine's configure only warns when an optional library is missing, so
# a broken pkg-config path ships a runtime with no video decode and
# says nothing. winedmo backs mfsrcsnk / mfmp4srcsnk / mfasfsrcsnk,
# which is how a game plays its intro before it lets you in.
grep -q '^#define HAVE_FFMPEG 1' include/config.h || {
  echo "::error::ffmpeg was not found; winedmo would ship with no backend"
  grep -i 'ffmpeg\|libav' config.log | tail -20
  exit 1
}
echo "ffmpeg: found"

# same story for gstreamer, which is what wmvcore, the quartz
# DirectShow path and every mfplat decoder go through. configure
# disables winegstreamer with a notice and builds on happily.
grep -qE '^GSTREAMER_LIBS *= *.+' Makefile || {
  echo "::error::winegstreamer is not in the build; gstreamer was not found"
  grep -i 'gstreamer\|glib-2.0\|gst_pad_new' config.log | tail -30
  exit 1
}
echo "gstreamer: found"
