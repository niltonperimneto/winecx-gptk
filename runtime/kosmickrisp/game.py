"""Run a repository-configured, hash-pinned Windows benchmark through the launcher."""
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import urllib.request
import zipfile


def extract_archive(data, destination):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 2 * 1024**3:
            raise ValueError("game archive expands beyond 2 GiB")
        for item in archive.infolist():
            relative = Path(item.filename.replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
                raise ValueError("unsafe game archive path")
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("game archive symlinks are not supported")
            target = destination / relative
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)


def run_game(config_path, launcher, env, output, run_probe):
    config = json.loads(config_path.read_text())
    if config is None:
        return {"status": "blocked", "reason": "no pinned game benchmark configured"}
    try:
        digest = config["archive_sha256"]
        if not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("game archive needs an exact SHA-256")
        if not config["archive_url"].startswith("https://"):
            raise ValueError("game archive URL must use HTTPS")
        for key in ("success_pattern", "driver_pattern", "metric_pattern"):
            if not config[key]:
                raise ValueError(f"missing {key}")
            re.compile(config[key])
        timeout = int(config["timeout_seconds"])
        if not 1 <= timeout <= 600:
            raise ValueError("game timeout must be 1..600 seconds")
        exe = Path(config["executable"])
        if exe.is_absolute() or ".." in exe.parts or ":" in str(exe) or "\\" in str(exe):
            raise ValueError("game executable must be a relative archive path")
        arguments = config.get("arguments", [])
        if not isinstance(arguments, list) or not all(isinstance(x, str) for x in arguments):
            raise ValueError("game arguments must be a list of strings")
        # The runner executes only the exact archive selected in the repository.
        with urllib.request.urlopen(config["archive_url"], timeout=30) as stream:
            data = stream.read(512 * 1024**2 + 1)
        if len(data) > 512 * 1024**2 or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("game archive too large or checksum mismatch")
        destination = output / "game-files"
        destination.mkdir()
        extract_archive(data, destination)
        executable = destination / exe
        if not executable.is_file():
            raise ValueError("game executable absent from archive")
        code, seconds, text = run_probe([str(launcher), str(executable), *arguments], env,
                                       output / "game.log", timeout=timeout, cwd=executable.parent)
        metric = re.search(config["metric_pattern"], text)
        score = float(metric.group(1)) if metric else None
        passed = (code == 0 and re.search(config["success_pattern"], text)
                  and re.search(config["driver_pattern"], text) and score is not None
                  and score >= float(config["minimum_metric"]))
        return {"status": "passed" if passed else "failed", "benchmark": config["name"],
                "archive_sha256": digest, "seconds": seconds, "metric": score,
                "exit_code": code, "reason": "benchmark exit, correctness/backend markers, and performance threshold"}
    except Exception as error:
        return {"status": "failed", "reason": str(error)}
