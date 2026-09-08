#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 OUTPUT.tar.gz" >&2
    exit 2
fi

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output=$1
work=$(mktemp -d "${TMPDIR:-/tmp}/d3d11on12-source.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

prefix=relay12/
main_tar=$work/source.tar

git -C "$repo" archive --format=tar --prefix="$prefix" HEAD > "$main_tar"

git -C "$repo" submodule status --recursive | while read -r status path rest; do
    case "$status" in
        -*) echo "submodule is not initialized: $path" >&2; exit 1 ;;
        +*) echo "submodule is not at its recorded revision: $path" >&2; exit 1 ;;
        U*) echo "submodule has unresolved conflicts: $path" >&2; exit 1 ;;
    esac

    sub_tar=$work/$(printf '%s' "$path" | tr / _).tar
    git -C "$repo/$path" archive --format=tar \
        --prefix="$prefix$path/" HEAD > "$sub_tar"
    tar --concatenate --file="$main_tar" "$sub_tar"
done

# -n excludes timestamps and original filenames from the gzip header.
gzip -n -9 < "$main_tar" > "$output"
