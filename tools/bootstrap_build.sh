#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
[ "$(uname -s)" = Darwin ] || { echo 'Darwin compilation requires a macOS host with Xcode.' >&2; exit 1; }
for tool in oras zstd ccache; do
    command -v "$tool" >/dev/null || brew install "$tool"
done
/usr/sbin/softwareupdate --install-rosetta --agree-to-license || true
arch -x86_64 /usr/bin/true
# Expose centrally pinned versions to later Actions steps, including publish.
cat tools/build/pins.env | sed -n 's/^export //p' >> "$GITHUB_ENV"
