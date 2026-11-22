"""Generate the two narrow RTL overrides from the pinned autonomous-v1 sources."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE_PIN = "b964dde00531a9cf65aa6121cfb1c36c321213d01b765d4a690e9da5fcb94980"


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Unexpected source around {old!r}")
    return text.replace(old, new)


def core(text):
    text = replace(text, "    input logic [8:0] token,",
                   "    input logic [8:0] token,\n    input logic skip_projection,\n    output logic skipped_done,")
    text = replace(text, "    typedef enum logic", "    logic skip_current_projection;\n    typedef enum logic")
    text = replace(text, "    always_ff @(posedge clk) begin",
                   """    always_ff @(posedge clk) begin
        if (reset || clear_context) begin
            skip_current_projection <= 0;
            skipped_done <= 0;
        end else begin
            if (token_valid && token_ready)
                skip_current_projection <= skip_projection;
            // Registered completion lets the controller see clipping from the last norm value.
            skipped_done <= state == NF_WAIT && nf_valid && nf_ready &&
                            nf_index == 31 && skip_current_projection;
        end
    end

    always_ff @(posedge clk) begin""")
    return replace(text, "if(nf_index==31)state<=LOGIT_START;",
                   "if(nf_index==31)state<=skip_current_projection ? IDLE : LOGIT_START;")


def wrapper(text):
    text = replace(text, "A_DECIDE=3,A_DONE=4,A_FAULT=5;", "A_DECIDE=3,A_DONE=4,A_FAULT=5,A_SKIP_WAIT=6;")
    text = replace(text, "    logic selected_valid,selected_ready;",
                   "    logic selected_valid,selected_ready,skip_projection,skipped_done;\n"
                   "    logic [8:0] skipped_positions;")
    text = replace(text, "auto_state==A_SCORES || auto_state==A_DECIDE;",
                   "auto_state==A_SCORES || auto_state==A_DECIDE || auto_state==A_SKIP_WAIT;")
    text = replace(text, "    assign auto_owned=auto_state!=A_IDLE;",
                   "    assign auto_owned=auto_state!=A_IDLE;\n"
                   "    assign skip_projection=auto_state==A_SEND && prefix_index+9'd1<prompt_count;")
    text = replace(text, "accepted_positions<=0;accepted_scores<=0;",
                   "accepted_positions<=0;accepted_scores<=0;skipped_positions<=0;")
    text = replace(text, "auto_state<=A_SCORES;best_valid<=0;expected_score<=0;",
                   "auto_state<=skip_projection ? A_SKIP_WAIT : A_SCORES;best_valid<=0;expected_score<=0;")
    text = replace(text, """                    A_DECIDE:begin
                        if(prefix_index+9'd1<prompt_count)begin
                            prefix_index<=prefix_index+9'd1;next_token<=prompt_memory[8'(prefix_index+9'd1)];auto_state<=A_SEND;
                        end else if(output_limit==0)begin""",
                   """                    A_SKIP_WAIT:if(skipped_done && !core_busy)begin
                        skipped_positions<=skipped_positions+9'd1;
                        prefix_index<=prefix_index+9'd1;
                        next_token<=prompt_memory[8'(prefix_index+9'd1)];
                        auto_state<=A_SEND;
                    end
                    A_DECIDE:begin
                        if(output_limit==0)begin""")
    text = replace(text, "        .busy(core_busy),", "        .skip_projection(skip_projection),.skipped_done(skipped_done),\n"
                   "        .busy(core_busy),")
    text = replace(text, "32'h41553031", "32'h41553032")
    return replace(text, "                    8'h58:s_axi_rdata<=accepted_scores;",
                   "                    8'h58:s_axi_rdata<=accepted_scores;\n"
                   "                    8'h5c:s_axi_rdata<={23'd0,skipped_positions};")


def materialise(kv260, output, *, candidate=True):
    baseline = kv260 / "variants/autonomous-v1"
    spec = (baseline / "manifest.json").read_bytes()
    if sha256(spec).hexdigest() != BASELINE_PIN:
        raise ValueError("Autonomous baseline manifest differs")
    files = {}
    for name, expected in json.loads(spec)["generated"].items():
        directory = baseline / "rtl" if name == "axi_transformer" else kv260 / "rtl"
        data = (directory / (name + ".sv")).read_bytes()
        if sha256(data).hexdigest() != expected:
            raise ValueError(f"Autonomous source differs: {name}")
        if candidate and name in {"transformer", "axi_transformer"}:
            data = (core if name == "transformer" else wrapper)(data.decode()).encode()
        files[name] = data
    manifest = {name: sha256(data).hexdigest() for name, data in files.items()}
    if candidate and json.loads((HERE / "manifest.json").read_text()) != manifest:
        raise ValueError("Candidate source closure differs")
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        (output / (name + ".sv")).write_bytes(data)
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return list(files)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.output)
