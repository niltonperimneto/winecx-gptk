#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/pins.env"
: "${RUNTIME_VERSION:?runtime version required}" "${GITHUB_SHA:?source revision required}"
shasum -a 256 -c Libraries.tar.gz.sha256
tag="runtime-canary-v$RUNTIME_VERSION"
sha=$(cut -d' ' -f1 < Libraries.tar.gz.sha256)
work=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/runtime-publish.XXXXXX")
trap 'rm -rf "$work"' EXIT
if gh release view "$tag" >/dev/null 2>&1; then
    gh release download "$tag" --pattern Libraries.tar.gz.sha256 --dir "$work"
    existing=$(cut -d' ' -f1 < "$work/Libraries.tar.gz.sha256")
    [ "$sha" = "$existing" ] || {
        echo "::error::$tag already identifies different bytes; choose a new runtime version"; exit 1;
    }
    echo "$tag already contains this archive; preserving published assets"
    exit 0
fi
{
    echo '| | |'
    echo '|---|---|'
    echo "| winecx | $WINECX_COMMIT |"
    echo "| dxvk | $DXVK_KOSMICKRISP_VERSION |"
    echo "| dxmt | $DXMT_COMMIT |"
    echo "| Vulkan provider | KosmicKrisp |"
    echo "| sha256 | $sha |"
    echo
    echo "Built from $GITHUB_SHA. Available only through the opt-in layout-v2 canary catalog."
} > "$work/notes.md"
gh release create "$tag" Libraries.tar.gz Libraries.tar.gz.sha256 \
    WhiskyWineVersion.plist RuntimeManifest.json RuntimeNetworkVerification.txt \
    --target "$GITHUB_SHA" --prerelease --title "canary runtime $RUNTIME_VERSION" \
    --notes-file "$work/notes.md"
