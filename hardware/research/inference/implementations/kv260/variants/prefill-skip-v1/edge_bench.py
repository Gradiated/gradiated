"""Derive a focused skip-controller test from the pinned autonomous AXI bench."""
from hashlib import sha256
from materialise import replace

SOURCE_PIN = "5449d4a09a7a6a26ae50089e4e416848ecb90f1f101f24fa24ae051cb3a2988d"

STIMULUS = """    initial begin
        int old_positions, old_scores;
        bus_reset();
        expect_reg(ID, 32'h41553032);
        configure();
        old_positions = dut.core.accepted_tokens;
        old_scores = dut.core.accepted_scores;
        queue_prompt(34);
        write_reg(START, 1, OKAY, 4'hf, 2, 8);
        expect_reg(STATUS, ACTIVE);
        expect_reg(8'h5c, 0);
        expect_reg(POSITIONS, 1);
        expect_reg(SCORES, 0);
        write_reg(CONTROL, 1, SLVERR);
        expect_reg(SCORE, 0, SLVERR);
        wait_done(DONE | AVAILABLE | BYTE_TIMES | EOS_STOP);
        expect_work(old_positions, old_scores, 3, 640, 1, 1);
        expect_token(old_positions, 256);
        expect_token(old_positions + 1, 34);
        expect_token(old_positions + 2, 0);
        expect_reg(8'h5c, 1);
        send_read(POP);
        repeat (8) begin tick(); check_read(OKAY, 0); @(negedge aclk); end
        write_reg(CONTROL, 2, SLVERR);
        check_read(OKAY, 0);
        finish_read();
        write_reg(CONTROL, 1);
        expect_reg(8'h5c, 0);
        expect_fresh_controller();

        // Fault flags arrive on the same edge as the completion pulse.
        for(int kind=1;kind<=2;kind++)begin
            dut.core.skip_fault_kind=kind;
            queue_prompt(34);
            write_reg(START, 1);
            wait_done(DONE | FAULT | FAULT_STOP);
            expect_reg(POSITIONS, 1);
            expect_reg(8'h5c, 0);
            expect_reg(SCORES, 0);
            write_reg(CONTROL, 1, SLVERR);
            write_reg(CONTROL, 2);
            expect_fresh_controller();
            configure();
        end
        dut.core.skip_fault_kind=0;
        queue_prompt(34);
        write_reg(START, 1);
        wait(dut.auto_state==6);
        write_reg(CONTROL, 2);
        expect_fresh_controller();
        configure();
        old_scores=dut.core.accepted_scores;
        write_reg(TOKEN, 256);
        repeat(8)tick();
        expect_reg(SCORE, 32'h80000000);
        if(dut.core.accepted_scores!=old_scores+1)$fatal(1,"Legacy request failed after skip reset");
        expect_reg(8'h5c, 0);
        $display("PASS skip wait, simultaneous completion/error/clip, output stalls, reset and legacy isolation");
        $finish;
    end

"""


def build_edge(source):
    raw = source.read_bytes()
    if sha256(raw).hexdigest() != SOURCE_PIN:
        raise ValueError("Pinned AXI edge bench changed")
    text = raw.decode()
    first=text.index("    initial begin\n        int old_positions")
    limit=text.index("    initial begin\n        #4000000;",first)
    text=text[:first]+STIMULUS+text[limit:]
    text=replace(text,"    input logic [8:0] token,",
                 "    input logic [8:0] token,\n    input logic skip_projection,\n    output logic skipped_done,")
    text=replace(text,"    logic [1:0] loaded, delay_count;",
                 "    logic [1:0] loaded, delay_count;\n    logic [7:0] skip_left;\n    int skip_fault_kind=0;")
    text=replace(text,"assign logit_valid = busy && delay_count == 0;",
                 "assign logit_valid = busy && delay_count == 0 && skip_left == 0;")
    text=replace(text,"            delay_count <= 0;","            delay_count <= 0;\n            skip_left <= 0;\n            skipped_done <= 0;")
    text=replace(text,"            if (weight_valid && weight_ready) begin",
                 """            skipped_done <= 0;
            if(skip_left != 0)begin
                skip_left <= skip_left-1'b1;
                if(skip_left==1)begin
                    busy <= 0;
                    skipped_done <= 1;
                    error <= skip_fault_kind==1;
                    saturated <= skip_fault_kind==2;
                end
            end
            if (weight_valid && weight_ready) begin""")
    return replace(text,"                delay_count <= 3;",
                   "                delay_count <= 3;\n                skip_left <= skip_projection ? 8'd100 : 8'd0;")
