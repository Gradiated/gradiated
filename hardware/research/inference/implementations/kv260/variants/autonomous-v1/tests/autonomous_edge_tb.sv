// Synthetic controller and AXI protocol checks using scripted scores.
`timescale 1ns/1ps
module autonomous_edge_tb;
    localparam logic [7:0] LEGACY_STATUS = 8'h00, BANK = 8'h04, ADDRESS = 8'h08,
        WEIGHT = 8'h0c, TOKEN = 8'h10, SCORE = 8'h18, CONTROL = 8'h1c, CONTEXT = 8'h20,
        ID = 8'h24, STATUS = 8'h28, PROMPT_COUNT = 8'h2c, APPEND = 8'h30, LIMIT = 8'h34,
        START = 8'h38, EMITTED = 8'h3c, POP = 8'h40, UNREAD = 8'h44, FIRST_CYCLES = 8'h48,
        LAST_CYCLES = 8'h4c, DONE_CYCLES = 8'h50, POSITIONS = 8'h54, SCORES = 8'h58;
    localparam logic [1:0] OKAY = 0, SLVERR = 2;
    localparam logic [31:0] ACTIVE = 1, DONE = 2, FAULT = 4, AVAILABLE = 8,
        BYTE_TIMES = 32'h30, OVERFLOW = 32'h40, EOS_STOP = 32'h100, CONTEXT_STOP = 32'h200,
        NONBYTE_STOP = 32'h300, LIMIT_STOP = 32'h400, FAULT_STOP = 32'h500;
    logic aclk = 0, aresetn = 0;
    always #5 aclk = !aclk;
    logic [7:0] s_axi_awaddr = 0, s_axi_araddr = 0;
    logic [2:0] s_axi_awprot = 0, s_axi_arprot = 0;
    logic s_axi_awvalid = 0, s_axi_awready, s_axi_wvalid = 0, s_axi_wready;
    logic s_axi_bvalid, s_axi_bready = 0, s_axi_arvalid = 0, s_axi_arready;
    logic s_axi_rvalid, s_axi_rready = 0;
    logic [31:0] s_axi_wdata = 0, s_axi_rdata;
    logic [3:0] s_axi_wstrb = 4'hf;
    logic [1:0] s_axi_bresp, s_axi_rresp;
    axi_transformer dut (.*);

    task automatic tick;
        @(posedge aclk);
        #1;
    endtask

    // order 1 holds AW alone, order 2 holds W alone, and order 0 sends both.
    task automatic send_write(input logic [7:0] address, input logic [31:0] data,
                              input logic [3:0] strobe = 4'hf, input int order = 0);
        @(negedge aclk);
        s_axi_awaddr = address;
        s_axi_wdata = data;
        s_axi_wstrb = strobe;
        s_axi_awvalid = order != 2;
        s_axi_wvalid = order != 1;
        #1;
        if ((s_axi_awvalid && !s_axi_awready) || (s_axi_wvalid && !s_axi_wready))
            $fatal(1, "AXI write not ready at %h", address);
        tick();
        @(negedge aclk);
        s_axi_awvalid = 0;
        s_axi_wvalid = 0;
        if (order != 0) begin
            repeat (3) begin
                tick();
                if (s_axi_bvalid) $fatal(1, "Write to %h executed with one channel missing", address);
                @(negedge aclk);
            end
            s_axi_awvalid = order == 2;
            s_axi_wvalid = order == 1;
            #1;
            if ((s_axi_awvalid && !s_axi_awready) || (s_axi_wvalid && !s_axi_wready))
                $fatal(1, "Second AXI write channel not ready at %h", address);
            tick();
            @(negedge aclk);
            s_axi_awvalid = 0;
            s_axi_wvalid = 0;
        end
    endtask

    task automatic finish_write(input logic [1:0] wanted, input int stalls = 0);
        for (int wait_cycle = 0; !s_axi_bvalid; wait_cycle++) begin
            if (wait_cycle == 20) $fatal(1, "No B response at %h", s_axi_awaddr);
            tick();
            @(negedge aclk);
        end
        if (s_axi_bresp != wanted)
            $fatal(1, "Write %h=%h: got BRESP %b, wanted %b", s_axi_awaddr, s_axi_wdata, s_axi_bresp, wanted);
        if (stalls != 0) begin
            s_axi_awvalid = 1;
            s_axi_wvalid = 1;
            repeat (stalls) begin
                tick();
                if (!s_axi_bvalid || s_axi_bresp != wanted || s_axi_awready || s_axi_wready)
                    $fatal(1, "B response changed or accepted another write during the stall");
                @(negedge aclk);
            end
            s_axi_awvalid = 0;
            s_axi_wvalid = 0;
        end
        s_axi_bready = 1;
        tick();
        if (s_axi_bvalid) $fatal(1, "B handshake failed");
        @(negedge aclk);
        s_axi_bready = 0;
    endtask

    task automatic write_reg(input logic [7:0] address, input logic [31:0] data,
                             input logic [1:0] response = OKAY,
                             input logic [3:0] strobe = 4'hf, input int order = 0,
                             input int stalls = 0);
        send_write(address, data, strobe, order);
        finish_write(response, stalls);
    endtask

    task automatic capture_read(input logic [7:0] address);
        s_axi_araddr = address;
        s_axi_arvalid = 1;
        #1;
        if (!s_axi_arready) $fatal(1, "AXI read not ready at %h", address);
        tick();
        @(negedge aclk);
        s_axi_arvalid = 0;
        if (!s_axi_rvalid) $fatal(1, "No R response at %h", address);
    endtask

    task automatic send_read(input logic [7:0] address);
        @(negedge aclk);
        capture_read(address);
    endtask

    task automatic check_read(input logic [1:0] wanted, input logic [31:0] data);
        if (!s_axi_rvalid || s_axi_rresp != wanted || s_axi_rdata != data)
            $fatal(1, "Read %h: got %h RRESP %b, wanted %h RRESP %b",
                   s_axi_araddr, s_axi_rdata, s_axi_rresp, data, wanted);
    endtask

    task automatic finish_read;
        s_axi_rready = 1;
        tick();
        if (s_axi_rvalid) $fatal(1, "R handshake failed");
        @(negedge aclk);
        s_axi_rready = 0;
    endtask

    task automatic expect_reg(input logic [7:0] address, input logic [31:0] data,
                              input logic [1:0] response = OKAY);
        send_read(address);
        check_read(response, data);
        finish_read();
    endtask

    task automatic get_reg(input logic [7:0] address, output logic [31:0] data);
        send_read(address);
        data = s_axi_rdata;
        check_read(OKAY, data);
        finish_read();
    endtask

    task automatic bus_reset;
        @(negedge aclk);
        aresetn = 0;
        s_axi_awvalid = 0;
        s_axi_wvalid = 0;
        s_axi_bready = 0;
        s_axi_arvalid = 0;
        s_axi_rready = 0;
        repeat (2) begin
            tick();
            if (s_axi_bvalid || s_axi_rvalid || s_axi_awready || s_axi_wready || s_axi_arready)
                $fatal(1, "Bus reset retained a channel");
            @(negedge aclk);
        end
        aresetn = 1;
    endtask

    task automatic configure;
        write_reg(BANK, 0, OKAY, 4'hf, 1, 3);
        write_reg(ADDRESS, 0, OKAY, 4'hf, 2, 3);
        write_reg(WEIGHT, 32'h12345678);
        write_reg(WEIGHT, 32'h98765432);
        expect_reg(ADDRESS, 2);
        expect_reg(LEGACY_STATUS, 32'h21);
    endtask

    task automatic queue_prompt(input int first_followup = -1);
        write_reg(APPEND, 256);
        if (first_followup >= 0) write_reg(APPEND, 32'(first_followup));
    endtask

    task automatic expect_fresh_controller;
        expect_reg(STATUS, 0);
        expect_reg(PROMPT_COUNT, 0);
        expect_reg(LIMIT, 255);
        expect_reg(EMITTED, 0);
        expect_reg(UNREAD, 0);
        expect_reg(POP, 0, SLVERR);
        expect_reg(FIRST_CYCLES, 0);
        expect_reg(LAST_CYCLES, 0);
        expect_reg(DONE_CYCLES, 0);
        expect_reg(POSITIONS, 0);
        expect_reg(SCORES, 0);
        expect_reg(CONTEXT, 0);
    endtask

    task automatic wait_done(input logic [31:0] wanted);
        logic [31:0] state_word;
        for (int sample = 0; sample < 4000; sample++) begin
            get_reg(STATUS, state_word);
            if ((state_word & DONE) != 0) begin
                if (state_word != wanted)
                    $fatal(1, "Completion status %h, wanted %h", state_word, wanted);
                return;
            end
            if ((state_word & ACTIVE) == 0) $fatal(1, "Controller became idle without completion");
            repeat (25) tick();
        end
        $fatal(1, "Autonomous request timed out, final status %h", state_word);
    endtask

    task automatic expect_work(input int old_positions, input int old_scores,
                               input int positions, input int scores, input int emitted,
                               input int unread);
        expect_reg(CONTEXT, 32'(positions));
        expect_reg(POSITIONS, 32'(positions));
        expect_reg(SCORES, 32'(scores));
        expect_reg(EMITTED, 32'(emitted));
        expect_reg(UNREAD, 32'(unread));
        if (dut.core.accepted_tokens != old_positions + positions ||
            dut.core.accepted_scores != old_scores + scores)
            $fatal(1, "Actual core handshakes %0d tokens and %0d scores, wanted %0d and %0d",
                   dut.core.accepted_tokens - old_positions, dut.core.accepted_scores - old_scores,
                   positions, scores);
        for (int i = 0; i < positions; i++)
            if (dut.core.input_context[old_positions + i] != i)
                $fatal(1, "Core input at position %0d started with context %0d",
                       i, dut.core.input_context[old_positions + i]);
    endtask

    task automatic expect_times(input int bytes, input bit later_stop = 0);
        logic [31:0] first, last, done;
        get_reg(FIRST_CYCLES, first);
        get_reg(LAST_CYCLES, last);
        get_reg(DONE_CYCLES, done);
        if (done == 0 || first > last || last > done ||
            (later_stop && last == done) ||
            (bytes == 0 && (first != 0 || last != 0)) ||
            (bytes != 0 && first == 0) ||
            (bytes == 1 && first != last) ||
            (bytes > 1 && first == last))
            $fatal(1, "Invalid timestamps: bytes=%0d first=%0d last=%0d done=%0d",
                   bytes, first, last, done);
    endtask

    task automatic expect_token(input int index, input int wanted);
        if (dut.core.input_token[index] != wanted)
            $fatal(1, "Core input %0d was %0d, wanted %0d", index, dut.core.input_token[index], wanted);
    endtask

    function automatic int full_prompt_token(input int position);
        // Reserve the stub's injected-fault tokens for their own requests.
        case (position)
            33, 36, 37, 39: return 256 + position;
            default: return position;
        endcase
    endfunction

    initial begin
        int old_positions, old_scores, old_clears, old_resets;
        bus_reset();
        expect_reg(ID, 32'h41553031);
        expect_reg(LEGACY_STATUS, 32'h40);
        expect_fresh_controller();
        write_reg(APPEND, 256, SLVERR);
        write_reg(START, 1, SLVERR);
        configure();
        write_reg(START, 1, SLVERR);
        write_reg(APPEND, 41, SLVERR);
        write_reg(APPEND, 256, SLVERR, 4'h1, 1, 3);
        write_reg(APPEND + 1, 256, SLVERR, 4'hf, 2, 3);
        write_reg(APPEND, 32'h1000100, SLVERR);
        write_reg(ID, 0, SLVERR);
        write_reg(UNREAD, 0, SLVERR);
        write_reg(LIMIT, 256, SLVERR);
        write_reg(LIMIT, 1, SLVERR, 4'h7);
        expect_reg(LIMIT, 255);
        expect_reg(PROMPT_COUNT, 0);
        expect_reg(APPEND, 0, SLVERR);
        expect_reg(START, 0, SLVERR);
        expect_reg(POP + 1, 0, SLVERR);
        queue_prompt();
        write_reg(TOKEN, 256, SLVERR);
        write_reg(APPEND, 320, SLVERR);
        write_reg(START, 0, SLVERR);
        write_reg(START, 3, SLVERR);
        write_reg(START, 1, SLVERR, 4'h3);
        expect_reg(PROMPT_COUNT, 1);
        expect_reg(POSITIONS, 0);
        expect_reg(STATUS, 0);

        // The synthetic BOS scores are all negative. IDs 11 and 19 tie for best.
        // Mid-request host writes and legacy score reads must not take ownership.
        write_reg(LIMIT, 1);
        old_positions = dut.core.accepted_tokens;
        old_scores = dut.core.accepted_scores;
        write_reg(START, 1, OKAY, 4'hf, 2, 8);
        expect_reg(STATUS, ACTIVE);
        write_reg(CONTROL, 1, SLVERR);
        write_reg(APPEND, 33, SLVERR);
        write_reg(START, 1, SLVERR);
        write_reg(LIMIT, 0, SLVERR);
        write_reg(TOKEN, 77, SLVERR);
        write_reg(WEIGHT, 77, SLVERR);
        write_reg(BANK, 1, SLVERR);
        write_reg(ADDRESS, 77, SLVERR);
        expect_reg(SCORE, 0, SLVERR);
        expect_reg(POP, 0, SLVERR);
        wait_done(DONE | AVAILABLE | BYTE_TIMES | LIMIT_STOP);
        expect_work(old_positions, old_scores, 1, 320, 1, 1);
        expect_token(old_positions, 256);
        expect_times(1);
        write_reg(START, 1, SLVERR);
        write_reg(TOKEN, 256, SLVERR);
        expect_reg(SCORE, 0, SLVERR);
        expect_reg(ADDRESS, 2);

        // Either an incoming or a held POP owns the response even when a
        // conflicting context-clear/full-reset write executes on the same edge.
        old_clears = dut.core.clear_count;
        old_resets = dut.core.reset_count;
        send_write(CONTROL, 1);
        capture_read(POP);
        finish_write(SLVERR, 3);
        check_read(OKAY, 11);
        write_reg(CONTROL, 2, SLVERR);
        s_axi_arvalid = 1;
        s_axi_araddr = POP;
        repeat (5) begin
            tick();
            check_read(OKAY, 11);
            if (s_axi_arready) $fatal(1, "Second POP accepted while first was held");
            @(negedge aclk);
        end
        s_axi_arvalid = 0;
        finish_read();
        if (old_clears != dut.core.clear_count || old_resets != dut.core.reset_count)
            $fatal(1, "Read ownership did not protect the core");
        expect_reg(UNREAD, 0);
        expect_reg(EMITTED, 1);
        expect_reg(STATUS, DONE | BYTE_TIMES | LIMIT_STOP);
        expect_reg(POP, 0, SLVERR);
        write_reg(CONTROL, 1);
        expect_fresh_controller();

        // Prompt scores are drained completely, including the discarded BOS
        // winner. Byte zero is emitted, then EOS ID 257 is kept out of the FIFO.
        old_positions = dut.core.accepted_tokens;
        old_scores = dut.core.accepted_scores;
        queue_prompt(34);
        write_reg(START, 1);
        wait_done(DONE | AVAILABLE | BYTE_TIMES | EOS_STOP);
        expect_work(old_positions, old_scores, 3, 960, 1, 1);
        expect_token(old_positions, 256);
        expect_token(old_positions + 1, 34);
        expect_token(old_positions + 2, 0);
        expect_times(1, 1);
        expect_reg(POP, 0);
        expect_reg(POP, 0, SLVERR);
        write_reg(CONTROL, 1);

        // Index 319 arrives last and wins with a negative score. The nonbyte
        // is preserved as nine bits and never fed back or timed as a byte.
        old_positions = dut.core.accepted_tokens;
        old_scores = dut.core.accepted_scores;
        queue_prompt(31);
        write_reg(START, 1);
        wait_done(DONE | AVAILABLE | NONBYTE_STOP);
        expect_work(old_positions, old_scores, 2, 640, 1, 1);
        expect_times(0);
        send_write(CONTROL, 2);
        capture_read(POP);
        finish_write(SLVERR);
        check_read(OKAY, 319);
        finish_read();
        write_reg(CONTROL, 1);

        // Limit zero and an EOS-first request both drain all 320 scores for
        // each prefix position, even though neither can emit a token.
        for (int request = 0; request < 2; request++) begin
            old_positions = dut.core.accepted_tokens;
            old_scores = dut.core.accepted_scores;
            queue_prompt(35);
            if (request == 0) write_reg(LIMIT, 0);
            write_reg(START, 1);
            wait_done(DONE | (request == 0 ? LIMIT_STOP : EOS_STOP));
            expect_work(old_positions, old_scores, 2, 640, 0, 0);
            expect_times(0);
            expect_reg(POP, 0, SLVERR);
            write_reg(CONTROL, 1);
        end

        // Hold an actual output read while the controller makes progress
        // through all 255 outputs. Remaining context wins the equal limits.
        old_positions = dut.core.accepted_tokens;
        old_scores = dut.core.accepted_scores;
        queue_prompt();
        write_reg(START, 1);
        repeat (350) begin tick(); @(negedge aclk); end
        expect_reg(STATUS, ACTIVE | AVAILABLE | BYTE_TIMES);
        send_read(POP);
        check_read(OKAY, 11);
        while (dut.core.accepted_scores < old_scores + 255 * 320) begin
            tick();
            check_read(OKAY, 11);
            if (s_axi_arready) $fatal(1, "AR ready while full buffer's head was reserved");
            @(negedge aclk);
        end
        repeat (8) begin tick(); @(negedge aclk); end
        write_reg(CONTROL, 2, SLVERR);
        check_read(OKAY, 11);
        finish_read();
        wait_done(DONE | AVAILABLE | BYTE_TIMES | CONTEXT_STOP);
        expect_work(old_positions, old_scores, 255, 255 * 320, 255, 254);
        expect_token(old_positions, 256);
        for (int i = 1; i < 255; i++) expect_token(old_positions + i, (10 + i) % 256);
        expect_times(255);
        for (int i = 1; i < 255; i++) expect_reg(POP, 32'((11 + i) % 256));
        expect_reg(UNREAD, 0);
        expect_reg(EMITTED, 255);
        expect_reg(POP, 0, SLVERR);
        write_reg(CONTROL, 1);

        // The ninth prompt-count bit must reach 256 without wrapping. Every
        // position receives its own input and all 320 scores despite no room
        // for an output. Vary the input so address aliases cannot pass.
        old_positions = dut.core.accepted_tokens;
        old_scores = dut.core.accepted_scores;
        queue_prompt();
        for (int i = 1; i < 256; i++) write_reg(APPEND, 32'(full_prompt_token(i)));
        expect_reg(PROMPT_COUNT, 256);
        write_reg(APPEND, 77, SLVERR);
        write_reg(LIMIT, 0);
        write_reg(START, 1);
        wait_done(DONE | CONTEXT_STOP);
        expect_work(old_positions, old_scores, 256, 256 * 320, 0, 0);
        expect_token(old_positions, 256);
        for (int i = 1; i < 256; i++) expect_token(old_positions + i, full_prompt_token(i));
        expect_times(0);
        write_reg(CONTROL, 1);

        // A deliberate core fault mid-score stops the request while preserving
        // the one earlier completed byte and its timing.
        old_positions = dut.core.accepted_tokens;
        old_scores = dut.core.accepted_scores;
        queue_prompt(38);
        write_reg(START, 1);
        wait_done(DONE | FAULT | AVAILABLE | BYTE_TIMES | FAULT_STOP);
        expect_work(old_positions, old_scores, 3, 653, 1, 1);
        expect_token(old_positions + 2, 33);
        expect_times(1, 1);
        expect_reg(POP, 33);
        write_reg(CONTROL, 1, SLVERR);
        write_reg(START, 1, SLVERR);
        write_reg(CONTROL, 2);
        expect_reg(LEGACY_STATUS, 32'h40);
        expect_fresh_controller();

        // Saturation terminates before an extra score is accepted. The
        // malformed index itself has already transferred. At the last score,
        // saturation leaves the underlying core idle but still requires reset.
        for (int scenario = 0; scenario < 3; scenario++) begin
            int fault_token, score_count;
            case (scenario)
                0: begin fault_token = 36; score_count = 333; end
                1: begin fault_token = 37; score_count = 334; end
                default: begin fault_token = 39; score_count = 640; end
            endcase
            configure();
            old_positions = dut.core.accepted_tokens;
            old_scores = dut.core.accepted_scores;
            queue_prompt(fault_token);
            write_reg(START, 1);
            wait_done(DONE | FAULT | FAULT_STOP);
            expect_work(old_positions, old_scores, 2, score_count, 0, 0);
            expect_times(0);
            expect_reg(POP, 0, SLVERR);
            if (fault_token == 39 && dut.core.busy)
                $fatal(1, "Final-score saturation test did not reach an idle core");
            write_reg(CONTROL, 1, SLVERR);
            expect_reg(STATUS, DONE | FAULT | FAULT_STOP);
            write_reg(CONTROL, 2);
            expect_fresh_controller();
        end

        // Move the cycle counter near exhaustion at a score handshake so both
        // the saturating limit and the exact number of consumed scores matter.
        configure();
        old_positions = dut.core.accepted_tokens;
        old_scores = dut.core.accepted_scores;
        queue_prompt();
        write_reg(START, 1);
        while (!(dut.core.logit_valid && dut.core.logit_ready)) begin
            tick();
            @(negedge aclk);
        end
        dut.auto_cycles = 32'hfffffffe;
        wait_done(DONE | FAULT | OVERFLOW | FAULT_STOP);
        expect_work(old_positions, old_scores, 1, 1, 0, 0);
        expect_reg(DONE_CYCLES, 32'hffffffff);
        expect_times(0);
        write_reg(CONTROL, 2);
        expect_fresh_controller();

        // Abort early with an unclaimed output path and perform two clean
        // restores: a software reset during generation and a hardware reset
        // while a POP response and half a write are both outstanding.
        configure();
        queue_prompt();
        write_reg(START, 1);
        expect_reg(STATUS, ACTIVE);
        write_reg(CONTROL, 2);
        expect_reg(LEGACY_STATUS, 32'h40);
        expect_fresh_controller();
        configure();
        queue_prompt();
        write_reg(LIMIT, 1);
        write_reg(START, 1);
        wait_done(DONE | AVAILABLE | BYTE_TIMES | LIMIT_STOP);
        send_read(POP);
        check_read(OKAY, 11);
        s_axi_awaddr = WEIGHT;
        s_axi_awvalid = 1;
        #1;
        if (!s_axi_awready) $fatal(1, "Could not create pending AW");
        tick();
        @(negedge aclk);
        s_axi_awvalid = 0;
        bus_reset();
        expect_fresh_controller();
        expect_reg(LEGACY_STATUS, 32'h40);
        configure();

        // Legacy access is restored and still advances exactly once on R.
        old_scores = dut.core.accepted_scores;
        write_reg(TOKEN, 256);
        repeat (8) tick();
        send_read(SCORE);
        check_read(OKAY, 32'h80000000);
        repeat (5) begin tick(); @(negedge aclk); end
        if (dut.core.accepted_scores != old_scores) $fatal(1, "Legacy score consumed before its R handshake");
        finish_read();
        if (dut.core.accepted_scores != old_scores + 1) $fatal(1, "Legacy score handshake lost");
        write_reg(CONTROL, 2);
        expect_fresh_controller();

        $display("PASS autonomous AXI edge simulation (synthetic scores)");
        $finish;
    end

    initial begin
        #4000000;
        $fatal(1, "Absolute AXI test time limit");
    end
endmodule

// Compile this scripted transformer in place of the real neural core only
// for the edge bench. It models independent token and score handshakes.
module transformer (
    input logic clk, reset, weight_valid,
    output logic weight_ready,
    input logic [3:0] weight_bank,
    input logic [15:0] weight_address,
    input logic [31:0] weight_value,
    output logic configured,
    input logic clear_context, token_valid,
    output logic token_ready,
    input logic [8:0] token,
    output logic busy, logit_valid,
    input logic logit_ready,
    output logic [8:0] logit_index,
    output logic signed [31:0] logit,
    output logic saturated, error,
    output logic [8:0] context_count,
    output logic [4:0] phase
);
    logic [1:0] loaded, delay_count;
    logic [8:0] current_token;
    logic consecutive_outputs;
    int accepted_tokens = 0, accepted_scores = 0, clear_count = 0, reset_count = 0;
    int input_token [0:1023], input_context [0:1023];

    assign weight_ready = !reset && !configured && weight_bank == 0
                          && weight_address == {14'd0, loaded};
    assign token_ready = !reset && configured && !busy && !clear_context && token < 320
                         && context_count < 256 && (context_count != 0 || token == 256);
    assign phase = busy ? 5'd1 : 5'd0;
    assign logit_valid = busy && delay_count == 0;

    function automatic logic signed [31:0] scripted_score(input logic [8:0] tok, index);
        logic [8:0] best;
        case (tok)
            256: best = 11;
            0, 35: best = 257;
            31: best = 319;
            34: best = 0;
            38: best = 33;
            default: best = 41;
        endcase
        if (consecutive_outputs) best = {1'b0, tok[7:0] + 8'd1};
        if (index == best || (tok == 256 && index == 19)) return -32'sd4;
        if (index == 0) return 32'sh80000000;
        return -32'sd1000 - $signed({23'd0, index});
    endfunction

    assign logit = scripted_score(current_token, logit_index);

    always_ff @(posedge clk) begin
        if (reset) begin
            configured <= 0;
            loaded <= 0;
            busy <= 0;
            error <= 0;
            saturated <= 0;
            current_token <= 0;
            consecutive_outputs <= 0;
            context_count <= 0;
            logit_index <= 0;
            delay_count <= 0;
            reset_count <= reset_count + 1;
        end else begin
            if (weight_valid && weight_ready) begin
                if (weight_value != (loaded == 0 ? 32'h12345678 : 32'h98765432))
                    $fatal(1, "Synthetic model load received unexpected word");
                loaded <= loaded + 1'b1;
                if (loaded == 1) configured <= 1;
            end
            if (clear_context && !busy) begin
                context_count <= 0;
                consecutive_outputs <= 0;
                clear_count <= clear_count + 1;
            end
            if (token_valid && token_ready) begin
                if (accepted_tokens >= 1024) $fatal(1, "Token trace full");
                input_token[accepted_tokens] <= int'(token);
                input_context[accepted_tokens] <= int'(context_count);
                accepted_tokens <= accepted_tokens + 1;
                current_token <= token;
                if (context_count == 1 && token == 11) consecutive_outputs <= 1;
                context_count <= context_count + 1'b1;
                logit_index <= 0;
                delay_count <= 3;
                busy <= 1;
            end
            if (delay_count != 0) delay_count <= delay_count - 1'b1;
            if (logit_valid && logit_ready && !error) begin
                accepted_scores <= accepted_scores + 1;
                if (logit_index == 319) begin
                    busy <= 0;
                    if (!consecutive_outputs && current_token == 39) saturated <= 1;
                end else begin
                    logit_index <= logit_index + 1'b1;
                    if (logit_index == 7 || logit_index == 167 || logit_index == 318)
                        delay_count <= 2;
                    if (!consecutive_outputs && logit_index == 12) begin
                        case (current_token)
                            33: error <= 1;
                            36: saturated <= 1;
                            37: logit_index <= 14;
                            default: ;
                        endcase
                    end
                end
            end
        end
    end
endmodule
