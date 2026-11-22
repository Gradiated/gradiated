`timescale 1ns/1ps
module probability_scalar_tb;
    logic clk=0, reset=1, cmd_valid=0, result_ready=0, table_valid=0, table_kind=0;
    logic [1:0] cmd_ready, result_valid, table_ready, error;
    logic [2:0] op;
    logic signed [63:0] a,b,result[2];
    logic signed [7:0] shift, result_exponent[2];
    logic [8:0] table_index;
    logic [31:0] table_value;
    logic [4:0] state[2];
    logic [63:0] quotient[2];
    logic [64:0] remainder[2];

    always #5 clk = ~clk;
    for (genvar lane=0; lane<2; lane++) begin : arm
        fixed_scalar_attention_exp #(.SHORT_PROBABILITY_DIVISION(lane == 1)) dut (
            .clk,.reset,.cmd_valid,.cmd_ready(cmd_ready[lane]),.cmd_op(op),.cmd_a(a),.cmd_b(b),
            .cmd_shift(shift),.table_valid,.table_ready(table_ready[lane]),
            .table_kind,.table_index,.table_value,.result_valid(result_valid[lane]),.result_ready,
            .result(result[lane]),.result_exponent(result_exponent[lane]),.error(error[lane])
        );
        assign state[lane]=dut.state;
        assign quotient[lane]=dut.quotient;
        assign remainder[lane]=dut.remainder;
    end
    // Matching encodings in the pinned scalar source.
    localparam logic [4:0] DIV_STEP = 5'd2, DIV_FINISH = 5'd17;

    task automatic load_table(input string filename, input bit kind);
        int fd, words, row_index;
        logic [31:0] value;
        fd=$fopen(filename,"r");
        if(!fd) $fatal(1,"Cannot open table %s",filename);
        words=kind ? 256 : 257;
        table_kind=kind;
        for (row_index=0; row_index<words; row_index++) begin
            if($fscanf(fd,"%h",value)!=1) $fatal(1,"Missing table word %0d",row_index);
            table_index=9'(row_index);table_value=value;table_valid=1;
            #1;
            if(table_ready!=2'b11) $fatal(1,"Table word refused");
            @(negedge clk);
        end
        table_valid=0;
        $fclose(fd);
    endtask

    task automatic check_case(input int row, input logic signed [63:0] expected_result,
                              input logic signed [7:0] expected_exp, input bit expected_error,
                              input logic [63:0] expected_q, expected_r, input int delta);
        int steps[2], valid_cycle[2], raw_seen[2];
        bit checking_division;
        if (cmd_ready!=2'b11 || result_valid!=0) $fatal(1,"Scalar not ready at row %0d",row);
        checking_division=op==3'd1 && !expected_error;
        steps='{default:0};
        raw_seen='{default:0};
        valid_cycle='{default:-1};
        cmd_valid=1;
        @(negedge clk);cmd_valid=0;
        for(int cycle=0; cycle<=400; cycle++) begin
            for(int lane=0; lane<2; lane++) begin
                if(checking_division && state[lane]==DIV_STEP) steps[lane]++;
                if(checking_division && state[lane]==DIV_FINISH) begin
                    raw_seen[lane]++;
                    if(quotient[lane]!==expected_q || remainder[lane]!=={1'b0,expected_r})
                        $fatal(1,"Incorrect q/r row=%0d arm=%0d",row,lane);
                end
                if(result_valid[lane]) begin
                    if(valid_cycle[lane]<0) valid_cycle[lane]=cycle;
                    if(result[lane]!==expected_result || result_exponent[lane]!==expected_exp ||
                       error[lane]!==expected_error || cmd_ready[lane])
                        $fatal(1,"Bad output row=%0d arm=%0d op=%0d a=%h b=%h got=%h want=%h",
                               row,lane,op,a,b,result[lane],expected_result);
                end else if(valid_cycle[lane]>=0) $fatal(1,"Lost held result");
            end
            if(result_valid==2'b11 && cycle>=valid_cycle[0]+3 && cycle>=valid_cycle[1]+3) break;
            @(negedge clk);
        end
        if(result_valid!=2'b11 || valid_cycle[0]-valid_cycle[1]!=delta)
            $fatal(1,"Latency row=%0d control=%0d candidate=%0d delta=%0d",
                   row,valid_cycle[0],valid_cycle[1],delta);
        if(checking_division &&
           (steps[0]!=32 || steps[1]!=32-delta || raw_seen[0]!=1 || raw_seen[1]!=1))
            $fatal(1,"Quotient state schedule row=%0d",row);
        result_ready=1;
        @(negedge clk);result_ready=0;
        if(cmd_ready!=2'b11 || result_valid!=0) $fatal(1,"Result was not consumed");
    endtask

    initial begin
        string folder;
        int fd,count,delta;
        logic signed [63:0] expected_result;
        logic signed [7:0] expected_exp;
        logic [63:0] expected_q, expected_r;
        bit expected_error;
        if(!$value$plusargs("FIXTURES=%s",folder) || !$value$plusargs("ROWS=%d",count))
            $fatal(1,"Missing scalar fixtures");
        @(negedge clk);reset=0;
        load_table({folder,"/exp.hex"},0);
        load_table({folder,"/rsqrt.hex"},1);
        #1;
        fd=$fopen({folder,"/scalar.hex"},"r");
        if(!fd) $fatal(1,"Cannot open scalar fixtures");
        for(int row=0; row<count; row++) begin
            if($fscanf(fd,"%h %h %h %h %h %h %h %h %h %d",
                       op,a,b,shift,expected_result,expected_exp,expected_error,expected_q,expected_r,delta)!=10)
                $fatal(1,"Fixture row %0d missing or malformed",row);
            check_case(row,expected_result,expected_exp,expected_error,expected_q,expected_r,delta);
        end
        $fclose(fd);
        // Cancel an operation after short and long variants both enter their recurrence.
        op=1; a=64'sd32768; b=64'sd3; shift=0; cmd_valid=1;
        @(negedge clk);cmd_valid=0;
        repeat(3) @(negedge clk);
        if(state[0]!=DIV_STEP || state[1]!=DIV_STEP) $fatal(1,"Reset probe missed active division");
        reset=1;
        @(negedge clk);reset=0;
        #1;
        if(cmd_ready!=2'b11 || result_valid!=0 || error!=0) $fatal(1,"Reset left a stale result");
        @(negedge clk);
        check_case(count,64'sd10923,8'sd0,0,64'd10922,64'd2,24);
        $display("PASS scalar: %0d valid, invalid, boundary and other-operation fixtures; held results and reset",count);
        $finish;
    end
endmodule
