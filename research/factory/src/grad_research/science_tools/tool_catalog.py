from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from .common import ScienceToolError, load_json


TIERS = ("base", "route", "reference")
CATEGORIES = (
    "profiling",
    "kernel",
    "model-surgery",
    "endpoint",
    "quality",
    "distributed",
    "build-download",
)
MUTATING_ARGUMENTS = {
    "delete",
    "destroy",
    "install",
    "launch",
    "provision",
    "remove",
    "terminate",
    "uninstall",
}


def default_catalog() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "tool_catalog.json"


def load_catalog(path: str | Path) -> list[dict[str, Any]]:
    value = load_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ScienceToolError("tool catalog must be a schema-version 1 object")
    tools = value.get("tools")
    if not isinstance(tools, list):
        raise ScienceToolError("tool catalog tools must be a list")
    seen: set[str] = set()
    result = []
    for index, raw in enumerate(tools):
        if not isinstance(raw, dict):
            raise ScienceToolError(f"tools[{index}] must be an object")
        identifier = raw.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ScienceToolError(f"tools[{index}].id must be unique text")
        if raw.get("tier") not in TIERS:
            raise ScienceToolError(f"{identifier} has an invalid tier")
        if raw.get("category") not in CATEGORIES:
            raise ScienceToolError(f"{identifier} has an invalid category")
        probe = raw.get("probe")
        if probe is not None:
            if (
                not isinstance(probe, list)
                or not probe
                or any(not isinstance(part, str) or not part for part in probe)
            ):
                raise ScienceToolError(f"{identifier} probe must be an argv list")
            if any(
                part.lower().lstrip("-").split("=", 1)[0]
                in MUTATING_ARGUMENTS
                for part in probe[1:]
            ):
                raise ScienceToolError(f"{identifier} probe is not read-only")
        seen.add(identifier)
        result.append(dict(raw))
    return result


def select_tools(
    tools: Sequence[dict[str, Any]],
    *,
    tier: str | None = None,
    category: str | None = None,
    platform: str | None = None,
) -> list[dict[str, Any]]:
    return [
        tool
        for tool in tools
        if (tier is None or tool["tier"] == tier)
        and (category is None or tool["category"] == category)
        and (
            platform is None
            or platform.lower()
            in {str(item).lower() for item in tool.get("platforms", [])}
        )
    ]


def probe_tool(tool: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    command = tool.get("probe")
    if command is None:
        return {"id": tool["id"], "status": "no-probe"}
    executable = shutil.which(command[0])
    if executable is None:
        return {
            "id": tool["id"],
            "status": "unavailable",
            "command": command,
        }
    try:
        completed = subprocess.run(
            [executable, *command[1:]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "id": tool["id"],
            "status": "probe-failed",
            "command": command,
            "error": str(error),
        }
    return {
        "id": tool["id"],
        "status": "available" if completed.returncode == 0 else "probe-failed",
        "command": command,
        "executable": executable,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="lab-tools",
        description="List and safely probe optional inference-research tools."
    )
    root.add_argument("--catalog", default=str(default_catalog()))
    commands = root.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--tier", choices=TIERS)
    listing.add_argument("--category", choices=CATEGORIES)
    listing.add_argument("--platform")
    listing.add_argument("--json", action="store_true")
    explain = commands.add_parser("explain")
    explain.add_argument("tool")
    probe = commands.add_parser("probe")
    probe.add_argument("tools", nargs="*")
    probe.add_argument("--tier", choices=TIERS)
    probe.add_argument("--category", choices=CATEGORIES)
    probe.add_argument("--platform")
    probe.add_argument("--timeout-seconds", type=float, default=5.0)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        tools = load_catalog(args.catalog)
        if args.command == "explain":
            matches = [tool for tool in tools if tool["id"] == args.tool]
            if not matches:
                raise ScienceToolError(f"unknown tool: {args.tool}")
            result: Any = matches[0]
        else:
            selected = select_tools(
                tools,
                tier=args.tier,
                category=args.category,
                platform=args.platform,
            )
            if args.command == "probe":
                if args.timeout_seconds <= 0 or args.timeout_seconds > 30:
                    raise ScienceToolError("probe timeout must be in (0,30]")
                if args.tools:
                    wanted = set(args.tools)
                    unknown = sorted(wanted - {tool["id"] for tool in tools})
                    if unknown:
                        raise ScienceToolError(
                            f"unknown tools: {', '.join(unknown)}"
                        )
                    selected = [tool for tool in selected if tool["id"] in wanted]
                result = [
                    probe_tool(tool, args.timeout_seconds) for tool in selected
                ]
            elif args.json:
                result = selected
            else:
                for tool in selected:
                    platforms = ",".join(tool.get("platforms", [])) or "-"
                    print(
                        f"{tool['id']}\t{tool['tier']}\t"
                        f"{tool['category']}\t{platforms}\t"
                        f"{tool.get('summary', '')}"
                    )
                return 0
    except (OSError, ScienceToolError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
