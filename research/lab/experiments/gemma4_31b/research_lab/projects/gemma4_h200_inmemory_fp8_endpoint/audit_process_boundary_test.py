#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import multiprocessing
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent
PARENT_ONLY_MARKER = False


def read_endpoint_contract() -> dict[str, str]:
    source = (PROJECT / "endpoint_entrypoint.py").read_text()
    tree = ast.parse(source)
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "EXPECTED_SOURCE_SHA256"
            for target in node.targets
        )
    )
    return ast.literal_eval(assignment.value)


def observe_parent_patch(pipe) -> None:
    pipe.send(PARENT_ONLY_MARKER)
    pipe.close()


def install_inside_worker(pipe) -> None:
    global PARENT_ONLY_MARKER
    PARENT_ONLY_MARKER = True
    pipe.send(PARENT_ONLY_MARKER)
    pipe.close()


def spawned_value(target) -> bool:
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=target, args=(writer,))
    process.start()
    writer.close()
    value = reader.recv()
    process.join(10)
    assert process.exitcode == 0
    return value


def main() -> None:
    contract = json.loads((PROJECT / "PINNED_SGLANG_AUDIT_CONTRACT.json").read_text())
    assert read_endpoint_contract() == contract["source_sha256"]
    global PARENT_ONLY_MARKER
    PARENT_ONLY_MARKER = True
    assert spawned_value(observe_parent_patch) is False
    assert spawned_value(install_inside_worker) is True
    print(
        json.dumps(
            {
                "contract_bound": True,
                "parent_monkeypatch_survives_spawn": False,
                "scheduler_target_install_survives_spawn": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
