`timescale 1ns/1ps
module logits_component_case #(parameter int WIDTH=32)(output bit done);
    bit clk=0, reset=1, start=0, input_valid=0, weight_valid=0, result_ready=0, checking=0;
    always #5 clk=!clk;

    logic [7:0] input_address=0, weight_address=0;
    logic [8:0] weight_row=0;
    logic signed [15:0] input_value=0, weight_value=0;
    logic [1:0] input_ready, weight_ready, start_ready, busy, result_valid, saturated, step_valid;
    logic [8:0] result_row[2], step_row[2];
    logic [7:0] step_index[2];
    logic signed [WIDTH-1:0] result[2];
    logic signed [15:0] step_input[2], step_weight[2];
    logic signed [31:0] step_product[2];
    logic signed [47:0] step_sum[2];
    logic signed [15:0] inputs[32], weights[10240];
    logic signed [31:0] products[10240];
    logic signed [47:0] sums[10240];
    logic [32:0] answers[320];
    int cycle=0, row_count[2], pair_count[2], last_cycle[2];
    string fixtures;
    localparam int PAIRS=10240, ROWS=320;

    dense #(.INPUTS(32),.OUTPUTS(320),.SHIFT(8),.RESULT_BITS(WIDTH)) arm_0 (
        .clk,.reset,.start,.input_valid,.input_address,.input_value,
        .weight_valid,.weight_address,.weight_row,.weight_value,.result_ready,
        .start_ready(start_ready[0]),.input_ready(input_ready[0]),
        .weight_ready(weight_ready[0]),.busy(busy[0]),.result_valid(result_valid[0]),
        .result(result[0]),.result_row(result_row[0]),.saturated(saturated[0]),
        .step_valid(step_valid[0]),.step_index(step_index[0]),.step_row(step_row[0]),
        .step_input(step_input[0]),.step_weight(step_weight[0]),
        .step_product(step_product[0]),.step_sum(step_sum[0]));

    logits_dense #(.INPUTS(32),.OUTPUTS(320),.SHIFT(8),.RESULT_BITS(WIDTH)) arm_1 (
        .clk,.reset,.start,.input_valid,.input_address,.input_value,
        .weight_valid,.weight_address,.weight_row,.weight_value,.result_ready,
        .start_ready(start_ready[1]),.input_ready(input_ready[1]),
        .weight_ready(weight_ready[1]),.busy(busy[1]),.result_valid(result_valid[1]),
        .result(result[1]),.result_row(result_row[1]),.saturated(saturated[1]),
        .step_valid(step_valid[1]),.step_index(step_index[1]),.step_row(step_row[1]),
        .step_input(step_input[1]),.step_weight(step_weight[1]),
        .step_product(step_product[1]),.step_sum(step_sum[1]));

    task automatic check_row(input int arm, row);
        if(result_row[arm]!==9'(row) || result[arm]!==answers[row][WIDTH-1:0] ||
           saturated[arm]!==answers[row][32])
            $fatal(1,"Width %0d arm %0d row %0d result %h saturation %b expected %h",
                WIDTH,arm,row,result[arm],saturated[arm],answers[row]);
    endtask

    always @(posedge clk) begin
        cycle++;
        if(checking) begin
            for(int arm=0;arm<2;arm++)begin
                if(step_valid[arm])begin
                    int i;
                    i=pair_count[arm];
                    if(i>=PAIRS || step_row[arm]!==9'(i/32) || step_index[arm]!==8'(i%32) ||
                        step_input[arm]!==inputs[i%32] || step_weight[arm]!==weights[i] ||
                        step_product[arm]!==products[i] || step_sum[arm]!==sums[i])
                        $fatal(1,"Width %0d arm %0d step %0d differs",WIDTH,arm,i);
                    pair_count[arm]++;
                end
                if(result_valid[arm] && result_ready)begin
                    if(row_count[arm]>=ROWS) $fatal(1,"Unexpected extra result");
                    check_row(arm,row_count[arm]);
                    row_count[arm]++;
                    last_cycle[arm]=cycle;
                end
            end
        end
    end

    task automatic tick;
        @(negedge clk);
    endtask

    task automatic launch;
        if(start_ready!==2'b11) $fatal(1,"Not idle for launch");
        start=1;
        tick();
        start=0;
    endtask

    task automatic cancel;
        reset=1;
        tick();
        reset=0;
        #1;
        if(busy!==0 || result_valid!==0 || step_valid!==0 || start_ready!==2'b11)
            $fatal(1,"Reset did not cancel work");
        tick();
    endtask

    initial begin
        if(!$value$plusargs("FIXTURES=%s",fixtures)) $fatal(1,"Missing integer oracle fixtures");
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
            if(input_ready!==2'b11 || start_ready!==0) $fatal(1,"Input load arbitration differs");
            tick();
        end
        input_valid=0;
        weight_valid=1;
        for(int i=0;i<PAIRS;i++)begin
            weight_row=9'(i/32);
            weight_address=8'(i%32);
            weight_value=weights[i];
            #1;
            if(weight_ready!==2'b11 || start_ready!==0) $fatal(1,"Weight load arbitration differs");
            tick();
        end
        weight_row=9'(ROWS);
        #1;
        if(weight_ready!==0) $fatal(1,"Out-of-range weight row accepted");
        tick();
        weight_valid=0;
        input_address=32;
        input_valid=1;
        #1;
        if(input_ready!==0) $fatal(1,"Out-of-range input accepted");
        tick();
        input_valid=0;
        tick();

        // Retire all 10,240 pairs in both arms at equal downstream readiness.
        checking=1;
        result_ready=1;
        launch();
        while(row_count[0]!=ROWS || row_count[1]!=ROWS) tick();
        checking=0;
        if(pair_count[0]!=PAIRS || pair_count[1]!=PAIRS || last_cycle[0]-last_cycle[1]!=9920)
            $fatal(1,"Unexpected full-shape cycle or pair counts");

        // Hold the first result across stalls and attempt simultaneous loads/restart.
        result_ready=0;
        launch();
        while(result_valid!==2'b11) tick();
        input_address=0;
        weight_address=0;
        weight_row=0;
        input_value=123;
        weight_value=456;
        input_valid=1;
        weight_valid=1;
        start=1;
        repeat(11)begin
            #1;
            if(result_valid!==2'b11 || step_valid!==0 || input_ready!==0 ||
               weight_ready!==0 || start_ready!==0) $fatal(1,"Busy stall handshakes differ");
            check_row(0,0);
            check_row(1,0);
            tick();
        end
        input_valid=0;
        weight_valid=0;
        start=0;
        cancel();

        // A reset at every active step of the first pipeline row, plus a stalled output.
        for(int delay=0;delay<=40;delay++)begin
            launch();
            repeat(delay) tick();
            cancel();
            launch();
            while(result_valid!==2'b11) tick();
            check_row(0,0);
            check_row(1,0);
            cancel();
        end

        // The first row has retired when the candidate starts reading the second.
        result_ready=1;
        launch();
        while(!result_valid[1]) tick();
        tick();
        cancel();
        result_ready=0;
        launch();
        while(result_valid!==2'b11) tick();
        check_row(0,0);
        check_row(1,0);
        cancel();
        done=1;
    end
endmodule

module logits_component_tb;
    wire full_done, clipped_done;
    logits_component_case #(.WIDTH(32)) full_width(full_done);
    logits_component_case #(.WIDTH(16)) narrow_width(clipped_done);
    initial begin
        wait(full_done && clipped_done);
        $display("PASS full and narrow exact logits, ordered trace and reset/stall coverage");
        $finish;
    end
    initial begin
        #10000000;
        $fatal(1,"Component watchdog");
    end
endmodule
