`timescale 1ns/1ps
module logits_lanes_case #(parameter int LANES=2, WIDTH=32)(output bit done);
    bit clk=0, reset=1, start=0, input_valid=0, weight_valid=0, result_ready=0, checking=0;
    always #5 clk=!clk;

    logic [7:0] input_address=0, weight_address=0;
    logic [8:0] weight_row=0, row;
    logic signed [15:0] input_value=0, weight_value=0;
    logic input_ready, weight_ready, start_ready, busy, result_valid, saturated;
    logic signed [WIDTH-1:0] result;
    logic signed [15:0] inputs[32], weights[10240];
    logic signed [31:0] products[10240];
    logic signed [47:0] sums[10240];
    logic [32:0] answers[320];
    int cycle=0, row_count=0, mac_count=0, last_cycle=0, launch_cycle=0;
    string fixtures;
    localparam int PAIRS=10240, ROWS=320, GROUPS=320/LANES;
    localparam int PROJECTION_CYCLES=(34+LANES)*GROUPS;

    logits_parallel #(.LANES(LANES),.RESULT_BITS(WIDTH)) dut (
        .clk,.reset,.start,.input_valid,.input_address,.input_value,
        .weight_valid,.weight_address,.weight_row,.weight_value,.result_ready,
        .start_ready,.input_ready,.weight_ready,.busy,.result_valid,
        .result,.result_row(row),.saturated);

    task automatic expect_row(input int number);
        if(!result_valid || row!==9'(number) || result!==answers[number][WIDTH-1:0] ||
           saturated!==answers[number][32])
            $fatal(1,"Lanes %0d width %0d row %0d has %0d/%h/%b expected %h",
                LANES,WIDTH,number,row,result,saturated,answers[number]);
    endtask

    // Each lane's bank output and next sum must come from exactly its own row.
    for(genvar lane=0;lane<LANES;lane++) begin : trace
        int seen=0;
        always @(posedge clk) if(checking && !reset && dut.state==3'd2) begin
            int coord, offset;
            coord=seen%32;
            offset=((seen/32)*LANES+lane)*32+coord;
            if(seen>=GROUPS*32 || dut.coordinate!==5'(coord) ||
                dut.group_index!==$clog2(GROUPS)'(seen/32) ||
                dut.input_operand!==inputs[coord] ||
                dut.bank[lane].weight_operand!==weights[offset] ||
                dut.bank[lane].product!==products[offset] ||
                dut.bank[lane].next_sum!==sums[offset])
                $fatal(1,"Lane %0d group %0d coordinate %0d trace differs",lane,seen/32,coord);
            seen++;
        end
    end

    always @(posedge clk) begin
        cycle++;
        if(checking) begin
            if(start && start_ready) launch_cycle=cycle;
            if(dut.state==3'd2) mac_count++;
            if(result_valid && result_ready) begin
                if(row_count>=ROWS) $fatal(1,"Extra output");
                expect_row(row_count);
                row_count++;
                last_cycle=cycle;
            end
        end
        if(!reset && busy && (input_ready || weight_ready || start_ready))
            $fatal(1,"Busy unit accepted unrelated work");
    end

    task automatic tick;
        @(negedge clk);
    endtask

    task automatic launch;
        if(!start_ready) $fatal(1,"Not idle for start");
        start=1;
        tick();
        start=0;
    endtask

    task automatic cancel;
        reset=1;
        tick();
        reset=0;
        #1;
        if(busy || result_valid || !start_ready) $fatal(1,"Reset did not cancel the projection");
        tick();
    endtask

    task automatic consume_group(input int base);
        for(int lane=0;lane<LANES;lane++)begin
            while(!result_valid) tick();
            expect_row(base+lane);
            if(dut.read_pair) $fatal(1,"Read reached next group before its first prime");
            repeat(lane+1)begin
                tick();
                expect_row(base+lane);
                if(dut.read_pair) $fatal(1,"Fetched past a stalled score");
            end
            result_ready=1;
            tick();
            result_ready=0;
        end
    endtask

    initial begin
        if(!$value$plusargs("FIXTURES=%s",fixtures)) $fatal(1,"Missing exact signed fixtures");
        $readmemh({fixtures,"/input.hex"},inputs);
        $readmemh({fixtures,"/weights.hex"},weights);
        $readmemh({fixtures,"/products.hex"},products);
        $readmemh({fixtures,"/sums.hex"},sums);
        $readmemh($sformatf("%s/answers%0d.hex",fixtures,WIDTH),answers);
        tick();
        reset=0;
        input_valid=1;
        for(int i=0;i<32;i++)begin
            input_address=8'(i);
            input_value=inputs[i];
            #1;
            if(!input_ready || start_ready) $fatal(1,"Input arbitration differs");
            tick();
        end
        input_address=32;
        #1;
        if(input_ready) $fatal(1,"Invalid input accepted");
        tick();
        input_valid=0;
        weight_valid=1;
        for(int i=0;i<PAIRS;i++)begin
            weight_row=9'(i/32);
            weight_address=8'(i%32);
            weight_value=weights[i];
            #1;
            if(!weight_ready || start_ready) $fatal(1,"Weight arbitration differs");
            tick();
        end
        weight_row=9'(ROWS);
        #1;
        if(weight_ready) $fatal(1,"Invalid weight row accepted");
        tick();
        weight_valid=0;
        tick();

        checking=1;
        result_ready=1;
        launch();
        while(row_count!=ROWS) tick();
        checking=0;
        if(busy || mac_count!=GROUPS*32 || last_cycle-launch_cycle!=PROJECTION_CYCLES)
            $fatal(1,"No-stall geometry differs: cycles %0d MAC states %0d",last_cycle-launch_cycle,mac_count);

        // Stall every output lane including the last lane of each group.
        // Reading for the next group must wait for the final handshake.
        result_ready=0;
        launch();
        for(int group=0;group<GROUPS;group++) consume_group(group*LANES);
        if(busy) $fatal(1,"Final group did not retire");
        tick();

        // Reset at prime, each MAC coordinate, round, every stream lane and
        // the next group boundary. Verify first group after a clean restart.
        for(int delay=0;delay<=34+LANES;delay++)begin
            result_ready=1;
            launch();
            repeat(delay) tick();
            cancel();
            result_ready=0;
            launch();
            consume_group(0);
            cancel();
        end
        done=1;
    end
endmodule

module logits_lanes_tb #(parameter int LANES=2);
    wire full_done, narrow_done;
    logits_lanes_case #(.LANES(LANES),.WIDTH(32)) full_width(full_done);
    logits_lanes_case #(.LANES(LANES),.WIDTH(16)) narrow_width(narrow_done);
    initial begin
        wait(full_done && narrow_done);
        $display("PASS %0d lanes, 320 ordered rows, exact lane traces, stalls and resets",LANES);
        $finish;
    end
    initial begin
        #10000000;
        $fatal(1,"Component watchdog");
    end
endmodule
