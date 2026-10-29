from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Change:
    area: str
    name: str
    before: object
    after: object


def mapping_changes(area: str, before: dict, after: dict) -> list[Change]:
    return [
        Change(area, name, before.get(name), after.get(name))
        for name in sorted(before.keys() | after.keys())
        if before.get(name) != after.get(name)
    ]


def file_changes(before: dict, after: dict) -> list[Change]:
    # Sizes are useful context in receipts; content identity is determined by the hash.
    old = {name: value["sha256"] for name, value in before.items()}
    new = {name: value["sha256"] for name, value in after.items()}
    return mapping_changes("files", old, new)


def compare(before: dict, after: dict) -> dict:
    changes = []
    for name in ("command", "selection", "root"):
        if before[name] != after[name]:
            changes.append(Change("capture", name, before[name], after[name]))
    if before["exit_code"] != after["exit_code"]:
        changes.append(
            Change("outcome", "exit_code", before["exit_code"], after["exit_code"])
        )
    left, right = before["inputs"], after["inputs"]
    changes.extend(mapping_changes("python", left["python"], right["python"]))
    changes.extend(mapping_changes("packages", left["packages"], right["packages"]))
    changes.extend(file_changes(left["files"], right["files"]))
    if left.get("git") != right.get("git"):
        changes.append(Change("git", "state", left.get("git"), right.get("git")))
    env_left, env_right = left["environment"], right["environment"]
    incomparable = []
    for name in sorted(env_left.keys() | env_right.keys()):
        a, b = env_left.get(name), env_right.get(name)

        def state(value):
            return (
                "not captured"
                if value is None
                else "set"
                if value["present"]
                else "unset"
            )

        if state(a) != state(b):
            changes.append(Change("environment", name, state(a), state(b)))
        elif a and b and a["present"]:
            if before["key_id"] != after["key_id"]:
                incomparable.append(name)
            elif a["fingerprint"] != b["fingerprint"]:
                changes.append(
                    Change(
                        "environment",
                        name,
                        "set (earlier value)",
                        "set (different value)",
                    )
                )
    mutations = {}
    for label, receipt in (("before", before), ("after", after)):
        # An incomplete final snapshot must never be presented as mass deletion.
        mutations[label] = (
            None
            if receipt["errors"]
            else [
                asdict(change)
                for change in file_changes(
                    receipt["inputs"]["files"], receipt["files_after"]
                )
            ]
        )
    return {
        "before": before["id"],
        "after": after["id"],
        "changes": [asdict(change) for change in changes],
        "environment_not_comparable": incomparable,
        "selection_changed": before["selection"] != after["selection"],
        "mutations": mutations,
        "capture_errors": {"before": before["errors"], "after": after["errors"]},
    }


def has_differences(result: dict) -> bool:
    return bool(
        result["changes"]
        or result["environment_not_comparable"]
        or any(result["mutations"].values())
        or any(result["capture_errors"].values())
    )
