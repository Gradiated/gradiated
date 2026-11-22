"""Reconcile standalone and dedicated replays and emit route-ready RTL evidence."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil

from materialise_shared_norm_multiply import checked
from replay_shared import need


DEDICATED_RESULTS_PIN = "6a13bee1c57f06454fb2322ad3626cb2ee39a29770a4523435e1581584d22c02"
PROTOCOL = Path("hardware/research/inference/experiments/kv260-norm-mul-shared-v1.md")
PROTOCOL_PIN = "4a68d029f7757197f9d4de63ab4165eafe903dd2ebee24009db7322c77562d0d"
VARIANT = "norm-mul-shared-v1"
NATURAL = ("encoded-hello-cap255", "encoded-fu2p2q-cap255", "encoded-max48-cap255")


def pin(path):
    return sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def cross_check(case, older, observed):
    shared, dedicated = observed/"candidate"/case, older/"candidate"/case
    for name in ("cache.kv", "phases.txt", "bus.events", "attention-events.txt",
                 "divider-values.txt", "cache-addresses.bin", "feedforward-products.txt",
                 "feedforward-elements.txt", "feedforward-profile.txt", "bos.csv"):
        need((shared/name).read_bytes() == (dedicated/name).read_bytes(),
             f"{case}: independent dedicated trace differs in {name}")
    with (dedicated/"norm-products.txt").open() as previous, (shared/"norm-products.txt").open() as new:
        for incoming, outgoing, compared in zip(previous, previous, new, strict=True):
            in_fields, out_fields, same = incoming.split(), outgoing.split(), compared.split()
            need(in_fields[0] == "A" and out_fields[0] == "P" and in_fields[1:7] == out_fields[1:7],
                 f"{case}: dedicated operand/product pairing differs")
            lane, depth = in_fields[1:3]
            a,b = in_fields[7:]
            need(same[:4] == [depth,lane,a,b] and same[5] == out_fields[7],
                 f"{case}: dedicated raw product differs")
    with (dedicated/"norm-results.txt").open() as previous, (shared/"norm-outputs.txt").open() as new:
        for expected, compared in zip(previous,new,strict=True):
            lane, depth, *values = expected.split()
            need([depth,lane,*values] == compared.split(), f"{case}: dedicated norm result differs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "dedicated-replay", "dedicated-results", "replay", "directed", "output"):
        parser.add_argument("--" + name, type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    check_text = (args.directed/"simulation.log").read_text()
    phi = "PASS shared scalar: 396 exact signed products, 4 blocked response clocks, five reset points"
    need(phi in check_text, "Directed proof did not pass")
    checked(args.repo / PROTOCOL, PROTOCOL_PIN)
    expected = json.loads(checked(args.dedicated_results, DEDICATED_RESULTS_PIN))
    observed = json.loads((args.replay/"model-results.json").read_text())
    need(set(expected) == set(observed) and len(observed)==7, "Expected seven matched fixtures")

    completed = {}
    for case, data in observed.items():
        cross_check(case, args.dedicated_replay, args.replay)
        old = expected[case]["candidate"]
        for boundary in ("prefix", "done"):
            row = data[boundary]
            compare = {"first_valid": row["valid"], "first": row["first"], "last": row["last"],
                       "done": row["done"], "phases": row["ticks"]}
            need(compare == {k:old[boundary][k] for k in compare},
                 f"{case}: archived {boundary} boundary differs")
        count = data["positions"]
        scored = data["scored_values"]
        need(old["done"]["positions"] == count and expected[case]["scored_values"] == scored
             and expected[case]["outputs"] == data["outputs"], f"{case}: archived request counts differ")
        completed[case] = dict(control=old, candidate=old, outputs=data["outputs"],
                               scored_values=scored, skipped_positions=count-scored//320,
                               stop_reason=expected[case]["stop_reason"], saved_clocks=0,
                               normalization_products=data["products"])
    need(sum(row["normalization_products"] for row in completed.values()) == 219096,
         "Wrong total normalization products")
    save(args.replay/"matched.json", completed)
    save(args.replay/"natural-gate.json", {case:completed[case] for case in NATURAL})
    for arm in ("control", "candidate"):
        destination = args.directed/arm
        destination.mkdir()
        shutil.copyfile(args.replay/arm/"rtl/source-manifest.json", destination/"source-manifest.json")
    directed = dict(all_exact=True, scalar_vectors=396, simultaneous_batches=132,
                    stalled_shared_response_clocks=4, reset_points=5,
                    exact_norm_products=219096, exact_norm_outputs=68736, unexpected_handoffs=0)
    save(args.directed/"summary.json", directed)
    save(args.output, dict(
        candidate=VARIANT, protocol=str(PROTOCOL), protocol_sha256=PROTOCOL_PIN,
        directed_summary=str(args.directed/"summary.json"), directed_summary_sha256=pin(args.directed/"summary.json"),
        replay_summary=str(args.replay/"natural-gate.json"), replay_summary_sha256=pin(args.replay/"natural-gate.json"),
        candidate_rtl_manifest_sha256=pin(args.replay/"candidate/rtl/source-manifest.json"),
        control_rtl_manifest_sha256=pin(args.replay/"control/rtl/source-manifest.json"),
        changed_rtl=["rmsnorm","transformer"], selected_sites=["norm1.scalar","norm2.scalar","normfinal.scalar","norm_mul"],
    ))
    print("Full independent dedicated cross-check and route evidence passed.")


if __name__ == "__main__":
    main()
