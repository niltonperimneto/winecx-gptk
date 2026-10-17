#!/bin/bash
set -euo pipefail

version=$("$1" --version)
if [[ "$version" =~ ^wine-([0-9]+\.[0-9]+(\.[0-9]+)?(-[[:alnum:].]+)?)$ ]]; then
  printf '%s\n' "${BASH_REMATCH[1]}"
else
  echo "::error::unexpected assembled Wine version: $version" >&2
  exit 1
fi
