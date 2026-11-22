`timescale 1ns/1ps
module down_projection_check #(parameter int INPUTS=128, OUTPUTS=32)(
    output bit done
);
    bit clk = 0;
    always #5 clk = !clk;

    bit reset = 1;
    bit input_valid = 0, weight_valid = 0, start = 0;
    bit [7:0] input_address, weight_address;
    bit [8:0] weight_row;
    logic signed [15:0] input_value, weight_value;
    bit [1:0] result_ready = 0;
    wire [1:0] input_ready, weight_ready, start_ready, busy, result_valid, saturated, step_valid;
    wire signed [15:0] result[2], step_input[2], step_weight[2];
    wire [8:0] result_row[2], step_row[2];
    wire [7:0] step_index[2];
    wire signed [31:0] step_product[2];
    wire signed [47:0] step_sum[2];

    dense #(.INPUTS(INPUTS),.OUTPUTS(OUTPUTS),.SHIFT(15)) control(
        .clk,.reset,.input_valid,.input_ready(input_ready[0]),.input_address,.input_value,
        .weight_valid,.weight_ready(weight_ready[0]),.weight_row,.weight_address,.weight_value,
        .start,.start_ready(start_ready[0]),.busy(busy[0]),.result_valid(result_valid[0]),
        .result_ready(result_ready[0]),.result(result[0]),.result_row(result_row[0]),.saturated(saturated[0]),
        .step_valid(step_valid[0]),.step_index(step_index[0]),.step_row(step_row[0]),.step_input(step_input[0]),
        .step_weight(step_weight[0]),.step_product(step_product[0]),.step_sum(step_sum[0])
    );
    dense_ff_down_pipeline #(.INPUTS(INPUTS),.OUTPUTS(OUTPUTS),.SHIFT(15)) candidate(
        .clk,.reset,.input_valid,.input_ready(input_ready[1]),.input_address,.input_value,
        .weight_valid,.weight_ready(weight_ready[1]),.weight_row,.weight_address,.weight_value,
        .start,.start_ready(start_ready[1]),.busy(busy[1]),.result_valid(result_valid[1]),
        .result_ready(result_ready[1]),.result(result[1]),.result_row(result_row[1]),.saturated(saturated[1]),
        .step_valid(step_valid[1]),.step_index(step_index[1]),.step_row(step_row[1]),.step_input(step_input[1]),
        .step_weight(step_weight[1]),.step_product(step_product[1]),.step_sum(step_sum[1])
    );

    localparam int TERMS=INPUTS*OUTPUTS;
    logic signed [15:0] inputs[INPUTS], weights[TERMS];
    logic [79:0] terms[TERMS];
    logic [16:0] results[OUTPUTS];

    task automatic load_memories;
        for (int i=0; i<TERMS; i++) begin
            @(negedge clk);
            input_valid = i < INPUTS;
            input_address = 8'(i);
            if (input_valid) input_value = inputs[i];
            weight_valid = 1;
            weight_row = 9'(i/INPUTS);
            weight_address = 8'(i%INPUTS);
            weight_value = weights[i];
            @(posedge clk);
            if ((input_valid && input_ready!=2'b11) || weight_ready!=2'b11)
                $fatal(1,"Valid load was excluded");
        end
        @(negedge clk);
        input_valid = 1; input_address = 8'(INPUTS);
        weight_valid = 1; weight_address = 8'(INPUTS); weight_row = 0;
        @(posedge clk);
        if (input_ready!=0 || weight_ready!=0 || start_ready!=0)
            $fatal(1,"Illegal address or concurrent launch accepted");
        @(negedge clk);
        input_valid = 0; weight_row = 9'(OUTPUTS); weight_address = 0;
        @(posedge clk);
        if (weight_ready!=0)
            $fatal(1,"Illegal row accepted");
        @(negedge clk);
        weight_valid = 0;
    endtask

    task automatic launch;
        @(negedge clk);
        if (start_ready!=2'b11)
            $fatal(1,"Projection unavailable at start");
        start = 1;
        @(posedge clk);
        #1;
        if (busy!=2'b11)
            $fatal(1,"Launch failed");
    endtask

    task automatic check_pass(input bit stall_output);
        int term_count[2], rows[2], held[2], counted[2];
        int stalled_clocks = 0;
        for (int row=0; row<OUTPUTS; row++)
            if (stall_output) stalled_clocks += 2+row%4;
        launch();
        while (rows[0]!=OUTPUTS || rows[1]!=OUTPUTS) begin
            @(negedge clk);
            start = 0;
            for (int arm=0; arm<2; arm++)
                result_ready[arm] = !stall_output || held[arm]>=2+rows[arm]%4;
            @(posedge clk);
            for (int arm=0; arm<2; arm++) begin
                if (rows[arm]<OUTPUTS) counted[arm]++;
                if (result_valid[arm]) begin
                    if (result_row[arm]!=9'(rows[arm]) ||
                        {saturated[arm],result[arm]}!==results[rows[arm]])
                        $fatal(1,"Wrong, unstable or misordered result %0d arm %0d",rows[arm],arm);
                    if (term_count[arm]!=(rows[arm]+1)*INPUTS)
                        $fatal(1,"Wrong number of arithmetic steps for row");
                    if (result_ready[arm]) begin
                        rows[arm]++;
                        held[arm]=0;
                    end else held[arm]++;
                end
            end
            #1;
            for (int arm=0; arm<2; arm++) begin
                if (step_valid[arm]) begin
                    int i = term_count[arm];
                    if (i>=TERMS || step_index[arm]!=8'(i%INPUTS) || step_row[arm]!=9'(i/INPUTS) ||
                        step_input[arm]!==inputs[i%INPUTS] || step_weight[arm]!==weights[i] ||
                        {step_product[arm],step_sum[arm]}!==terms[i])
                        $fatal(1,"Operand, product, index, accumulator or order differed at %0d arm %0d",i,arm);
                    term_count[arm]++;
                end
                if (counted[arm]>OUTPUTS*(2*INPUTS+8))
                    $fatal(1,"Projection failed to finish");
            end
        end
        if (counted[0]!=OUTPUTS*(2*INPUTS+2)+stalled_clocks ||
            counted[1]!=OUTPUTS*(INPUTS+3)+stalled_clocks)
            $fatal(1,"Wrong cycle law %0d vs %0d, stalls %0d",counted[0],counted[1],stalled_clocks);
        $display("DOWN_PASS %0dx%0d stalled=%0d control=%0d candidate=%0d terms=%0d",
                 INPUTS,OUTPUTS,stall_output,counted[0],counted[1],TERMS);
    endtask

    task automatic cancel_at(input int phase);
        @(negedge clk);
        result_ready = 0;
        launch();
        case (phase)
            0: ;
            1: wait (step_valid[1] && step_index[1]==1);
            2: wait (result_valid[1]);
            default: $fatal(1,"Unknown phase");
        endcase
        @(negedge clk);
        start = 0; reset = 1;
        @(posedge clk);
        #1;
        if (busy!=0 || result_valid!=0 || step_valid!=0 || start_ready!=2'b11)
            $fatal(1,"Reset did not cancel at phase %0d",phase);
        @(negedge clk);
        reset = 0;
        check_pass(1);
        $display("DOWN_RESET_PASS phase=%0d",phase);
    endtask

    initial begin
        string fixture;
        if (!$value$plusargs("FIXTURES=%s",fixture))
            $fatal(1,"Provide fixtures");
        fixture = {fixture,$sformatf("/%0dx%0d/",INPUTS,OUTPUTS)};
        $readmemh({fixture,"inputs.hex"},inputs);
        $readmemh({fixture,"weights.hex"},weights);
        $readmemh({fixture,"terms.hex"},terms);
        $readmemh({fixture,"results.hex"},results);
        repeat (2) @(negedge clk);
        reset = 0;
        load_memories();
        check_pass(0);
        check_pass(1);
        if (INPUTS==128)
            for (int phase=0; phase<3; phase++) cancel_at(phase);
        done = 1;
    end
endmodule

module ff_down_tb;
    wire done_full, done_odd, done_one;
    down_projection_check full_size(done_full);
    down_projection_check #(.INPUTS(5),.OUTPUTS(3)) odd_size(done_odd);
    down_projection_check #(.INPUTS(1),.OUTPUTS(3)) single_input(done_one);
    initial begin
        wait (done_full && done_odd && done_one);
        $finish;
    end
endmodule
