#!/usr/bin/env python3
"""Apply the pinned Mesa patch set, accepting only pristine or exactly patched trees."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile


def apply(source, patch, revision, sha256, series=False):
    source, patch = Path(source).resolve(), Path(patch).resolve()
    if hashlib.sha256(patch.read_bytes()).hexdigest() != sha256:
        raise RuntimeError("Mesa patch checksum mismatch")

    patches = [patch]
    if series:
        patches = []
        seen = set()
        for line in patch.read_text().splitlines():
            fields = line.split()
            if len(fields) != 2:
                raise RuntimeError("Invalid Mesa patch series entry")
            digest, name = fields
            if (len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
                    or Path(name).name != name or not name.endswith(".patch")
                    or name in seen):
                raise RuntimeError("Invalid Mesa patch series entry")
            item = patch.parent / name
            if item.resolve().parent != patch.parent:
                raise RuntimeError("Invalid Mesa patch series path")
            if hashlib.sha256(item.read_bytes()).hexdigest() != digest:
                raise RuntimeError("Mesa patch checksum mismatch: " + name)
            patches.append(item)
            seen.add(name)
        if not patches:
            raise RuntimeError("Empty Mesa patch series")

    def git(*args, env=None, check=True, input=None):
        return subprocess.run(["git", "-C", str(source), *args], env=env,
                              check=check, capture_output=True, text=True, input=input)

    if git("rev-parse", "HEAD").stdout.strip() != revision:
        raise RuntimeError("Mesa base revision mismatch")
    if git("diff", "--cached", "--quiet", "HEAD", check=False).returncode:
        raise RuntimeError("Mesa has staged changes; refusing to overwrite them")
    untracked = set(filter(None, git("ls-files", "--others", "--exclude-standard", "-z").stdout.split("\0")))
    with tempfile.TemporaryDirectory(prefix="kosmickrisp-index-") as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
        git("read-tree", "HEAD", env=env)
        for item in patches:
            git("apply", "--cached", str(item), env=env)
        added = set(filter(None, git("diff", "--cached", "--diff-filter=A", "--name-only", "-z", "HEAD", env=env).stdout.split("\0")))
        if untracked - added:
            raise RuntimeError("Mesa has untracked files; refusing to patch")
        if not git("diff", "--quiet", env=env, check=False).returncode:
            return "already applied"
        if untracked:
            raise RuntimeError("Mesa has untracked files; refusing to patch")
        if git("diff", "--quiet", check=False).returncode:
            raise RuntimeError("Mesa has incompatible local changes; refusing to overwrite them")
        combined = git("diff", "--cached", "--binary", "--full-index", "HEAD", env=env).stdout
        git("apply", "--check", "-", input=combined)
        git("apply", "-", input=combined)
        git("diff", "--exit-code", env=env)
    return "applied"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", action="store_true")
    parser.add_argument("source")
    parser.add_argument("patch")
    parser.add_argument("revision")
    parser.add_argument("sha256")
    args = parser.parse_args()
    try:
        print("Mesa patch set: " + apply(args.source, args.patch, args.revision, args.sha256, args.series))
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
