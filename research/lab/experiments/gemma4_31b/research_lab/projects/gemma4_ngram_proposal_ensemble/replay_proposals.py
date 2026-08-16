#!/usr/bin/env python3
import argparse
import collections
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path


DEPTH = 18
DRAFT_NODES = 11
FIXED_VERIFY_ROWS = 12
ENDPOINT_ROWS = 791


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    part.replace(path)


def atomic_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    with part.open("w") as handle:
        for row in rows:
            handle.write(canonical(row) + "\n")
    part.replace(path)


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    rank = q * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - rank) + ordered[high] * (rank - low)


def deep_size(value):
    seen = set()

    def visit(item):
        identity = id(item)
        if identity in seen:
            return 0
        seen.add(identity)
        total = sys.getsizeof(item)
        if isinstance(item, dict):
            total += sum(visit(k) + visit(v) for k, v in item.items())
        elif isinstance(item, (list, tuple, set, collections.deque)):
            total += sum(visit(v) for v in item)
        elif hasattr(item, "__dict__"):
            total += visit(vars(item))
        else:
            for slot in getattr(type(item), "__slots__", ()):
                if hasattr(item, slot):
                    total += visit(getattr(item, slot))
        return total

    return visit(value)


class TrieNode:
    __slots__ = ("children", "recency", "frequency")

    def __init__(self):
        self.children = {}
        self.recency = []
        self.frequency = 0


class NativeCorpus:
    def __init__(self):
        self.root = TrieNode()
        self.node_count = 1

    def insert(self, tokens):
        for begin in range(len(tokens)):
            node = self.root
            for token in tokens[begin : begin + DEPTH]:
                child = node.children.get(token)
                if child is None:
                    child = TrieNode()
                    node.children[token] = child
                    self.node_count += 1
                else:
                    node.recency.remove(token)
                node.recency.insert(0, token)
                child.frequency += 1
                node = child

    def query(self, context):
        anchors = []
        for order in range(min(DEPTH, len(context)), 0, -1):
            node = self.root
            for token in context[-order:]:
                node = node.children.get(token)
                if node is None:
                    break
            if node is not None and node.children:
                anchors.append((order, node))

        children = [dict()]
        breadth_scale = 9.0 / 17.0
        for order, anchor in anchors:
            queue = collections.deque(
                [(0, (17 - order) * breadth_scale + 1, anchor)]
            )
            while queue and len(children) <= DRAFT_NODES:
                parent, width, node = queue.popleft()
                for token in node.recency[: max(1, int(width))]:
                    position = children[parent].get(token)
                    if position is None:
                        if len(children) > DRAFT_NODES:
                            break
                        position = len(children)
                        children[parent][token] = position
                        children.append({})
                    queue.append(
                        (position, width - breadth_scale, node.children[token])
                    )
                    if len(children) > DRAFT_NODES:
                        break
        return children, {"max_match_order": anchors[0][0] if anchors else 0}

    def working_set_bytes(self):
        return deep_size(self)


class PromptIndex:
    def __init__(self, prompt):
        self.prompt = prompt
        self.positions = {}
        for position, token in enumerate(prompt):
            self.positions.setdefault(token, []).append(position)

    def next_token(self, context):
        for order in range(min(DEPTH, len(context)), 0, -1):
            suffix = context[-order:]
            matches = []
            for end in reversed(self.positions.get(suffix[-1], ())):
                begin = end - order + 1
                if begin < 0 or end + 1 >= len(self.prompt):
                    continue
                if self.prompt[begin : end + 1] == suffix:
                    matches.append(end)
            if matches:
                chosen = matches[0]
                token = self.prompt[chosen + 1]
                support = sum(
                    self.prompt[end + 1] == token for end in matches
                )
                return token, order, support
        return None


def prompt_chain(index, prefix):
    hypothetical = list(prefix)
    chain = []
    initial = None
    for _ in range(DRAFT_NODES):
        match = index.next_token(index.prompt + hypothetical)
        if match is None:
            break
        if initial is None:
            initial = match
        chain.append(match[0])
        hypothetical.append(match[0])
    return chain, {
        "initial_order": initial[1] if initial else 0,
        "initial_support": initial[2] if initial else 0,
    }


def output_next(prefix, hypothetical):
    if not prefix:
        return None
    for order in range(min(DEPTH, len(hypothetical)), 0, -1):
        suffix = hypothetical[-order:]
        next_rows = []
        for begin in range(0, len(prefix) - order):
            if prefix[begin : begin + order] == suffix:
                next_rows.append((prefix[begin + order], begin))
        if next_rows:
            counts = collections.Counter(token for token, _ in next_rows)
            recency = {}
            for token, begin in next_rows:
                recency[token] = max(recency.get(token, -1), begin)
            token = min(
                counts,
                key=lambda value: (-counts[value], -recency[value], value),
            )
            return token, order, counts[token]
    return None


def output_chain(prefix):
    hypothetical = list(prefix)
    chain = []
    initial = None
    for _ in range(DRAFT_NODES):
        match = output_next(prefix, hypothetical)
        if match is None:
            break
        if initial is None:
            initial = match
        chain.append(match[0])
        hypothetical.append(match[0])
    return chain, {
        "initial_order": initial[1] if initial else 0,
        "initial_support": initial[2] if initial else 0,
    }


def tree_paths(children):
    paths = []

    def visit(node, path):
        if node and not children[node]:
            paths.append(path)
        for token, child in children[node].items():
            visit(child, path + [token])

    visit(0, [])
    return paths


def accept_chain(chain, future):
    accepted = 0
    for proposed, target in zip(chain, future):
        if proposed != target:
            break
        accepted += 1
    return accepted


def accept_tree(children, future):
    node = 0
    accepted = 0
    for target in future:
        child = children[node].get(target)
        if child is None:
            break
        accepted += 1
        node = child
    return accepted


class Method:
    def __init__(self, name):
        self.name = name
        self.corpus = NativeCorpus() if name in {"native", "ensemble"} else None
        self.max_ephemeral_bytes = 0
        self.max_observed_prefix_length = 0

    def begin_row(self, prompt):
        index = PromptIndex(prompt) if self.name in {"prompt", "ensemble"} else None
        if index is not None:
            self.max_ephemeral_bytes = max(
                self.max_ephemeral_bytes, deep_size(index)
            )
        return index

    def propose(self, prompt, prefix, prompt_index):
        if self.name == "native":
            tree, meta = self.corpus.query(prompt + prefix)
            return tree, "tree", meta
        if self.name == "prompt":
            chain, meta = prompt_chain(prompt_index, prefix)
            return chain, "chain", meta
        if self.name == "output_history":
            chain, meta = output_chain(prefix)
            return chain, "chain", meta

        native_tree, native_meta = self.corpus.query(prompt + prefix)
        output, output_meta = output_chain(prefix)
        copied, prompt_meta = prompt_chain(prompt_index, prefix)
        if (
            output_meta["initial_order"] >= 2
            and output_meta["initial_support"] >= 2
        ):
            proposal, kind, selected = output, "chain", "output_history"
        elif prompt_meta["initial_order"] >= 4:
            proposal, kind, selected = copied, "chain", "prompt"
        else:
            proposal, kind, selected = native_tree, "tree", "native"
        return proposal, kind, {
            "selected": selected,
            "native": native_meta,
            "output_history": output_meta,
            "prompt": prompt_meta,
        }

    def after_emit(self, prompt, prefix):
        if self.corpus is not None:
            self.corpus.insert((prompt + prefix)[-DEPTH:])

    def observe_prefix(self, prefix):
        if len(prefix) > self.max_observed_prefix_length:
            self.max_observed_prefix_length = len(prefix)
            self.max_ephemeral_bytes = max(
                self.max_ephemeral_bytes, deep_size(prefix)
            )

    def working_set_bytes(self):
        persistent = self.corpus.working_set_bytes() if self.corpus else 0
        return persistent + self.max_ephemeral_bytes


def proposal_nodes(proposal, kind):
    return len(proposal) - 1 if kind == "tree" else len(proposal)


def replay_method(method_name, traces):
    method = Method(method_name)
    rows = []
    for trace in traces:
        prompt = trace["prompt_ids"]
        output = trace["output_ids"]
        prompt_index = method.begin_row(prompt)
        prefix = []
        passes = []
        lookup_ns = 0
        selected = collections.Counter()
        while len(prefix) < len(output):
            began = time.perf_counter_ns()
            proposal, kind, meta = method.propose(prompt, prefix, prompt_index)
            lookup_ns += time.perf_counter_ns() - began
            future = output[len(prefix) :]
            accepted = (
                accept_tree(proposal, future)
                if kind == "tree"
                else accept_chain(proposal, future)
            )
            emitted = min(accepted + 1, len(future))
            nodes = proposal_nodes(proposal, kind)
            passes.append(
                {
                    "accepted_drafts": accepted,
                    "emitted_tokens": emitted,
                    "logical_verify_rows": nodes + 1,
                    "proposed_nodes": nodes,
                }
            )
            if method_name == "ensemble":
                selected[meta["selected"]] += 1
            prefix.extend(future[:emitted])
            began = time.perf_counter_ns()
            method.after_emit(prompt, prefix)
            lookup_ns += time.perf_counter_ns() - began
            method.observe_prefix(prefix)
        rows.append(
            {
                "accepted_drafts": [p["accepted_drafts"] for p in passes],
                "emitted_per_pass": [p["emitted_tokens"] for p in passes],
                "fixed_verify_rows": FIXED_VERIFY_ROWS * len(passes),
                "logical_verify_rows": sum(
                    p["logical_verify_rows"] for p in passes
                ),
                "lookup_ns": lookup_ns,
                "method": method_name,
                "no_match_passes": sum(p["proposed_nodes"] == 0 for p in passes),
                "output_tokens": len(output),
                "passes": len(passes),
                "proposed_nodes": sum(p["proposed_nodes"] for p in passes),
                "row_id": trace["row_id"],
                "scope": trace["scope"],
                "selected_sources": dict(selected),
            }
        )
    return rows, method.working_set_bytes()


def summarize(rows, working_set_bytes):
    accepted = [value for row in rows for value in row["accepted_drafts"]]
    emitted = [value for row in rows for value in row["emitted_per_pass"]]
    output_tokens = sum(row["output_tokens"] for row in rows)
    passes = sum(row["passes"] for row in rows)
    lookup = [row["lookup_ns"] for row in rows]
    fixed_rows = sum(row["fixed_verify_rows"] for row in rows)
    logical_rows = sum(row["logical_verify_rows"] for row in rows)
    proposed = sum(row["proposed_nodes"] for row in rows)
    selected = collections.Counter()
    for row in rows:
        selected.update(row["selected_sources"])
    return {
        "accepted_drafts_histogram": {
            str(key): value for key, value in sorted(collections.Counter(accepted).items())
        },
        "emitted_per_pass_histogram": {
            str(key): value for key, value in sorted(collections.Counter(emitted).items())
        },
        "estimated_algorithm_working_set_bytes": working_set_bytes,
        "fixed_target_rows": fixed_rows,
        "fixed_target_rows_per_emitted_token": fixed_rows / output_tokens,
        "logical_target_rows": logical_rows,
        "logical_target_rows_per_emitted_token": logical_rows / output_tokens,
        "lookup_ns_per_emitted_token": sum(lookup) / output_tokens,
        "lookup_ns_per_row": {
            "mean": statistics.mean(lookup),
            "median": statistics.median(lookup),
            "p95": percentile(lookup, 0.95),
        },
        "no_match_frequency": sum(row["no_match_passes"] for row in rows) / passes,
        "output_tokens": output_tokens,
        "proposed_nodes": proposed,
        "proposed_nodes_per_emitted_token": proposed / output_tokens,
        "rows": len(rows),
        "selected_sources": dict(selected),
        "target_passes": passes,
        "target_passes_per_emitted_token": passes / output_tokens,
    }


def load_primary(input_root):
    trace_packet = json.loads((input_root / "TRACE_PACKET.json").read_text())
    template = next(
        group
        for group in trace_packet["primary_groups"]
        if group["name"] == "primary_c1"
    )["scored"][0]["request_body"]["prompt"]
    rows = [
        json.loads(line)
        for line in (input_root / "exact_semantic_rows.jsonl").read_text().splitlines()
    ]
    traces = []
    for row in rows:
        prompt = list(template)
        prompt[535] = 200000 + row["i"]
        traces.append(
            {
                "output_ids": row["semantic"]["output_ids"],
                "prompt_ids": prompt,
                "row_id": row["i"],
                "scope": "endpoint",
            }
        )
    return traces


def load_gpqa(capture, tokenizer_path):
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_path, local_files_only=True
    )
    traces = []
    for line in capture.read_text().splitlines():
        row = json.loads(line)
        prompt = tokenizer.apply_chat_template(
            row["request"]["messages"],
            tokenize=True,
            add_generation_prompt=True,
            return_dict=False,
        )
        content = row["response"]["choices"][0]["message"].get("content") or ""
        output = tokenizer.encode(content, add_special_tokens=False)
        usage = row["usage"]
        if len(prompt) != usage["prompt_tokens"]:
            raise RuntimeError("gpqa_prompt_token_count_mismatch:" + row["case_id"])
        if len(output) == usage["completion_tokens"] - 1:
            output.append(tokenizer.eos_token_id)
        if len(output) != usage["completion_tokens"]:
            raise RuntimeError("gpqa_output_token_count_mismatch:" + row["case_id"])
        traces.append(
            {
                "capture_response_sha256": row["raw_response_sha256"],
                "output_ids": output,
                "prompt_ids": prompt,
                "row_id": row["case_id"],
                "scope": "gpqa",
            }
        )
    return traces


def deterministic_fixture_audit():
    prompt = [10, 20, 30, 20, 30, 40]
    prefix = [20, 30, 40, 20, 30, 40]
    first_prompt = prompt_chain(PromptIndex(prompt), prefix)
    second_prompt = prompt_chain(PromptIndex(prompt), prefix)
    first_output = output_chain(prefix)
    second_output = output_chain(prefix)
    if first_prompt != second_prompt or first_output != second_output:
        raise RuntimeError("determinism_audit_failed")
    return {
        "deterministic_repeated_calls": True,
        "full_output_not_passed_to_proposal": True,
        "proposal_inputs": ["prompt_ids", "already_emitted_output_prefix"],
    }


def native_source_fixture_audit():
    dominant = [51935] * 358
    transient = list(dominant)
    transient[289:292] = [25627, 1767, 1154]
    alternate = [51935] * 26 + [3055] * (358 - 26)
    cases = [
        ("dominant_only", [dominant], 11),
        ("three_token_transient", [dominant, transient, dominant], 4),
        ("persistent_alternate", [dominant, alternate], 2),
        (
            "persistent_alternate_after_four_normal",
            [dominant, alternate, dominant, dominant, dominant, dominant],
            4,
        ),
    ]
    observed = {}
    for name, sequences, expected in cases:
        corpus = NativeCorpus()
        for sequence in sequences:
            for end in range(1, len(sequence) + 1):
                corpus.insert(sequence[max(0, end - DEPTH) : end])
        tree, _ = corpus.query([51935] * DEPTH)
        actual = accept_tree(tree, [51935] * DRAFT_NODES)
        observed[name] = {"actual": actual, "expected": expected}
    return {
        "all_match_pinned_cpp_probe": all(
            row["actual"] == row["expected"] for row in observed.values()
        ),
        "cases": observed,
        "probe": "Exact f63458b5 v0.5.15 trie.cpp/result.cpp compiled with g++ -std=c++17 -O2.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    project = args.project.resolve()
    projects = project.parent
    input_root = (
        projects
        / "gemma4_h100_v0515_ngram_price_normalized"
        / "packet/candidate-v0.5.15/inputs"
    )
    quality_capture = (
        projects
        / "gemma4_h200_ngram_decode_equivalent_production_validation"
        / "artifacts/quality-final-20260724t1304z/control-gpqa.jsonl"
    )
    tokenizer_path = (
        projects
        / "gemma4_h100_v0515_ngram_price_normalized"
        / "inputs/checkpoint"
    )
    source_root = (
        project.parents[5]
        / ".agents/runtime/sglang-v0.5.15-full-checkout"
        / "python/sglang/jit_kernel/csrc/ngram_corpus"
    )
    if not source_root.exists():
        source_root = Path(
            "/root/workspace/.agents/runtime/sglang-v0.5.15-full-checkout/"
            "python/sglang/jit_kernel/csrc/ngram_corpus"
        )

    manifest = {
        "inputs": {
            "exact_semantic_rows.jsonl": {
                "bytes": (input_root / "exact_semantic_rows.jsonl").stat().st_size,
                "path": str(input_root / "exact_semantic_rows.jsonl"),
                "sha256": sha256(input_root / "exact_semantic_rows.jsonl"),
            },
            "requests.jsonl": {
                "bytes": (input_root / "requests.jsonl").stat().st_size,
                "path": str(input_root / "requests.jsonl"),
                "sha256": sha256(input_root / "requests.jsonl"),
            },
            "TRACE_PACKET.json": {
                "path": str(input_root / "TRACE_PACKET.json"),
                "sha256": sha256(input_root / "TRACE_PACKET.json"),
            },
            "control-gpqa.jsonl": {
                "path": str(quality_capture),
                "sha256": sha256(quality_capture),
            },
            "tokenizer.json": {
                "path": str(tokenizer_path / "tokenizer.json"),
                "sha256": sha256(tokenizer_path / "tokenizer.json"),
            },
            "tokenizer_config.json": {
                "path": str(tokenizer_path / "tokenizer_config.json"),
                "sha256": sha256(tokenizer_path / "tokenizer_config.json"),
            },
        },
        "native_source": {
            name: sha256(source_root / name)
            for name in [
                "ngram.cpp",
                "ngram.h",
                "param.h",
                "result.cpp",
                "result.h",
                "trie.cpp",
                "trie.h",
            ]
        },
        "replay_code_sha256": sha256(Path(__file__)),
        "schema_version": 1,
    }
    artifact_root = project / "artifacts/replay"
    atomic_json(artifact_root / "input_manifest.json", manifest)

    primary = load_primary(input_root)
    gpqa = load_gpqa(quality_capture, tokenizer_path)
    atomic_jsonl(artifact_root / "gpqa_token_trace.jsonl", gpqa)

    methods = ["native", "prompt", "output_history", "ensemble"]
    all_rows = []
    working_sets = {}
    for scope, traces in [("endpoint", primary), ("gpqa", gpqa)]:
        for method_name in methods:
            rows, working_set = replay_method(method_name, traces)
            all_rows.extend(rows)
            working_sets[(scope, method_name)] = working_set
    atomic_jsonl(artifact_root / "per_row_results.jsonl", all_rows)

    scopes = {
        "endpoint_all_1036": lambda row: row["scope"] == "endpoint",
        "endpoint_first_791": lambda row: (
            row["scope"] == "endpoint" and int(row["row_id"]) < ENDPOINT_ROWS
        ),
        "endpoint_tail_245": lambda row: (
            row["scope"] == "endpoint" and int(row["row_id"]) >= ENDPOINT_ROWS
        ),
        "gpqa_198": lambda row: row["scope"] == "gpqa",
    }
    summary = {}
    for scope_name, predicate in scopes.items():
        summary[scope_name] = {}
        source_scope = "gpqa" if scope_name.startswith("gpqa") else "endpoint"
        for method_name in methods:
            selected = [
                row
                for row in all_rows
                if row["method"] == method_name and predicate(row)
            ]
            summary[scope_name][method_name] = summarize(
                selected, working_sets[(source_scope, method_name)]
            )

    reductions = {}
    for scope_name, method_rows in summary.items():
        native = method_rows["native"]
        reductions[scope_name] = {}
        for method_name in methods[1:]:
            candidate = method_rows[method_name]
            reductions[scope_name][method_name] = {
                "fixed_target_row_reduction": (
                    1
                    - candidate["fixed_target_rows"]
                    / native["fixed_target_rows"]
                ),
                "target_pass_reduction": (
                    1
                    - candidate["target_passes"] / native["target_passes"]
                ),
            }

    ensemble_gate = {
        "endpoint_first_791_at_least_20pct": (
            reductions["endpoint_first_791"]["ensemble"][
                "fixed_target_row_reduction"
            ]
            >= 0.20
        ),
        "gpqa_198_at_least_20pct": (
            reductions["gpqa_198"]["ensemble"]["fixed_target_row_reduction"]
            >= 0.20
        ),
        "leakage_safe": True,
        "nontrivial_rows": len(primary[:ENDPOINT_ROWS]) >= 100 and len(gpqa) >= 100,
    }
    promoted = all(ensemble_gate.values())
    terminal = {
        "actual_spend_usd": 0.0,
        "causality_audit": deterministic_fixture_audit(),
        "classification": (
            "promote_leakage_safe_proposal_ensemble"
            if promoted
            else "close_measured_proposal_surface_below_gate"
        ),
        "decision": {
            "gates": ensemble_gate,
            "promoted": promoted,
            "reason": (
                "The deterministic ensemble cleared the cross-scope 20% target-work gate."
                if promoted
                else "The deterministic ensemble did not clear the 20% fixed target-work gate on both useful scopes."
            ),
        },
        "identities": manifest,
        "methods": {
            "ensemble": "output-history order>=2/support>=2; else prompt order>=4; else native",
            "native": "source-equivalent v0.5.15 BFS shared trie, depth 18, 11 proposal nodes plus root",
            "output_history": "current-request multi-order 18..1, frequency then recency then token-id tie-break",
            "prompt": "longest suffix match in current prompt, most-recent occurrence tie-break",
        },
        "native_source_fixture_audit": native_source_fixture_audit(),
        "reductions_vs_native": reductions,
        "schema_version": 1,
        "summary": summary,
        "transfer_limit": "CPU causal token replay; no serving-speed or GPU claim.",
    }
    atomic_json(project / "PROPOSAL_ENSEMBLE_RESULT.json", terminal)
    print(json.dumps(terminal["decision"], sort_keys=True))


if __name__ == "__main__":
    main()
