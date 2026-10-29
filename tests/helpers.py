import copy


def sample():
    return copy.deepcopy(
        {
            "schema_version": 1,
            "root": "/project",
            "id": "aaaaaaaaaaaa",
            "started_at": "2026-10-29T09:00:00+00:00",
            "command": ["python", "app.py"],
            "duration_ms": 12,
            "exit_code": 0,
            "child_exit_code": 0,
            "key_id": "a" * 16,
            "selection": {"track": ["src"], "exclude": []},
            "inputs": {
                "python": {"version": "3.10.9"},
                "packages": {"example": ["1.0"]},
                "files": {"src/app.py": {"sha256": "a" * 64, "size": 10}},
                "environment": {"MODE": {"present": True, "fingerprint": "b" * 64}},
                "git": None,
            },
            "files_after": {"src/app.py": {"sha256": "a" * 64, "size": 10}},
            "errors": [],
        }
    )
