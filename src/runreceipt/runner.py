from __future__ import annotations

import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .capture import ReceiptError, environment, files, git_state, interpreter_info
from .store import initialize, key_id, save


def record(
    root: Path,
    python: str,
    argv: list[str],
    tracked: list[str],
    env: list[str],
    excludes: list[str],
) -> tuple[dict, Path]:
    root = root.resolve()
    if not root.is_dir():
        raise ReceiptError("project root must be an existing directory")
    if not argv:
        raise ReceiptError(
            "provide a Python script or interpreter arguments after '--'"
        )
    runs, key = initialize(root)
    executable, info = interpreter_info(python, root)
    inputs = {
        **info,
        "files": files(root, tracked, excludes),
        "environment": environment(env, key),
        "git": git_state(root),
    }
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    start = time.monotonic()
    interrupted = False
    try:
        process = subprocess.Popen([executable, *argv], cwd=root)
    except OSError as error:
        raise ReceiptError("could not launch the selected Python command") from error
    try:
        child_exit = process.wait()
    except KeyboardInterrupt:
        interrupted = True
        process.terminate()
        try:
            child_exit = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            child_exit = process.wait()
    elapsed = round((time.monotonic() - start) * 1000)
    exit_code = (
        130 if interrupted else child_exit if child_exit >= 0 else 128 - child_exit
    )
    errors = []
    try:
        after = files(root, tracked, excludes, allow_missing=True)
    except ReceiptError as error:
        errors.append(str(error))
        after = {}
    receipt = {
        "schema_version": 1,
        "id": uuid.uuid4().hex[:12],
        "started_at": started_at,
        "command": [executable, *argv],
        "root": str(root),
        "duration_ms": elapsed,
        "exit_code": exit_code,
        "child_exit_code": child_exit,
        "interrupted": interrupted,
        "key_id": key_id(key),
        "selection": {"track": sorted(set(tracked)), "exclude": sorted(set(excludes))},
        "inputs": inputs,
        "files_after": after,
        "errors": errors,
    }
    return receipt, save(runs, receipt)
