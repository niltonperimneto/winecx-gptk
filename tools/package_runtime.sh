#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/build/common.sh"
# Metadata is excluded because the verifier treats these two files as
# the signed envelope. Every other regular file must be declared.
python3 - <<'PY'
import hashlib, json, os

root = "Libraries"
metadata = {"WhiskyWineVersion.plist", "RuntimeManifest.json"}
files = []
for directory, _, names in os.walk(root):
    for name in names:
        path = os.path.join(directory, name)
        relative = os.path.relpath(path, root)
        if relative in metadata or os.path.islink(path) or not os.path.isfile(path):
            continue
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        files.append({
            "path": relative,
            "size": os.path.getsize(path),
            "sha256": digest.hexdigest()
        })
manifest = {"formatVersion": 1, "files": sorted(files, key=lambda item: item["path"])}
with open(os.path.join(root, "RuntimeManifest.json"), "w") as stream:
    json.dump(manifest, stream, indent=2, sort_keys=True)
    stream.write("\n")
PY

# the plist rides alongside the tarball so the publish job, and then
# the mirror in dappermint/Whisky, can read the version without
# decompressing 434MB to reach one file
cp Libraries/WhiskyWineVersion.plist .
cp Libraries/RuntimeManifest.json .
cp Libraries/RuntimeNetworkVerification.txt .
tar -czf Libraries.tar.gz Libraries
shasum -a 256 Libraries.tar.gz | tee Libraries.tar.gz.sha256
# the stock whisky engine v3.1.1 tarball is 332,438,526 bytes and
# carries the same addons, so this is the number to compare against
echo "tarball bytes: $(wc -c < Libraries.tar.gz | tr -d ' ')" | tee -a "$GITHUB_STEP_SUMMARY"
