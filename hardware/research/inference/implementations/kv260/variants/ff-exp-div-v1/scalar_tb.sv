`timescale 1ns/1ps
module ff_exp_scalar_tb;
    bit clk = 0, reset = 1;
    always #5 clk = !clk;

    bit cmd_valid = 0, table_valid = 0, result_ready = 0;
    logic [2:0] op = 0;
    logic signed [63:0] a = 0, b = 0;
    logic [8:0] table_index = 0;
    logic [31:0] table_value = 0;
    wire cmd_ready[2], table_ready[2], result_valid[2], error[2];
    wire signed [63:0] result[2];
    wire signed [7:0] exponent[2];
    string fixtures;

    fixed_scalar control(
        .clk,.reset,.cmd_valid,.cmd_ready(cmd_ready[0]),.cmd_op(op),.cmd_a(a),.cmd_b(b),.cmd_shift(8'sd0),
        .table_valid,.table_ready(table_ready[0]),.table_kind(1'b0),.table_index,.table_value,
        .result_valid(result_valid[0]),.result_ready,.result(result[0]),.result_exponent(exponent[0]),.error(error[0])
    );
    fixed_scalar_ff_exp candidate(
        .clk,.reset,.cmd_valid,.cmd_ready(cmd_ready[1]),.cmd_op(op),.cmd_a(a),.cmd_b(b),.cmd_shift(8'sd0),
        .table_valid,.table_ready(table_ready[1]),.table_kind(1'b0),.table_index,.table_value,
        .result_valid(result_valid[1]),.result_ready,.result(result[1]),.result_exponent(exponent[1]),.error(error[1])
    );

    task automatic tick;
        @(posedge clk); #1;
    endtask

    task automatic clear_units;
        @(negedge clk); reset=1;
        tick();
        if (result_valid[0] || result_valid[1] || int'(candidate.state)!=0)
            $fatal(1,"Reset failed to cancel scalar work");
        @(negedge clk); reset=0;
    endtask

    task automatic launch_raw(input logic signed [63:0] n, input int role, input bit round_even);
        clear_units();
        case (role)
            0: candidate.exp_divide_start(n, round_even, candidate.EXP_POWER);
            1: candidate.exp_divide_start(n, round_even, candidate.EXP_INDEX);
            2: candidate.exp_divide_start(n, round_even, candidate.EXP_DONE);
            default: $fatal(1,"Unknown divider callsite in fixture");
        endcase
        #1;
    endtask

    task automatic test_raw(input logic signed [63:0] n, input int role, input bit round_even,
                            input logic [63:0] q, r, rounded, input int steps);
        launch_raw(n,role,round_even);
        if (int'(candidate.state)!=2 || int'(candidate.remaining)!=steps)
            $fatal(1,"Unexpected guarded start: n=%h role=%0d steps=%0d",n,role,steps);
        for (int i=0; i<steps; i++) begin
            if (int'(candidate.state)!=2) $fatal(1,"Early divider exit");
            tick();
        end
        if (int'(candidate.state)!=17 || candidate.quotient!==q || candidate.remainder!=={1'b0,r})
            $fatal(1,"Bad quotient/remainder: n=%h role=%0d wanted %h/%h",n,role,q,r);
        tick();
        if (candidate.math_value!==rounded || int'(candidate.state)!=(role==0 ? 5 : role==1 ? 6 : 10))
            $fatal(1,"Wrong sign/rounding/return: n=%h role=%0d expected %h",n,role,rounded);
    endtask

    task automatic load_exp_word(input logic [8:0] index, input logic [31:0] word_value);
        @(negedge clk);
        table_index=index; table_value=word_value; table_valid=1;
        #1;
        if (!table_ready[0] || !table_ready[1]) $fatal(1,"Legal table write blocked");
        tick();
        @(negedge clk); table_valid=0;
    endtask

    task automatic check_response(input int unit, input logic signed [63:0] expected, input bit fault);
        if (!result_valid[unit] || result[unit]!==expected || error[unit]!==fault || exponent[unit]!==0)
            $fatal(1,"Scalar response differs: lane=%0d op=%0d a=%h b=%h",unit,op,a,b);
    endtask

    task automatic test_interface(input logic [2:0] opcode, input logic signed [63:0] lhs, rhs, expected,
                                  input bit fault, input int saving, stall);
        int elapsed, cycles[2];
        cycles='{0,0};
        @(negedge clk);
        op=opcode; a=lhs; b=rhs; cmd_valid=1;
        #1;
        if (!cmd_ready[0] || !cmd_ready[1]) $fatal(1,"Scalar handshake unavailable");
        tick();
        @(negedge clk); cmd_valid=0; elapsed=1;
        while (cycles[0]==0 || cycles[1]==0) begin
            for (int unit=0; unit<2; unit++)
                if (result_valid[unit]) begin
                    check_response(unit,expected,fault);
                    if (cycles[unit]==0) cycles[unit]=elapsed;
                end
            if (cycles[0]==0 || cycles[1]==0) begin
                tick(); elapsed++;
                if (elapsed>140) $fatal(1,"Component command timed out");
            end
        end
        if (cycles[0]-cycles[1]!=saving) $fatal(1,"Scalar cycle law differs for opcode %0d",opcode);
        repeat (stall) begin
            tick();
            check_response(0,expected,fault); check_response(1,expected,fault);
            if (cmd_ready[0] || cmd_ready[1]) $fatal(1,"Accepted work while outputs were blocked");
        end
        @(negedge clk); result_ready=1;
        tick();
        if (result_valid[0] || result_valid[1]) $fatal(1,"Output did not retire");
        @(negedge clk); result_ready=0;
    endtask

    initial begin
        int fd, rc, rows, raw_rows, interface_rows;
        logic [63:0] x0, x1, x2, x3, x4, x5, x6;
        string line;
        if (!$value$plusargs("FIXTURES=%s",fixtures)) $fatal(1,"Missing fixture directory");
        if (!$value$plusargs("RAW_ROWS=%d",raw_rows) || !$value$plusargs("INTERFACE_ROWS=%d",interface_rows))
            $fatal(1,"Missing fixture counts");
        fd=$fopen({fixtures,"/raw.hex"},"r");
        if (!fd) $fatal(1,"No arithmetic fixtures");
        rows=0;
        while ($fgets(line,fd)!=0) begin
            rc=$sscanf(line,"%h %h %h %h %h %h %h",x0,x1,x2,x3,x4,x5,x6);
            if (rc!=7) $fatal(1,"Malformed raw fixture");
            test_raw(x0,int'(x1),x2[0],x3,x4,x5,int'(x6));
            rows++;
        end
        $fclose(fd);
        if (rows!=raw_rows) $fatal(1,"Missing raw divide case");

        // Cancel halfway through a shortened division and a 32-digit fallback.
        launch_raw(64'sd45426,0,1); tick(); clear_units();
        launch_raw(64'sh8000_0000_0000_0000,0,1); repeat (8) tick(); clear_units();

        fd=$fopen({fixtures,"/interface.hex"},"r");
        if (!fd) $fatal(1,"No command fixtures");
        rows=0;
        while ($fgets(line,fd)!=0) begin
            rc=$sscanf(line,"%h %h %h %h %h %h %h",x0,x1,x2,x3,x4,x5,x6);
            if (rc!=7) $fatal(1,"Malformed interface fixture");
            case (int'(x0))
                0: load_exp_word(x2[8:0],x3[31:0]);
                1: test_interface(x1[2:0],x2,x3,x4,x5[0],int'(x6),rows%5);
                2: clear_units();
                default: $fatal(1,"Unexpected fixture kind");
            endcase
            rows++;
        end
        $fclose(fd);
        if (rows!=interface_rows) $fatal(1,"Missing interface case");
        $display("PASS exact quotient/remainder, signed ties, generic latency, EXP tables, stalls and reset (%0d + %0d rows)",
                 raw_rows,interface_rows);
        $finish;
    end
    initial begin #50000000; $fatal(1,"Arithmetic fixture time bound"); end
endmodule
