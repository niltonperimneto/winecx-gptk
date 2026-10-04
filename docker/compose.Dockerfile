# syntax=docker/dockerfile:1
# Input references must identify the transport images built by Dockerfile,
# not ORAS file manifests. Prefer immutable @sha256:... references.
ARG SYSROOT_IMAGE
ARG TOOLS_IMAGE
ARG PAYLOADS_IMAGE
ARG CORE_IMAGE
FROM ${SYSROOT_IMAGE} AS sysroot
FROM ${TOOLS_IMAGE} AS tools
FROM ${PAYLOADS_IMAGE} AS payloads
FROM ${CORE_IMAGE} AS core

FROM scratch AS development
COPY --from=sysroot /winecx/sysroot/ /winecx/sysroot/
COPY --from=tools /winecx/tools/ /winecx/tools/
COPY --from=core /winecx/core/ /winecx/core/

FROM development AS assembly-inputs
COPY --from=payloads /winecx/payloads/ /winecx/payloads/
