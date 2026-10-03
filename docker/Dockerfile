# syntax=docker/dockerfile:1
# Run on Linux: package the native macOS build outputs as a transport image.
# Deliberately no RUN: these are Darwin binaries, not Linux executables.
FROM scratch AS sysroot
COPY sysroot/ /winecx/sysroot/

FROM scratch AS tools
COPY tools/ /winecx/tools/

FROM scratch AS payloads
COPY payloads/ /winecx/payloads/

FROM scratch AS kosmickrisp
COPY kosmickrisp/ /winecx/kosmickrisp/

FROM scratch AS core
COPY core/ /winecx/core/

FROM scratch AS runtime
ARG SOURCE_REVISION
ARG RUNTIME_VERSION
LABEL org.opencontainers.image.title="WineCX GPTK Darwin runtime" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="${RUNTIME_VERSION}" \
      io.winecx.target.platform="darwin/amd64" \
      io.winecx.image.usage="artifact-only"
COPY runtime/ /winecx/runtime/
