// Behavioural tests only. Independent Python fixtures supply every expected value.
`timescale 1ns/1ps
module qk_rope_tb;
    logic clk;
    initial begin clk = 0; forever #5 clk = !clk; end
    logic reset = 1, load_valid = 0, coefficient_valid = 0, start = 0, result_ready = 0;
    logic load_ready, coefficient_ready, start_ready, busy, result_valid, step_valid;
    logic [5:0] load_index = 0, result_index_a, result_index_b;
    logic signed [15:0] load_value = 0, load_cosine = 0, load_sine = 0;
    logic [7:0] coefficient_position = 0;
    logic [2:0] coefficient_pair = 0;
    logic [8:0] token_position = 0;
    logic [4:0] result_pair, step_pair;
    logic signed [15:0] result_a, result_b, step_input, step_coefficient;
    logic [1:0] saturated, step_kind;
    logic signed [31:0] step_product;
    logic signed [47:0] step_total;
    qk_rope dut (.*);
    localparam integer MAX_CASES = 1024, RESET_PROBES = 9;
    logic signed [15:0] xs [0:MAX_CASES*64-1], cs [0:MAX_CASES*8-1], ss [0:MAX_CASES*8-1];
    logic signed [15:0] answers [0:MAX_CASES*64-1];
    logic [7:0] clips [0:MAX_CASES*32-1];
    logic [8:0] positions [0:MAX_CASES-1];
    logic signed [15:0] table_cosines [0:2047], table_sines [0:2047];
    integer csv, cases, cycle = 0, case_id = -1, passed = 0;
    string xfile, cfile, sfile, answerfile, clipfile, positionfile, tcfile, tsfile, csvfile, wavefile;
    task automatic tick;
        @(posedge clk); #1;
        cycle = int'($time/10);
        $fwrite(csv,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
            case_id,cycle,dut.state,busy,start_ready,load_ready,coefficient_ready,result_ready,result_valid,
            result_pair,result_index_a,result_index_b,result_a,result_b,saturated,step_valid,step_pair,step_kind,
            step_input,step_coefficient,step_product,step_total,dut.a,dut.b,dut.cosine,dut.sine,
            dut.combined_a,dut.combined_b,dut.position);
    endtask
    task automatic load_fixture(input integer id);
        for (integer i = 0; i < 64; i = i+1) begin
            @(negedge clk); load_valid = 1; coefficient_valid = 0; start = 0; result_ready = 0;
            load_index = 6'(i); load_value = xs[id*64+i]; tick();
            if (!load_ready || busy) $fatal(1,"Input loading not ready");
        end
        for (integer j = 0; j < 8; j = j+1) begin
            @(negedge clk); load_valid = 0; coefficient_valid = 1;
            coefficient_position = positions[id][7:0]; coefficient_pair = 3'(j);
            load_cosine = cs[id*8+j]; load_sine = ss[id*8+j]; tick();
            if (!coefficient_ready || busy) $fatal(1,"Coefficient loading not ready");
        end
        @(negedge clk); coefficient_valid = 0;
    endtask
    task automatic launch(input integer id);
        if (id<0 || id>=cases) $fatal(1,"Invalid launch fixture");
        token_position = positions[id]; start = 1; load_valid = 0; coefficient_valid = 0; result_ready = 0;
        tick();
        if (!busy || start_ready || load_ready || coefficient_ready) $fatal(1,"Start failed");
        @(negedge clk); start = 0;
    endtask
    task automatic run_case(input integer id, input integer label_id, input bit reload);
        integer elapsed, seen, ia, ib;
        longint signed expected_product, expected_total, previous;
        case_id = label_id;
        if (reload) load_fixture(id);
        launch(id);
        for (integer pair_number = 0; pair_number < 32; pair_number = pair_number+1) begin
            seen = 0; elapsed = 0; previous = 0;
            ia = (pair_number/16)*32 + ((pair_number/8)%2)*16 + pair_number%8;
            ib = ia+8;
            while (!result_valid) begin
                // Changing the external position and attempted writes must not affect busy work.
                load_valid = 1; coefficient_valid = 1; start = 1; token_position = 9'd511;
                load_value = -16'sd1234; load_cosine = 16'sd37; load_sine = 16'sd39;
                tick(); elapsed = elapsed+1;
                if (!busy || start_ready || load_ready || coefficient_ready) $fatal(1,"Busy request accepted");
                if (step_valid) begin
                    if (int'(step_pair) != pair_number || int'(step_kind) != seen || seen >= 4) $fatal(1,"Wrong step tag");
                    expected_product = longint'(xs[id*64 + ((seen==0 || seen==3) ? ia : ib)]) *
                                       ((seen==0 || seen==2) ? longint'(cs[id*8+pair_number%8]) : longint'(ss[id*8+pair_number%8]));
                    expected_total = (seen==0 || seen==2) ? expected_product :
                                     seen==1 ? previous-expected_product : previous+expected_product;
                    if (longint'(step_product) != expected_product || longint'(step_total) != expected_total)
                        $fatal(1,"Product/combined mismatch: case %0d pair %0d step %0d",id,pair_number,seen);
                    previous = expected_product; seen = seen+1;
                end
                if (elapsed > 8) $fatal(1,"RoPE latency exceeded");
                @(negedge clk);
            end
            if (seen != 4 || elapsed != 6 || int'(result_pair) != pair_number ||
                int'(result_index_a) != ia || int'(result_index_b) != ib ||
                result_a != answers[id*64+ia] || result_b != answers[id*64+ib] || saturated != clips[id*32+pair_number][1:0])
                $fatal(1,"RoPE result/tag mismatch: case %0d pair %0d",id,pair_number);
            for (integer stall = 0; stall < 1+(id+pair_number)%4; stall = stall+1) begin
                tick();
                if (!result_valid || !busy || step_valid || load_ready || coefficient_ready || start_ready ||
                    int'(result_pair) != pair_number || int'(result_index_a) != ia || int'(result_index_b) != ib ||
                    result_a != answers[id*64+ia] || result_b != answers[id*64+ib] || saturated != clips[id*32+pair_number][1:0])
                    $fatal(1,"RoPE output changed during backpressure");
                @(negedge clk);
            end
            load_valid = 0; coefficient_valid = 0; start = 0; result_ready = 1;
            tick();
            if (result_valid || step_valid || busy != (pair_number < 31)) $fatal(1,"Early completion/handshake");
            @(negedge clk); result_ready = 0;
        end
        passed = passed+1;
    endtask
    task automatic abort_after(input integer edges);
        case_id = -1; load_fixture(0); launch(0); result_ready = 1;
        repeat (edges) begin tick(); @(negedge clk); end
        reset = 1; load_valid = 0; coefficient_valid = 0; start = 0; tick();
        if (busy || result_valid || step_valid || result_a != 0 || result_b != 0 ||
            result_pair != 0 || dut.combined_a != 0 || dut.combined_b != 0)
            $fatal(1,"Reset did not cancel RoPE");
        @(negedge clk); reset = 0; result_ready = 0;
    endtask
    initial begin
        if (!$value$plusargs("CASES=%d",cases) || cases<=0 || cases>MAX_CASES ||
            !$value$plusargs("X=%s",xfile) || !$value$plusargs("C=%s",cfile) || !$value$plusargs("S=%s",sfile) ||
            !$value$plusargs("ANSWERS=%s",answerfile) || !$value$plusargs("CLIPS=%s",clipfile) ||
            !$value$plusargs("POSITIONS=%s",positionfile) || !$value$plusargs("TC=%s",tcfile) || !$value$plusargs("TS=%s",tsfile) ||
            !$value$plusargs("CSV=%s",csvfile) || !$value$plusargs("VCD=%s",wavefile)) $fatal(1,"Missing fixtures");
        $readmemh(xfile,xs,0,cases*64-1); $readmemh(cfile,cs,0,cases*8-1); $readmemh(sfile,ss,0,cases*8-1);
        $readmemh(answerfile,answers,0,cases*64-1); $readmemh(clipfile,clips,0,cases*32-1);
        $readmemh(positionfile,positions,0,cases-1); $readmemh(tcfile,table_cosines); $readmemh(tsfile,table_sines);
        csv = $fopen(csvfile,"w"); if (csv==0) $fatal(1,"Cannot open CSV");
        $fwrite(csv,"case,cycle,phase,busy,start_ready,load_ready,coefficient_ready,result_ready,result_valid,pair,index_a,index_b,result_a,result_b,saturated,step_valid,step_pair,step_kind,step_input,step_coefficient,step_product,step_total,a,b,cosine,sine,combined_a,combined_b,position\n");
        $dumpfile(wavefile); $dumpvars(0,dut);
        tick(); @(negedge clk); reset = 0;
        // Load the complete pinned table, then use each position during the sweep.
        for (integer i = 0; i < 2048; i = i+1) begin
            coefficient_valid = 1; coefficient_position = 8'(i/8); coefficient_pair = 3'(i%8);
            load_cosine = table_cosines[i]; load_sine = table_sines[i]; tick();
            if (!coefficient_ready) $fatal(1,"Table loading failed");
            @(negedge clk);
        end
        coefficient_valid = 1; load_valid = 1; start = 1; tick();
        if (busy || start_ready || load_ready || coefficient_ready) $fatal(1,"Conflicting requests accepted");
        @(negedge clk); start = 0; tick();
        if (load_ready || coefficient_ready) $fatal(1,"Conflicting loads accepted");
        @(negedge clk); coefficient_valid = 0; load_valid = 0;
        for (integer invalid_position = 256; invalid_position < 512; invalid_position = invalid_position+1) begin
            token_position = 9'(invalid_position); start = 1; tick();
            if (start_ready || busy) $fatal(1,"Invalid position accepted");
            @(negedge clk);
        end
        start = 0;
        for (integer id = 0; id < cases; id = id+1) run_case(id,id,1);
        for (integer probe = 0; probe < RESET_PROBES; probe = probe+1) begin
            case (probe)
                0: abort_after(0);
                1: abort_after(1);
                2: abort_after(2);
                3: abort_after(3);
                4: abort_after(4);
                5: abort_after(5);
                6: abort_after(6);
                7: abort_after(16*7); // Entering the K bank.
                8: abort_after(31*7+4); // Last pair arithmetic.
            endcase
            run_case(0,cases+probe,0);
        end
        run_case(0,cases+RESET_PROBES,0);
        $fclose(csv);
        $display("PASS rope_transactions=%0d reset_probes=%0d pair_latency_edges=6",passed,RESET_PROBES);
        $finish;
    end
    initial begin #20000000; $fatal(1,"Absolute simulation-time limit"); end
endmodule
