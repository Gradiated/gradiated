"""Add a second exact exponential unit to the adopted serial attention circuit."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
ADOPTED = "variants/attention-exp-div-v1"


def digest(data):
    return sha256(data).hexdigest()


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Unexpected adopted source: {old}")
    return source.replace(old, new, 1)


def parallelise(source):
    controller, helpers = source.split("endmodule", 1)
    controller = replace_once(
        controller, "CONTEXT_REQ, CONTEXT_DATA, CONTEXT_MAC, CONTEXT_SEND, CONTEXT_WAIT, OUTPUT",
        "CONTEXT_REQ, CONTEXT_DATA, CONTEXT_MAC, CONTEXT_SEND, CONTEXT_WAIT, OUTPUT,\n"
        "        EXP_READ_SECOND, EXP_RETIRE_SECOND")
    controller = replace_once(controller, "    logic next_score_coordinate, next_value_position;", """    logic next_score_coordinate, next_value_position;
    logic exp_pair, first_exp_failed, first_exp_error, second_exp_error;
    logic second_cmd_valid, second_cmd_ready, second_table_ready;
    logic second_result_valid, second_result_ready, second_error;
    logic commit_first_exp, commit_second_exp;
    logic [7:0] exp_read_position;
    logic signed [31:0] exp_read_score;
    logic signed [63:0] exp_delta, second_input, second_result, committed_exp;""")
    controller = replace_once(controller, "!load_valid && scalar_table_ready;",
                              "!load_valid && scalar_table_ready && second_table_ready;")
    controller = replace_once(controller,
        "    assign scalar_cmd_valid=state==SCORE_SEND || state==EXP_SEND || state==PROB_SEND || state==CONTEXT_SEND;",
        """    // Keep one score read port. The second score is read on the next clock.
    assign exp_pair = {1'b0,position} + 9'd1 < length;
    assign exp_read_position = position + {7'd0,state==EXP_READ_SECOND};
    assign exp_read_score = scores[exp_read_position];
    assign exp_delta = $signed({{32{exp_read_score[31]}},exp_read_score}) -
                       $signed({{32{maximum[31]}},maximum});
    // The controller drains each issued result before it reaches a new SEND.
    // A table write can occur only in IDLE, so both requested lanes are ready.
    assign scalar_cmd_valid = state==SCORE_SEND || state==EXP_SEND || state==PROB_SEND || state==CONTEXT_SEND;
    assign second_cmd_valid = state==EXP_SEND && exp_pair;
    assign second_result_ready = state==EXP_RETIRE_SECOND;
    assign first_exp_error = scalar_error || scalar_result<0 || scalar_result>64'sd2147483648;
    assign second_exp_error = second_error || second_result<0 || second_result>64'sd2147483648;
    assign commit_first_exp = state==EXP_WAIT && scalar_result_valid && !first_exp_error;
    assign commit_second_exp = state==EXP_RETIRE_SECOND && second_result_valid &&
                               !first_exp_failed && !second_exp_error;
    assign committed_exp = state==EXP_RETIRE_SECOND ? second_result : scalar_result;""")
    controller = replace_once(controller, "    task automatic fail;", """    fixed_scalar_attention_exp second_exp (
        .clk(clk),.reset(reset),.cmd_valid(second_cmd_valid),.cmd_ready(second_cmd_ready),
        .cmd_op(3'd3),.cmd_a(second_input),.cmd_b(64'sd0),.cmd_shift(8'sd0),
        .table_valid(table_valid && table_ready),.table_ready(second_table_ready),.table_kind(1'b0),
        .table_index(table_index),.table_value(table_value),.result_valid(second_result_valid),
        .result_ready(second_result_ready),.result(second_result),.result_exponent(),.error(second_error)
    );
    task automatic finish_exp;
        begin
            if ({1'b0,position}+9'd1==length) begin
                position<=0;state<=PROB_READ;
            end else begin
                position<=position+1'b1;state<=EXP_READ;
            end
        end
    endtask
    task automatic fail;""")
    controller = replace_once(controller, "            scalar_op<=0;scalar_a<=0;scalar_b<=0;scalar_shift<=0;",
        """            scalar_op<=0;scalar_a<=0;scalar_b<=0;scalar_shift<=0;
            second_input<=0;first_exp_failed<=0;""")
    controller = replace_once(controller, '            score_valid<=0;exp_valid<=0;probability_valid<=0;step_valid<=0;', '            score_valid<=0;exp_valid<=0;probability_valid<=0;step_valid<=0;\n            // This buffer has one write port for both ordered completions.\n            if (commit_first_exp || commit_second_exp) begin\n                exponentials[position]<=committed_exp[31:0];\n                exp_sum<=exp_sum+$unsigned(committed_exp);\n                exp_valid<=1;exp_head<=head;exp_position<=position;exp_value<=committed_exp[31:0];\n            end')
    a = controller.index("                EXP_READ: begin")
    b = controller.index("                PROB_READ: begin", a)
    controller = controller[:a] + """                EXP_READ: begin
                    scalar_a<=exp_delta;scalar_b<=0;scalar_op<=3;scalar_shift<=0;
                    state<=exp_pair ? EXP_READ_SECOND : EXP_SEND;
                end
                EXP_READ_SECOND: begin
                    second_input<=exp_delta;
                    state<=EXP_SEND;
                end
                EXP_SEND: if (scalar_cmd_ready && (!exp_pair || second_cmd_ready)) state<=EXP_WAIT;
                EXP_WAIT: if (scalar_result_valid) begin
                    if (exp_pair) begin
                        // A fault in the first unit still drains the second unit.
                        // The next command must never see its old held result.
                        first_exp_failed<=first_exp_error;
                        position<=position+1'b1;
                        state<=EXP_RETIRE_SECOND;
                    end else if (first_exp_error) fail();
                    else finish_exp();
                end
                EXP_RETIRE_SECOND: if (second_result_valid) begin
                    if (first_exp_failed || second_exp_error) fail();
                    else finish_exp();
                end
""" + controller[b:]
    return controller + "endmodule" + helpers


def materialise(kv260, output, candidate):
    spec = json.loads((HERE / "manifest.json").read_bytes())
    adopted = kv260 / ADOPTED
    generator = adopted / "materialise_attention_exp.py"
    if (digest(generator.read_bytes()) != spec["control_generator_sha256"] or
        digest((adopted / "manifest.json").read_bytes()) != spec["control_manifest_sha256"]):
        raise ValueError("Adopted generator or manifest differs")
    names = runpy.run_path(str(generator))["materialise"](kv260, output, True)
    attention = output / "attention.sv"
    if digest(attention.read_bytes()) != spec["control_attention_sha256"]:
        raise ValueError("Adopted attention source differs")
    if candidate:
        data = parallelise(attention.read_text()).encode()
        pin = digest(data)
        if pin != spec["candidate_attention_sha256"]:
            raise ValueError("Generated parallel attention differs")
        attention.write_bytes(data)
        ledger = output / "source-manifest.json"
        hashes = json.loads(ledger.read_bytes())
        hashes["attention"] = pin
        ledger.write_text(json.dumps(hashes, indent=2) + "\n")
    return names


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=("control", "candidate"), required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.output, args.arm == "candidate")
