from __future__ import annotations

import fnmatch
import hashlib
import hmac
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path


class ReceiptError(Exception):
    """A receipt could not be captured or read reliably."""


_SKIP = {
    ".git",
    ".runreceipt",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "target",
    "build",
    "dist",
}
_COLLECT = r"""
import importlib.metadata, json, platform, re, sys
packages = {}
for item in importlib.metadata.distributions():
    name = item.metadata.get("Name")
    if name:
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        packages.setdefault(normalized, set()).add(item.version)
print(json.dumps({
    "python": {"version": platform.python_version(), "implementation": platform.python_implementation(),
               "executable": sys.executable, "system": platform.system(), "machine": platform.machine(),
               "os_release": platform.release()},
    "packages": {name: sorted(versions) for name, versions in sorted(packages.items())}
}))
"""


def interpreter_info(python: str, root: Path) -> tuple[str, dict]:
    candidate = Path(python)
    if candidate.is_absolute() or "/" in python or "\\" in python:
        executable = str(candidate if candidate.is_absolute() else root / candidate)
    else:
        executable = shutil.which(python) or python
    try:
        result = subprocess.run(
            [executable, "-c", _COLLECT],
            cwd=root,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReceiptError("cannot inspect the selected Python interpreter") from error
    if result.returncode:
        raise ReceiptError(
            "selected Python interpreter could not collect package metadata"
        )
    try:
        data = json.loads(result.stdout)
        if not isinstance(data["python"], dict) or not isinstance(
            data["packages"], dict
        ):
            raise ValueError
    except (ValueError, KeyError, TypeError) as error:
        raise ReceiptError(
            "selected Python interpreter returned invalid metadata"
        ) from error
    return executable, data


def environment(
    names: list[str], key: bytes, values: dict[str, str] | None = None
) -> dict:
    values = os.environ if values is None else values
    result = {}
    for name in sorted(set(names)):
        if not name or "=" in name or "\0" in name:
            raise ReceiptError(
                "environment variable names must be nonempty and contain no '=' or NUL"
            )
        if name in values:
            payload = (
                name.encode("utf-8", "surrogatepass")
                + b"\0"
                + values[name].encode("utf-8", "surrogatepass")
            )
            result[name] = {
                "present": True,
                "fingerprint": hmac.new(key, payload, hashlib.sha256).hexdigest(),
            }
        else:
            result[name] = {"present": False}
    return result


def files(
    root: Path, tracked: list[str], excludes: list[str], *, allow_missing: bool = False
) -> dict:
    found: dict[str, dict] = {}

    def visit(path: Path) -> None:
        relative = path.relative_to(root)
        label = relative.as_posix()
        if any(part in _SKIP for part in relative.parts) or any(
            fnmatch.fnmatchcase(label, pattern) for pattern in excludes
        ):
            return
        try:
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ReceiptError(f"selected input is a symlink: {label!a}")
            if stat.S_ISDIR(mode):
                for child in sorted(path.iterdir()):
                    visit(child)
            elif stat.S_ISREG(mode):
                before = path.stat()
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ino,
                ):
                    raise ReceiptError(
                        f"input changed while it was being hashed: {label!a}"
                    )
                found[label] = {"sha256": digest.hexdigest(), "size": after.st_size}
            else:
                raise ReceiptError(
                    f"selected input is not a regular file or directory: {label!a}"
                )
        except OSError as error:
            raise ReceiptError(f"cannot read selected input: {label!a}") from error

    for selected in sorted(set(tracked)):
        path = Path(selected)
        if path.is_absolute() or ".." in path.parts:
            raise ReceiptError("tracked inputs must be relative paths without '..'")
        path = root / path
        # Reject symlinked ancestors too, including a selected directory itself.
        current = root
        for part in path.relative_to(root).parts:
            current = current / part
            if current.is_symlink():
                raise ReceiptError(f"selected input has a symlink: {selected!a}")
        if not path.exists():
            if allow_missing:
                continue
            raise ReceiptError(f"selected input does not exist: {selected!a}")
        visit(path)
    return dict(sorted(found.items()))


def git_state(root: Path) -> dict | None:
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            timeout=10,
            check=False,
        )

    try:
        commit = git("rev-parse", "--verify", "HEAD")
        if commit.returncode:
            return None
        dirty = git("status", "--porcelain", "-z", "--untracked-files=no")
        if dirty.returncode:
            return None
        return {
            "commit": commit.stdout.decode("ascii").strip(),
            "tracked_dirty": bool(dirty.stdout),
        }
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return None
