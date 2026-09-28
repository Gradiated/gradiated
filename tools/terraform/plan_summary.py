"""Render resource actions without publishing plan values or Terraform state."""

import collections
import html
import json
from pathlib import Path
import sys


def code(value):
    text = html.escape(str(value)).replace("`", "&#96;").replace("|", "&#124;")
    return "`" + " ".join(text.split())[:300] + "`"


def action(change):
    actions = change["actions"]
    if "create" in actions and "delete" in actions:
        return "REPLACE"
    if change.get("importing"):
        return "IMPORT / " + ", ".join(actions)
    return ", ".join(actions)


def summarize(directory):
    paths = sorted(directory.rglob("*.json"))
    if not paths:
        raise ValueError("No plan JSON files were produced; refusing an empty preview")

    counts = collections.Counter()
    rows = []
    drift = 0
    for path in paths:
        plan = json.loads(path.read_text())
        if not str(plan.get("format_version", "")).startswith("1."):
            raise ValueError("Unsupported Terraform plan JSON format")
        if plan.get("errored") or plan.get("complete") is False:
            raise ValueError("Incomplete Terraform plan; refusing a success preview")
        unit = code(path.parent.relative_to(directory))
        drift += len(plan.get("resource_drift", []))
        for resource in plan.get("resource_changes", []):
            change = resource["change"]
            moved = resource.get("previous_address")
            if change["actions"] == ["no-op"] and not change.get("importing") and not moved:
                continue
            operation = "MOVE" if moved and change["actions"] == ["no-op"] else action(change)
            counts[operation] += 1
            before, after = change.get("before") or {}, change.get("after") or {}
            unknown = change.get("after_unknown") or {}
            fields = sorted(key for key in before.keys() | after.keys() | unknown.keys()
                            if before.get(key) != after.get(key) or unknown.get(key))
            address = code(resource["address"])
            if moved:
                address = code(moved) + " → " + address
            rows.append(f"| {unit} | {operation} | {address} | {', '.join(map(code, fields)) or '—'} |")
        for name, change in plan.get("output_changes", {}).items():
            if change["actions"] != ["no-op"]:
                counts["output changes"] += 1
                rows.append(f"| {unit} | output {action(change)} | {code(name)} | values omitted |")

    totals = ", ".join(f"{count} {name}" for name, count in sorted(counts.items()))
    lines = [f"**{totals or 'No planned changes'}** across {len(paths)} Terraform units.", ""]
    if drift:
        lines += [f"Refresh detected drift in {drift} resources; inspect the full plan before merging.", ""]
    lines += ["Resource and output values are omitted from this comment. Changed attributes are top-level names.", ""]
    if rows:
        lines += ["| Unit | Action | Resource / output | Changed attributes |", "| --- | --- | --- | --- |"]
        size = sum(len(line) + 1 for line in lines)
        for row in rows:
            if size + len(row) > 50_000:
                lines += ["", "Preview truncated; inspect the full plan for remaining changes."]
                break
            lines.append(row)
            size += len(row) + 1
    return "\n".join(lines)


if __name__ == "__main__":
    print(summarize(Path(sys.argv[1])))
