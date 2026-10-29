from __future__ import annotations

import json
from html import escape


def printable(value: object) -> str:
    if value is None:
        return "-"
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def text_report(result: dict) -> str:
    lines = [f"{result['before']} -> {result['after']}"]
    for change in result["changes"]:
        if change["area"] == "files":
            state = (
                "added"
                if change["before"] is None
                else "removed"
                if change["after"] is None
                else "modified"
            )
            lines.append(f"files: {change['name']!a} {state}")
        else:
            lines.append(
                f"{change['area']}: {change['name']!a}: {printable(change['before'])} -> {printable(change['after'])}"
            )
    if result["selection_changed"]:
        lines.append(
            "File selection changed; added/removed files may reflect changed coverage."
        )
    for name in result["environment_not_comparable"]:
        lines.append(
            f"environment: {name!a}: values cannot be compared because receipt keys differ"
        )
    for label, mutations in result["mutations"].items():
        if mutations is None:
            lines.append(f"{label} run: final file snapshot is incomplete")
        else:
            for item in mutations:
                lines.append(f"{label} run changed tracked file: {item['name']!a}")
    for label, errors in result["capture_errors"].items():
        for error in errors:
            lines.append(f"{label} capture error: {ascii(error)}")
    lines.append(
        f"{len(result['changes'])} recorded difference(s). Changes are evidence, not proof of cause."
    )
    return "\n".join(lines) + "\n"


def html_report(result: dict) -> str:
    rows = []
    for change in result["changes"]:
        cells = [
            change["area"],
            change["name"],
            printable(change["before"]),
            printable(change["after"]),
        ]
        if change["area"] == "files":
            cells[2:] = [
                "not observed"
                if change[side] is None
                else "sha256: " + change[side][:12]
                for side in ("before", "after")
            ]
        rows.append(
            "<tr>"
            + "".join(f"<td>{escape(str(cell))}</td>" for cell in cells)
            + "</tr>"
        )
    if not rows:
        rows.append(
            '<tr><td colspan="4">No differences in the recorded starting inputs or exit codes.</td></tr>'
        )
    notes = []
    if result["selection_changed"]:
        notes.append(
            "File selection changed. Added or removed files can reflect changed coverage."
        )
    for name in result["environment_not_comparable"]:
        notes.append(
            f"Environment values cannot be compared for {name}: the receipts use different keys."
        )
    mutation_rows = []
    for label, mutations in result["mutations"].items():
        if mutations is None:
            notes.append(f"The {label} run has an incomplete final file snapshot.")
        else:
            for item in mutations:
                state = (
                    "added"
                    if item["before"] is None
                    else "removed"
                    if item["after"] is None
                    else "modified"
                )
                mutation_rows.append(
                    f"<tr><td>{escape(label)}</td><td>{escape(item['name'])}</td><td>{state}</td></tr>"
                )
    for label, errors in result["capture_errors"].items():
        notes.extend(f"{label} capture: {error}" for error in errors)
    note_html = (
        "".join(f"<li>{escape(note)}</li>" for note in notes)
        or "<li>Both captures are complete and their environment fingerprints are comparable.</li>"
    )
    mutation_empty = (
        '<tr><td colspan="3">Final file comparison is incomplete. See capture notes.</td></tr>'
        if any(value is None for value in result["mutations"].values())
        else '<tr><td colspan="3">No final content changes in tracked files.</td></tr>'
    )
    return (
        """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>Run comparison · runreceipt</title>
<style>
:root{color-scheme:light;--ink:#192b37;--muted:#526775;--line:#dce4e8;--accent:#087f73}
*{box-sizing:border-box}body{margin:0;background:#f4f7f8;color:var(--ink);font:15px/1.6 system-ui,sans-serif}
main{max-width:1120px;margin:48px auto;padding:0 24px}.eyebrow{color:var(--accent);font-size:12px;letter-spacing:.15em;text-transform:uppercase;font-weight:700}
h1{font-size:40px;line-height:1.15;letter-spacing:-.04em;margin:12px 0}h2{font-size:20px;margin:0 0 16px}.intro{color:var(--muted);max-width:720px}
.cards{display:flex;gap:16px;margin:28px 0;flex-wrap:wrap}.card{background:white;border:1px solid var(--line);border-radius:12px;padding:18px 24px;flex:1;min-width:220px}.card strong{font-size:clamp(20px,2.5vw,27px);display:block;overflow-wrap:anywhere}.card span{color:var(--muted)}
section{background:white;border:1px solid var(--line);border-radius:14px;padding:24px;margin:20px 0}.scroll{overflow:auto}table{width:100%;min-width:580px;table-layout:fixed;border-collapse:collapse}th:nth-child(1),th:nth-child(2){width:20%}th{text-align:left;background:#f4f7f8;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}td,th{padding:12px;border-bottom:1px solid var(--line);vertical-align:top}td{overflow-wrap:anywhere;white-space:pre-wrap}td:nth-child(n+2){font:12px/1.6 ui-monospace,monospace}footer{color:var(--muted);font-size:13px;margin:24px 0}li{margin:8px 0}@media(max-width:600px){main{margin:24px auto;padding:0 14px}h1{font-size:32px}section{padding:16px}}
</style><main><div class="eyebrow">runreceipt / comparison</div><h1>What changed between runs?</h1>
<p class="intro">Recorded differences in the inputs and outcome of two Python commands. A difference is a lead to investigate, not proof that it caused the result.</p>
"""
        + f"""<div class="cards"><div class="card"><span>Earlier run</span><strong>{escape(result["before"])}</strong></div><div class="card"><span>Later run</span><strong>{escape(result["after"])}</strong></div><div class="card"><span>Recorded differences</span><strong>{len(result["changes"])}</strong></div></div>
<section><h2>Starting inputs and outcome</h2><div class="scroll"><table><thead><tr><th>Area</th><th>Name</th><th>Earlier</th><th>Later</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>
<section><h2>Files changed during execution</h2><div class="scroll"><table><thead><tr><th>Run</th><th>File</th><th>Change</th></tr></thead><tbody>{"".join(mutation_rows) or mutation_empty}</tbody></table></div></section>
<section><h2>Capture notes</h2><ul>{note_html}</ul></section><footer>Generated locally by runreceipt. No scripts, external fonts or network resources are needed to view this report.</footer></main></html>"""
    )
