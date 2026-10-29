from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
from datetime import datetime
from pathlib import Path

from .capture import ReceiptError

_ID = re.compile(r"[a-f0-9]{12}")


def _write_new(path: Path, payload: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
        # Publish complete files without replacing another concurrent writer.
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def initialize(root: Path) -> tuple[Path, bytes]:
    directory = root / ".runreceipt"
    runs = directory / "runs"
    if directory.is_symlink() or runs.is_symlink():
        raise ReceiptError("receipt storage must not be a symlink")
    directory.mkdir(mode=0o700, exist_ok=True)
    runs.mkdir(mode=0o700, exist_ok=True)
    path = directory / "key"
    if path.is_symlink():
        raise ReceiptError("receipt key must not be a symlink")
    try:
        key = secrets.token_bytes(32)
        _write_new(path, key)
    except FileExistsError:
        key = path.read_bytes()
    if len(key) != 32:
        raise ReceiptError(
            "receipt key is invalid; restore the original 32-byte key or use another project directory"
        )
    return runs, key


def key_id(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:16]


def save(runs: Path, receipt: dict) -> Path:
    path = runs / f"{receipt['id']}.json"
    payload = (json.dumps(receipt, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    _write_new(path, payload)
    return path


def resolve(root: Path, reference: str) -> Path:
    if _ID.fullmatch(reference):
        return root / ".runreceipt" / "runs" / f"{reference}.json"
    path = Path(reference)
    return path if path.is_absolute() else root / path


def validate(data: object) -> dict:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ReceiptError("unsupported receipt schema; expected version 1")
    required = {
        "id": str,
        "root": str,
        "started_at": str,
        "command": list,
        "inputs": dict,
        "files_after": dict,
        "errors": list,
        "exit_code": int,
        "duration_ms": int,
        "key_id": str,
        "selection": dict,
    }
    for name, kind in required.items():
        if not isinstance(data.get(name), kind):
            raise ReceiptError(f"invalid receipt field: {name}")
    if not _ID.fullmatch(data["id"]) or not re.fullmatch(
        r"[a-f0-9]{16}", data["key_id"]
    ):
        raise ReceiptError("invalid receipt identifier")
    try:
        timestamp = datetime.fromisoformat(data["started_at"])
        if (
            timestamp.tzinfo is None
            or not data["started_at"].isascii()
            or any(ord(c) < 32 for c in data["started_at"])
        ):
            raise ValueError
    except ValueError as error:
        raise ReceiptError("invalid receipt timestamp") from error
    for name in ("track", "exclude"):
        value = data["selection"].get(name)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ReceiptError("invalid receipt selection")
    if not all(isinstance(error, str) for error in data["errors"]):
        raise ReceiptError("invalid receipt error list")
    inputs = data["inputs"]
    for name in ("python", "packages", "environment", "files"):
        if not isinstance(inputs.get(name), dict):
            raise ReceiptError(f"invalid receipt input: {name}")
    if not all(isinstance(arg, str) for arg in data["command"]):
        raise ReceiptError("receipt command must contain strings")
    for name, value in inputs["packages"].items():
        if (
            not isinstance(name, str)
            or not isinstance(value, list)
            or not all(isinstance(v, str) for v in value)
        ):
            raise ReceiptError("invalid receipt package metadata")
    for entry in (inputs["files"], data["files_after"]):
        for value in entry.values():
            if (
                not isinstance(value, dict)
                or not isinstance(value.get("sha256"), str)
                or not isinstance(value.get("size"), int)
            ):
                raise ReceiptError("invalid receipt file metadata")
    for value in inputs["environment"].values():
        if not isinstance(value, dict) or not isinstance(value.get("present"), bool):
            raise ReceiptError("invalid receipt environment metadata")
        if value["present"] and not isinstance(value.get("fingerprint"), str):
            raise ReceiptError("invalid receipt environment fingerprint")
    return data


def load(path: Path) -> dict:
    try:
        if path.stat().st_size > 20 * 1024 * 1024:
            raise ReceiptError("receipt exceeds the 20 MiB input limit")
        return validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, UnicodeError) as error:
        raise ReceiptError(f"cannot read receipt: {str(path)!a}") from error
