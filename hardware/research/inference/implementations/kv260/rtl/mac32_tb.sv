// Behavioural testbench; excluded from synthesis. Same suite supports 1/32/96 rows.
`timescale 1ns/1ps
module mac32_tb #(parameter integer ROWS = 1);
    localparam integer ROW_BITS = (ROWS > 1) ? $clog2(ROWS) : 1;
    localparam integer RESET_PROBES = (ROWS == 96) ? 8 : ((ROWS > 1) ? 6 : 5);
    logic clk;
    initial begin clk = 0; forever #5 clk = !clk; end
    logic reset = 1, load_valid = 0, start = 0, result_ready = 0;
    logic load_ready, start_ready, busy, result_valid, saturated, step_valid;
    logic [4:0] load_address = 0, step_index;
    logic [ROW_BITS-1:0] load_row = 0, result_row, step_row;
    logic signed [15:0] load_input = 0, load_weight = 0, result, step_input, step_weight;
    logic signed [31:0] step_product;
    logic signed [47:0] step_sum;
    mac32 #(.ROWS(ROWS)) dut (.*);
    localparam integer MAX_CASES = 256;
    logic signed [15:0] xs [0:MAX_CASES*32-1], ws [0:MAX_CASES*ROWS*32-1];
    logic signed [15:0] answers [0:MAX_CASES*ROWS-1];
    logic [7:0] clips [0:MAX_CASES*ROWS-1];
    integer cases, csv, cycle = 0, case_id = -1, passed = 0;
    string xfile, wfile, answerfile, clipfile, csvfile, wavefile;

    task automatic tick;
        @(posedge clk); #1;
        cycle = int'($time / 10);
        $fwrite(csv, "%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
            case_id, cycle, dut.state, busy, start_ready, load_ready, load_valid,
            start, result_ready, result_valid, result, saturated, dut.address,
            dut.operand_x, dut.operand_w, dut.product, dut.accumulator,
            step_valid, step_index, step_product, step_sum, dut.row, result_row, step_row);
    endtask

    task automatic load_vector(input integer id);
        for (integer r = 0; r < ROWS; r = r + 1) begin
            for (integer j = 0; j < 32; j = j + 1) begin
                @(negedge clk);
                load_valid = 1; start = 0; result_ready = 0;
                load_row = ROW_BITS'(r); load_address = 5'(j);
                // Only row zero may update the shared input memory.
                load_input = r == 0 ? xs[id*32+j] : 16'sh4321;
                load_weight = ws[(id*ROWS+r)*32+j];
                tick();
                if (!load_ready || busy) $fatal(1, "Loading was not ready while idle");
            end
        end
        @(negedge clk); load_valid = 0;
    endtask

    task automatic launch;
        start = 1; load_valid = 0; result_ready = 0;
        tick();
        if (!busy || start_ready || load_ready) $fatal(1, "Start handshake failed");
        @(negedge clk); start = 0;
    endtask

    task automatic run_case(input integer id, input integer label_id, input bit reload);
        integer seen, elapsed;
        longint signed total, expected_product;
        case_id = label_id;
        if (reload) load_vector(id);
        launch();
        for (integer r = 0; r < ROWS; r = r + 1) begin
            seen = 0; elapsed = 0; total = 0;
            while (!result_valid) begin
                // Busy requests must not restart or overwrite either memory.
                load_valid = 1; load_address = 5'(elapsed); load_row = ROW_BITS'(r);
                load_input = 16'sh1234; load_weight = -16'sd1234;
                start = (elapsed % 3) == 0;
                tick(); elapsed = elapsed + 1;
                if (load_ready || start_ready || !busy) $fatal(1, "Busy handshake failed");
                if (step_valid) begin
                    if (seen >= 32 || int'(step_index) != seen || int'(step_row) != r)
                        $fatal(1, "Wrong row/term index");
                    expected_product = longint'(xs[id*32+seen]) * longint'(ws[(id*ROWS+r)*32+seen]);
                    total = total + expected_product;
                    if (step_input != xs[id*32+seen] || step_weight != ws[(id*ROWS+r)*32+seen] ||
                        longint'(step_product) != expected_product || longint'(step_sum) != total)
                        $fatal(1, "Term mismatch: case %0d row %0d term %0d", id, r, seen);
                    seen = seen + 1;
                end
                if (elapsed > 70) $fatal(1, "No result within bounded row latency");
                @(negedge clk);
            end
            if (seen != 32 || elapsed != 65) $fatal(1, "Unexpected row steps or latency");
            if (int'(result_row) != r || result != answers[id*ROWS+r] || saturated != clips[id*ROWS+r][0])
                $fatal(1, "Output mismatch: case %0d row %0d got %0d", id, r, result);
            for (integer stall = 0; stall < 1 + (id+r)%5; stall = stall + 1) begin
                start = 1; load_valid = 1;
                tick();
                if (!result_valid || !busy || step_valid || load_ready || start_ready ||
                    int'(result_row) != r || result != answers[id*ROWS+r] || saturated != clips[id*ROWS+r][0])
                    $fatal(1, "Output/row tag changed during backpressure");
                @(negedge clk);
            end
            start = 0; load_valid = 0; result_ready = 1;
            tick();
            if (result_valid || step_valid || busy != (r < ROWS-1))
                $fatal(1, "Result handshake or early matrix completion failed");
            @(negedge clk); result_ready = 0;
        end
        passed = passed + 1;
    endtask

    task automatic abort_after(input integer edges);
        case_id = -1;
        load_vector(0); launch(); result_ready = 1;
        repeat (edges) begin tick(); @(negedge clk); end
        reset = 1; load_valid = 0; start = 0;
        tick();
        if (busy || result_valid || step_valid || dut.accumulator != 0 || result != 0 || result_row != 0)
            $fatal(1, "Reset did not cancel the matrix transaction");
        @(negedge clk); reset = 0; result_ready = 0;
    endtask

    initial begin
        if (!$value$plusargs("CASES=%d", cases) || cases <= 0 || cases > MAX_CASES ||
            !$value$plusargs("X=%s", xfile) || !$value$plusargs("W=%s", wfile) ||
            !$value$plusargs("ANSWERS=%s", answerfile) || !$value$plusargs("CLIPS=%s", clipfile) ||
            !$value$plusargs("CSV=%s", csvfile) || !$value$plusargs("VCD=%s", wavefile))
            $fatal(1, "Missing or invalid fixture arguments");
        $readmemh(xfile, xs, 0, cases*32-1);
        $readmemh(wfile, ws, 0, cases*ROWS*32-1);
        $readmemh(answerfile, answers, 0, cases*ROWS-1);
        $readmemh(clipfile, clips, 0, cases*ROWS-1);
        csv = $fopen(csvfile, "w");
        if (csv == 0) $fatal(1, "Cannot open trace");
        $fwrite(csv,"case,cycle,phase,busy,start_ready,load_ready,load_valid,start,result_ready,result_valid,result,saturated,address,operand_x,operand_w,product,accumulator,step_valid,step_index,step_product,step_sum,row,result_row,step_row\n");
        $dumpfile(wavefile); $dumpvars(0, dut);
        tick(); @(negedge clk); reset = 0;
        start = 1; load_valid = 1; tick();
        if (busy || load_ready || start_ready) $fatal(1, "Conflicting idle requests accepted");
        @(negedge clk); start = 0; load_valid = 0;
        if (ROWS == 96 || ROWS == 1) begin
            // Exercise every unrepresentable row in the available row address space.
            for (integer invalid_row = ROWS; invalid_row < 2**ROW_BITS; invalid_row = invalid_row + 1) begin
                load_valid = 1; load_row = ROW_BITS'(invalid_row); tick();
                if (load_ready || busy) $fatal(1, "Out-of-range weight load was accepted");
                @(negedge clk);
            end
            load_valid = 0; load_row = 0;
        end
        for (integer id = 0; id < cases; id = id + 1) run_case(id, id, 1);
        for (integer probe = 0; probe < RESET_PROBES; probe = probe + 1) begin
            case (probe)
                0: abort_after(0);
                1: abort_after(1);
                2: abort_after(7);
                3: abort_after(64);
                4: abort_after(65);
                5: abort_after(2*66+7); // Later-row work.
                6: abort_after(32*66);  // Q complete, entering K.
                7: abort_after(64*66+7); // Q/K complete, inside V.
            endcase
            run_case(0, cases+probe, 0);
        end
        run_case(0, cases+RESET_PROBES, 0);
        $fclose(csv);
        $display("PASS full_transactions=%0d output_rows=%0d reset_probes=%0d row_latency_edges=65", passed, ROWS, RESET_PROBES);
        $finish;
    end
    initial begin #20000000; $fatal(1, "Testbench absolute simulation-time limit"); end
endmodule
