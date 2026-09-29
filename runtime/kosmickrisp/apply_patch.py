#!/usr/bin/env python3
"""Apply the pinned Mesa patch set, accepting only pristine or exactly patched trees."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile


def apply(source, patch, revision, sha256):
    source, patch = Path(source).resolve(), Path(patch).resolve()
    if hashlib.sha256(patch.read_bytes()).hexdigest() != sha256:
        raise RuntimeError("Mesa patch checksum mismatch")

    def git(*args, env=None, check=True):
        return subprocess.run(["git", "-C", str(source), *args], env=env,
                              check=check, capture_output=True, text=True)

    if git("rev-parse", "HEAD").stdout.strip() != revision:
        raise RuntimeError("Mesa base revision mismatch")
    if git("diff", "--cached", "--quiet", "HEAD", check=False).returncode:
        raise RuntimeError("Mesa has staged changes; refusing to overwrite them")
    if git("ls-files", "--others", "--exclude-standard").stdout:
        raise RuntimeError("Mesa has untracked files; refusing to patch")
    with tempfile.TemporaryDirectory(prefix="kosmickrisp-index-") as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
        git("read-tree", "HEAD", env=env)
        git("apply", "--cached", str(patch), env=env)
        if not git("diff", "--quiet", env=env, check=False).returncode:
            return "already applied"
        if git("diff", "--quiet", check=False).returncode:
            raise RuntimeError("Mesa has incompatible local changes; refusing to overwrite them")
        git("apply", "--check", str(patch))
        git("apply", str(patch))
        git("diff", "--exit-code", env=env)
    return "applied"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("patch")
    parser.add_argument("revision")
    parser.add_argument("sha256")
    args = parser.parse_args()
    try:
        print("Mesa patch set: " + apply(args.source, args.patch, args.revision, args.sha256))
    except (RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
