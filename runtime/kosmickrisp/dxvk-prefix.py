#!/usr/bin/env python3
"""Install/restore the runtime's upstream DXVK DLLs in one Wine prefix."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil


NAMES = ("d3d8.dll", "d3d9.dll", "d3d10core.dll", "d3d11.dll", "dxgi.dll")
LANES = (("system32", "x64"), ("syswow64", "x32"))
RECEIPT = ".winecx-kosmickrisp-dxvk.json"
BACKUP = ".winecx-kosmickrisp-dxvk-backup"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paths(prefix, payload):
    if prefix.is_symlink() or not (prefix / "drive_c/windows").is_dir():
        raise ValueError("expected an initialized, non-symlink Wine prefix")
    for lane, arch in LANES:
        directory = prefix / "drive_c/windows" / lane
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"unsafe or missing Wine directory: {directory}")
        for name in NAMES:
            source = payload / arch / name
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"missing DXVK DLL: {source}")
            yield lane, name, source, directory / name


def restore_copy(source, destination):
    temporary = destination.with_name("." + destination.name + ".kk-restore")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    if source.is_symlink():
        temporary.symlink_to(os.readlink(source))
    else:
        shutil.copy2(source, temporary)
    temporary.replace(destination)


def install(prefix, payload):
    entries = list(paths(prefix, payload))
    receipt, backup = prefix / RECEIPT, prefix / BACKUP
    if receipt.exists():
        data = json.loads(receipt.read_text())
        if data.get("version") != "3.1.1" or any(
            sha256(target) != data["files"][f"{lane}/{name}"]["installed_sha256"]
            for lane, name, _, target in entries
        ):
            raise ValueError("existing DXVK installation differs; refusing to overwrite it")
        return "already installed"
    if backup.exists():
        raise ValueError("uncommitted DXVK backup exists; refusing to overwrite it")
    backup.mkdir()
    files = {}
    changed = []
    try:
        for lane, name, source, target in entries:
            original = target.exists() or target.is_symlink()
            saved = backup / lane / name
            saved.parent.mkdir(exist_ok=True)
            if original:
                if target.is_symlink():
                    saved.symlink_to(os.readlink(target))
                else:
                    shutil.copy2(target, saved)
            files[f"{lane}/{name}"] = {"had_original": original,
                                      "installed_sha256": sha256(source)}
            restore_copy(source, target)
            changed.append((target, saved, original))
        temporary = receipt.with_name(RECEIPT + ".tmp")
        temporary.write_text(json.dumps({"version": "3.1.1", "files": files}, indent=2) + "\n")
        temporary.replace(receipt)
    except Exception:
        for target, saved, original in reversed(changed):
            if original:
                restore_copy(saved, target)
            else:
                target.unlink(missing_ok=True)
        shutil.rmtree(backup)
        raise
    return "installed"


def restore(prefix, payload):
    entries = list(paths(prefix, payload))
    receipt, backup = prefix / RECEIPT, prefix / BACKUP
    if not receipt.is_file() or not backup.is_dir():
        raise ValueError("no managed DXVK installation to restore")
    data = json.loads(receipt.read_text())
    if data.get("version") != "3.1.1":
        raise ValueError("unsupported DXVK receipt")
    for lane, name, _, target in entries:
        entry = data["files"][f"{lane}/{name}"]
        if target.is_symlink() or not target.is_file() or sha256(target) != entry["installed_sha256"]:
            raise ValueError(f"DXVK DLL changed since installation: {target}")
        if entry["had_original"] and not ((backup / lane / name).exists() or
                                          (backup / lane / name).is_symlink()):
            raise ValueError(f"missing original DLL backup: {lane}/{name}")
    for lane, name, _, target in entries:
        entry = data["files"][f"{lane}/{name}"]
        if entry["had_original"]:
            restore_copy(backup / lane / name, target)
        else:
            target.unlink()
    receipt.unlink()
    shutil.rmtree(backup)
    return "restored"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("install", "restore"))
    parser.add_argument("prefix", type=Path)
    parser.add_argument("payload", type=Path)
    args = parser.parse_args()
    prefix, payload = args.prefix.absolute(), args.payload.resolve()
    print(install(prefix, payload) if args.operation == "install" else restore(prefix, payload))


if __name__ == "__main__":
    main()
