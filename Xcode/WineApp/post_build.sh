#!/bin/bash
set -euo pipefail

# 1. If an external WINE_LOADER binary is specified, copy it over the target executable
if [ -n "${WINE_LOADER:-}" ] && [ -f "${WINE_LOADER}" ]; then
    echo "== Installing specified Wine loader: ${WINE_LOADER} -> ${TARGET_BUILD_DIR}/${EXECUTABLE_PATH}"
    cp -f "${WINE_LOADER}" "${TARGET_BUILD_DIR}/${EXECUTABLE_PATH}"
    chmod +x "${TARGET_BUILD_DIR}/${EXECUTABLE_PATH}"
fi

# 2. Ensure ntdll.so symlink exists in Contents/MacOS so wine loader can resolve it
MACOS_DIR="${TARGET_BUILD_DIR}/${CONTENTS_FOLDER_PATH}/MacOS"
mkdir -p "${MACOS_DIR}"
if [ ! -e "${MACOS_DIR}/ntdll.so" ]; then
    echo "== Creating ntdll.so symlink -> ../../../ntdll.so"
    ln -sf "../../../ntdll.so" "${MACOS_DIR}/ntdll.so"
fi

# 3. If an explicit provisioning profile path is specified via WINE_PROVISIONING_PROFILE, embed it
if [ -n "${WINE_PROVISIONING_PROFILE:-}" ] && [ -f "${WINE_PROVISIONING_PROFILE}" ]; then
    echo "== Embedding explicit provisioning profile: ${WINE_PROVISIONING_PROFILE}"
    cp -f "${WINE_PROVISIONING_PROFILE}" "${TARGET_BUILD_DIR}/${CONTENTS_FOLDER_PATH}/embedded.provisionprofile"
fi

echo "== WineApp staging complete for ${TARGET_BUILD_DIR}/${WRAPPER_NAME}"
