#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
command=${1:?usage: oci.sh restore|pull|push COMPONENT [REFERENCE or PATH...]}
component=${2:?component required}
registry=${OCI_REGISTRY:-ghcr.io/${GITHUB_REPOSITORY:-niltonperimneto/winecx-gptk}}
registry=$(printf '%s' "$registry" | tr '[:upper:]' '[:lower:]')
package="$RUNNER_TEMP/oci-$component"
mkdir -p "$package"

pull() {
    local reference=$1
    # Consume the exact manifest resolved by the producer, never a moving tag.
    [[ "$reference" == *@sha256:* ]] || { echo 'OCI pulls require a digest reference' >&2; exit 1; }
    rm -f "$package/layer.tar.zst" "$package/metadata.json"
    oras pull "$reference" --output "$package"
    bash tools/import_layer.sh "$component" "$package"
}
case "$command" in
    restore)
        key=$(python3 tools/build/cache_key.py "$component")
        reference="$registry/$component:$key"
        echo "tag=$reference" >> "$GITHUB_OUTPUT"
        if [ "${REBUILD_ALL:-false}" = true ]; then
            echo 'hit=false' >> "$GITHUB_OUTPUT"
            exit 0
        fi
        if digest=$(oras resolve "$reference" 2> "$package/resolve-error"); then
            pull "$registry/$component@$digest"
            echo 'hit=true' >> "$GITHUB_OUTPUT"
            echo "ref=$registry/$component@$digest" >> "$GITHUB_OUTPUT"
            printf 'OCI %s: `%s/%s@%s`\n\n' "$component" "$registry" "$component" "$digest" >> "$GITHUB_STEP_SUMMARY"
        elif grep -Eqi 'MANIFEST_UNKNOWN|NAME_UNKNOWN|not found|404' "$package/resolve-error"; then
            echo 'hit=false' >> "$GITHUB_OUTPUT"
        else
            cat "$package/resolve-error" >&2
            exit 1
        fi
        ;;
    pull) pull "${3:?digest reference required}" ;;
    push)
        shift 2
        if [ "$component" = sysroot ]; then
            roots=$(cat store-outs.txt native-store-outs.txt nix-tool-outs.txt)
            # Export the complete native + target closure with original store
            # paths; copying dylibs alone breaks .pc files and transitive links.
            nix-store --query --requisites $roots | sort -u > closure-paths.txt
            closure_paths=()
            while IFS= read -r store_path; do closure_paths+=("$store_path"); done < closure-paths.txt
            nix-store --export "${closure_paths[@]}" > sysroot-closure.nar
            # Actions creates a new GITHUB_ENV file for every step. Persist
            # inherited values rather than rereading an earlier step's file.
            printf 'NIX_TOOL_PATH=%s\nNIX_PKG_CONFIG_PATH=%s\nNIX_INCS=%s\nNIX_LDFS=%s\n' \
                "$NIX_TOOL_PATH" "$NIX_PKG_CONFIG_PATH" "$NIX_INCS" "$NIX_LDFS" > sysroot.env
        fi
        tar -cf - "$@" | zstd -T0 -3 -o "$package/layer.tar.zst" -f
        python3 - "$package" "$component" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
root = Path(sys.argv[1])
h = hashlib.sha256()
with (root / 'layer.tar.zst').open('rb') as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(chunk)
(root / 'metadata.json').write_text(json.dumps({'schema': 1, 'component': sys.argv[2],
    'sha256': h.hexdigest(), 'source': os.environ['GITHUB_SHA']}, indent=2) + '\n')
PY
        if [[ "$component" == core || "$component" == assembled || "$component" == runtime ]]; then
            key="${GITHUB_SHA}-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
        else
            key=$(python3 tools/build/cache_key.py "$component")
        fi
        reference="$registry/$component:$key"
        (cd "$package" && oras push "$reference" \
            --artifact-type application/vnd.winecx.build.v1 \
            layer.tar.zst:application/vnd.winecx.layer.v1.tar+zstd \
            metadata.json:application/vnd.winecx.metadata.v1+json)
        digest=$(oras resolve "$reference")
        echo "ref=$registry/$component@$digest" >> "$GITHUB_OUTPUT"
        printf 'OCI %s: `%s/%s@%s`\n\n' "$component" "$registry" "$component" "$digest" >> "$GITHUB_STEP_SUMMARY"
        [ "$component" != sysroot ] || rm sysroot-closure.nar
        ;;
    *) echo "Unknown OCI command: $command" >&2; exit 1 ;;
esac
