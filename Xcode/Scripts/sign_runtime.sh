#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

USAGE="Usage: sign_runtime.sh EXECUTABLE APP_DIRECTORY PROFILE [IDENTITY_SHA1]"
EXECUTABLE="${1:-}"
APP_DIR="${2:-}"
PROFILE="${3:-}"
IDENTITY="${4:-${CODE_SIGN_IDENTITY:-}}"

if [ -z "$EXECUTABLE" ] || [ -z "$APP_DIR" ] || [ -z "$PROFILE" ]; then
    echo "$USAGE" >&2
    echo "Note: If run from Xcode, IDENTITY defaults to CODE_SIGN_IDENTITY." >&2
    exit 1
fi

if [ -z "$IDENTITY" ]; then
    # Look for the first valid codesigning identity
    IDENTITY=$(security find-identity -v -p codesigning | awk -F'"' '/Apple Development|Developer ID/ {print $1}' | awk '{print $2}' | head -n 1)
    if [ -z "$IDENTITY" ]; then
        echo "Error: No codesigning identity specified or found in keychain." >&2
        exit 1
    fi
fi

echo "== Invoking make-wine-app.sh with identity ${IDENTITY}..."
bash "${REPO_ROOT}/arm64/make-wine-app.sh" "${EXECUTABLE}" "${APP_DIR}" "${PROFILE}" "${IDENTITY}" "ntdll.so=../../../ntdll.so"
