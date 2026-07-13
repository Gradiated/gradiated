#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
import urllib.error
import urllib.request
from pathlib import Path

from score_pair import ScoreError, score_pair
from validate_quality import QualityError, load_and_validate


class RunnerError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class QualityAPIClient:
    def __init__(self, base_url, execution_contract, api_key=None):
        self.base_url = base_url.rstrip("/")
        self.execution_contract = execution_contract
        self.api_key = api_key

    def post(self, endpoint, payload):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self.base_url + endpoint,
            data=canonical(payload),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.execution_contract["timeout_seconds"]) as response:
                raw = response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            raise RunnerError(f"quality transport failed: {type(error).__name__}") from error
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RunnerError("quality endpoint returned malformed JSON") from error
        if not isinstance(value, dict) or "error" in value:
            raise RunnerError("quality endpoint returned an error object")
        return value, hashlib.sha256(raw).hexdigest()

    def chat(self, case, messages):
        contract = self.execution_contract
        payload = {
            "model": "zai-org/GLM-4.7-Flash",
            "messages": messages,
            "temperature": contract["temperature"],
            "top_p": contract["top_p"],
            "max_tokens": contract["max_output_tokens"],
            "seed": 470200,
            "stream": False,
        }
        value, raw_sha256 = self.post(contract["chat_endpoint"], payload)
        choices = value.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise RunnerError("chat response must contain exactly one choice")
        choice = choices[0]
        if choice.get("finish_reason") == "length":
            raise RunnerError("quality response was truncated")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise RunnerError("chat response message is missing")
        output = message.get("content")
        tool_calls = message.get("tool_calls")
        if output is None and isinstance(tool_calls, list) and len(tool_calls) == 1:
            function = tool_calls[0].get("function", {})
            try:
                arguments = json.loads(function.get("arguments", ""))
            except json.JSONDecodeError as error:
                raise RunnerError("structured tool arguments are malformed") from error
            output = json.dumps({"name": function.get("name"), "arguments": arguments}, sort_keys=True, separators=(",", ":"))
        if not isinstance(output, str):
            raise RunnerError("chat response has neither text nor one structured tool call")
        return {"output": output, "raw_sha256": raw_sha256}

    def teacher_force(self, case, text):
        contract = self.execution_contract
        payload = {
            "text": text,
            "sampling_params": {
                "temperature": 0.0,
                "max_new_tokens": contract["teacher_forced_max_new_tokens"],
            },
            "return_logprob": True,
            "logprob_start_len": 0,
            "top_logprobs_num": 0,
        }
        value, raw_sha256 = self.post(contract["teacher_forced_logprob_endpoint"], payload)
        value["_raw_sha256"] = raw_sha256
        return value


def messages_for_case(case):
    if case["category"] == "long_context_retrieval":
        return [{"role": "user", "content": case["synthetic_context"] + "\n\n" + case["prompt"]}]
    if case["category"] == "multi_turn_continuation":
        return case["history"] + [{"role": "user", "content": case["prompt"]}]
    return [{"role": "user", "content": case["prompt"]}]


def normalized_input_logprobs(case, response):
    meta_info = response.get("meta_info")
    rows = meta_info.get("input_token_logprobs") if isinstance(meta_info, dict) else None
    if not isinstance(rows, list):
        raise RunnerError("runtime input token logprobs are missing")
    values = []
    for row in rows:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            logprob, token_id = row[0], row[1]
        elif isinstance(row, dict):
            logprob, token_id = row.get("logprob"), row.get("token_id")
        else:
            raise RunnerError("runtime input token logprobs are malformed")
        if logprob is None:
            continue
        if not isinstance(logprob, (int, float)) or isinstance(logprob, bool) or not math.isfinite(logprob) or logprob > 0:
            raise RunnerError("runtime input token logprob is invalid")
        if not isinstance(token_id, int) or isinstance(token_id, bool) or token_id < 0:
            raise RunnerError("runtime input token ID is invalid")
        values.append({"logprob": float(logprob), "token_id": token_id})
    minimum = case["scorer"]["minimum_scored_tokens"]
    if len(values) < minimum:
        raise RunnerError("runtime input token logprobs are incomplete")
    return {
        "source": "runtime_teacher_forced_input_token_logprobs",
        "token_sequence_sha256": case["token_sequence_sha256"],
        "input_token_logprobs": values,
    }


def write_json(path, value):
    Path(path).write_bytes(canonical(value) + b"\n")


def write_jsonl(path, values):
    Path(path).write_bytes(b"".join(canonical(value) + b"\n" for value in values))


def run_endpoint(bundle, split, client, response_path, evidence_path):
    if split not in {"development", "holdout"}:
        raise RunnerError("quality split must be development or holdout")
    cases = bundle["fixtures"][split]
    response_rows = []
    evidence_rows = []
    for case in cases:
        if case["category"] == "teacher_forced_loss":
            raw = client.teacher_force(case, case["teacher_forced_text"])
            output = normalized_input_logprobs(case, raw)
            raw_sha256 = raw.get("_raw_sha256") or hashlib.sha256(canonical(raw)).hexdigest()
            evidence_rows.append({
                "case_id": case["case_id"],
                "mode": "runtime_teacher_forced_input_logprobs",
                "request_count": 1,
                "raw_response_sha256": raw_sha256,
                "scored_token_count": len(output["input_token_logprobs"]),
            })
        else:
            repetitions = case.get("deterministic_repetitions", bundle["policy"]["execution_contract"]["request_repetitions"])
            results = [client.chat(case, messages_for_case(case)) for _ in range(repetitions)]
            outputs = [result["output"] for result in results]
            if len(set(outputs)) != 1:
                raise RunnerError(f"deterministic serving mismatch for {case['case_id']}")
            output = outputs[0]
            evidence_rows.append({
                "case_id": case["case_id"],
                "mode": "deterministic_chat_completion",
                "request_count": repetitions,
                "raw_response_sha256": [result["raw_sha256"] for result in results],
                "exact_repetition_identity": True,
            })
        response_rows.append({"case_id": case["case_id"], "output": output})
    write_jsonl(response_path, response_rows)
    response_sha256 = hashlib.sha256(Path(response_path).read_bytes()).hexdigest()
    evidence = {
        "schema_version": 1,
        "suite_sha256": bundle["manifest"]["bundle_sha256"],
        "split": split,
        "response_file_sha256": response_sha256,
        "cases": evidence_rows,
        "caller_supplied_nll_used": False,
        "model_emitted_compliance_flags_used": False,
    }
    write_json(evidence_path, evidence)
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["capture", "score", "pair"], required=True)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--split", choices=["development", "holdout"], required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--control-url")
    parser.add_argument("--candidate-url")
    parser.add_argument("--output-dir")
    parser.add_argument("--responses")
    parser.add_argument("--evidence")
    parser.add_argument("--control-responses")
    parser.add_argument("--candidate-responses")
    parser.add_argument("--result-output")
    parser.add_argument("--api-key-env", default="")
    arguments = parser.parse_args()
    try:
        bundle = load_and_validate(arguments.suite)
        api_key = os.environ.get(arguments.api_key_env) if arguments.api_key_env else None
        contract = bundle["policy"]["execution_contract"]
        if arguments.mode == "capture":
            if not all([arguments.base_url, arguments.responses, arguments.evidence]):
                raise RunnerError("capture mode requires --base-url, --responses, and --evidence")
            run_endpoint(
                bundle,
                arguments.split,
                QualityAPIClient(arguments.base_url, contract, api_key),
                Path(arguments.responses),
                Path(arguments.evidence),
            )
            return
        if arguments.mode == "score":
            if not all([arguments.control_responses, arguments.candidate_responses, arguments.result_output]):
                raise RunnerError("score mode requires both response files and --result-output")
            result = score_pair(
                arguments.suite,
                arguments.split,
                Path(arguments.control_responses),
                Path(arguments.candidate_responses),
            )
            write_json(Path(arguments.result_output), result)
        else:
            if not all([arguments.control_url, arguments.candidate_url, arguments.output_dir]):
                raise RunnerError("pair mode requires both URLs and --output-dir")
            output = Path(arguments.output_dir)
            output.mkdir(parents=True, exist_ok=True)
            control_responses = output / "control_responses.jsonl"
            candidate_responses = output / "candidate_responses.jsonl"
            run_endpoint(
                bundle,
                arguments.split,
                QualityAPIClient(arguments.control_url, contract, api_key),
                control_responses,
                output / "control_evidence.json",
            )
            run_endpoint(
                bundle,
                arguments.split,
                QualityAPIClient(arguments.candidate_url, contract, api_key),
                candidate_responses,
                output / "candidate_evidence.json",
            )
            result = score_pair(arguments.suite, arguments.split, control_responses, candidate_responses)
            write_json(output / "paired_quality_result.json", result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        if not result["point_screen_pass"]:
            raise SystemExit(1)
    except (QualityError, RunnerError, ScoreError) as error:
        print(f"INVALID: {error}", file=os.sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
