"""Safe project source materialization from directories, ZIP files or Git URLs."""

from __future__ import annotations

import shutil
import stat
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


def materialize_source(source: str | Path, destination: str | Path) -> tuple[Path, str]:
    source_text = str(source)
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    if source_text.startswith(("https://", "ssh://", "git@")):
        parsed_source = source_text.replace("git@", "ssh://git@", 1) if source_text.startswith("git@") else source_text
        parsed = urlsplit(parsed_source)
        if parsed.scheme not in {"https", "ssh"} or not parsed.hostname or parsed.password is not None or (parsed.scheme == "https" and parsed.username is not None):
            shutil.rmtree(destination, ignore_errors=True)
            raise ValueError("Git URLs must use HTTPS or SSH and cannot embed a password/token.")
        try:
            result = subprocess.run(["git", "clone", "--depth", "1", "--no-recurse-submodules", source_text, str(destination)], check=False, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f"Unable to clone repository: {error}") from error
        if result.returncode:
            shutil.rmtree(destination, ignore_errors=True)
            # Git diagnostics can echo an authenticated remote URL. Keep the
            # failure useful while never persisting its potentially secret URL.
            raise RuntimeError("Git clone failed. Check the repository URL, credentials and Git diagnostics locally.")
        return destination, "git"
    path = Path(source).expanduser().resolve()
    if path.is_dir():
        destination.rmdir()
        return path, "directory"
    if not path.is_file() or path.suffix.lower() != ".zip":
        shutil.rmtree(destination, ignore_errors=True)
        raise ValueError("Source must be a local directory, .zip archive, or HTTPS/SSH Git URL.")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 100_000 or sum(member.file_size for member in members) > 1_000_000_000:
            raise ValueError("ZIP archive exceeds the 100,000-file / 1 GB extraction limit.")
        for member in members:
            name = member.filename.replace("\\", "/")
            parsed = PurePosixPath(name)
            mode = member.external_attr >> 16
            if parsed.is_absolute() or ".." in parsed.parts or (len(parsed.parts) and ":" in parsed.parts[0]):
                raise ValueError(f"Unsafe ZIP member path rejected: {member.filename}")
            if stat.S_ISLNK(mode):
                raise ValueError(f"ZIP symlink is not accepted: {member.filename}")
        archive.extractall(destination)
    entries = [p for p in destination.iterdir() if p.name != "__MACOSX"]
    root = entries[0] if len(entries) == 1 and entries[0].is_dir() else destination
    return root, "zip"
