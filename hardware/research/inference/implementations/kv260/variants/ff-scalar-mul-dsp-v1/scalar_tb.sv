`timescale 1ns/1ps
module partial_multiply_scalar_tb;
    logic clk=0, reset=1, cmd_valid=0, result_ready=0, table_valid=0, table_kind=0;
    logic [1:0] cmd_ready, result_valid, table_ready, error;
    logic [2:0] op;
    logic signed [63:0] a,b,result[2];
    logic signed [7:0] shift, result_exponent[2];
    logic [8:0] table_index;
    logic [31:0] table_value;
    logic [4:0] state[2];
    logic [127:0] raw_control, raw_candidate;
    logic raw_control_valid, raw_candidate_valid;
    // Encodings are pinned by the generated source manifest.
    localparam logic [4:0] MUL_STEP=5'd3, MUL_ROWS=5'd18, MUL_FINISH=5'd21;

    always #5 clk = ~clk;
    fixed_scalar_mul_control control (
        .clk,.reset,.cmd_valid,.cmd_ready(cmd_ready[0]),.cmd_op(op),.cmd_a(a),.cmd_b(b),
        .cmd_shift(shift),.table_valid,.table_ready(table_ready[0]),
        .table_kind,.table_index,.table_value,.result_valid(result_valid[0]),.result_ready,
        .result(result[0]),.result_exponent(result_exponent[0]),.error(error[0])
    );
    fixed_scalar_ff_exp candidate (
        .clk,.reset,.cmd_valid,.cmd_ready(cmd_ready[1]),.cmd_op(op),.cmd_a(a),.cmd_b(b),
        .cmd_shift(shift),.table_valid,.table_ready(table_ready[1]),
        .table_kind,.table_index,.table_value,.result_valid(result_valid[1]),.result_ready,
        .result(result[1]),.result_exponent(result_exponent[1]),.error(error[1])
    );
    assign state[0]=control.state;
    assign state[1]=candidate.state;
    assign raw_control=control.next_product;
    assign raw_control_valid=state[0]==MUL_STEP && control.remaining==7'd1;
    assign raw_candidate=candidate.product_sum;
    assign raw_candidate_valid=state[1]==MUL_FINISH;

    task automatic load_table(input string filename, input bit kind);
        int fd, words;
        logic [31:0] value;
        fd=$fopen(filename,"r");
        if(fd==0) $fatal(1,"Cannot open table %s",filename);
        words=kind ? 256 : 257;
        table_kind=kind;
        for(int row=0; row<words; row++) begin
            if($fscanf(fd,"%h",value)!=1) $fatal(1,"Missing table word %0d",row);
            table_index=9'(row);table_value=value;table_valid=1;
            #1;
            if(table_ready!=2'b11) $fatal(1,"Valid table word refused");
            @(negedge clk);
        end
        table_valid=0;
        $fclose(fd);
        #1;
    endtask

    task automatic check_case(input int row, input logic signed [63:0] expected_result,
                              input logic signed [7:0] expected_exp, input bit expected_error,
                              input logic [127:0] expected_raw, input int expected_products);
        int valid_cycle[2], work_cycles[2], products[2];
        logic [127:0] control_products[6], candidate_products[6];
        if(cmd_ready!=2'b11 || result_valid!=0) $fatal(1,"Scalar not ready at row %0d",row);
        work_cycles='{default:0};
        products='{default:0};
        valid_cycle='{default:-1};
        cmd_valid=1;
        @(negedge clk);cmd_valid=0;
        for(int cycle=0; cycle<=400; cycle++) begin
            if(state[0]==MUL_STEP) work_cycles[0]++;
            if(state[1]==MUL_STEP || (state[1]>=MUL_ROWS && state[1]<=MUL_FINISH)) work_cycles[1]++;
            if(raw_control_valid) begin
                if(products[0]>=6) $fatal(1,"Too many control products");
                control_products[products[0]]=raw_control;
                products[0]++;
            end
            if(raw_candidate_valid) begin
                if(products[1]>=6) $fatal(1,"Too many candidate products");
                candidate_products[products[1]]=raw_candidate;
                products[1]++;
            end
            for(int lane=0; lane<2; lane++) begin
                if(cmd_ready[lane]) $fatal(1,"Busy or stalled scalar accepted another command");
                if(result_valid[lane]) begin
                    if(valid_cycle[lane]<0) valid_cycle[lane]=cycle;
                    if(result[lane]!==expected_result || result_exponent[lane]!==expected_exp ||
                       error[lane]!==expected_error)
                        $fatal(1,"Bad response row=%0d arm=%0d op=%0d a=%h b=%h got=%h want=%h",
                               row,lane,op,a,b,result[lane],expected_result);
                end else if(valid_cycle[lane]>=0) $fatal(1,"Lost held result");
            end
            if(result_valid==2'b11 && cycle>=valid_cycle[0]+3 && cycle>=valid_cycle[1]+3) break;
            @(negedge clk);
        end
        if(result_valid!=2'b11 || products[0]!=products[1] ||
           (expected_products>=0 && products[0]!=expected_products))
            $fatal(1,"Product or response count differs at row %0d",row);
        for(int index=0; index<products[0]; index++)
            if(control_products[index]!==candidate_products[index])
                $fatal(1,"Internal 128-bit scalar product differs at row %0d product %0d",row,index);
        if(op==3'd2 && (products[0]!=1 || candidate_products[0]!==expected_raw))
            $fatal(1,"Raw 128-bit product differs from oracle at row %0d",row);
        if(valid_cycle[0]-valid_cycle[1]!=11*products[0] ||
           work_cycles[0]!=16*products[0] || work_cycles[1]!=5*products[0])
            $fatal(1,"Latency row=%0d products=%0d control=%0d candidate=%0d",
                   row,products[0],valid_cycle[0],valid_cycle[1]);
        result_ready=1;
        @(negedge clk);result_ready=0;
        if(cmd_ready!=2'b11 || result_valid!=0) $fatal(1,"Result was not consumed");
    endtask

    initial begin
        string folder;
        int fd,count,products;
        logic signed [63:0] expected_result;
        logic signed [7:0] expected_exp;
        logic [127:0] expected_raw;
        bit expected_error;
        if(!$value$plusargs("FIXTURES=%s",folder) || !$value$plusargs("ROWS=%d",count))
            $fatal(1,"Missing scalar fixtures");
        @(negedge clk);reset=0;
        #1;
        // An unloaded EXP should reject as before without using the multiplier.
        op=3; a=0; b=0; shift=0; check_case(-1,0,0,1,0,0);
        load_table({folder,"/exp.hex"},0);
        load_table({folder,"/rsqrt.hex"},1);
        fd=$fopen({folder,"/scalar.hex"},"r");
        if(fd==0) $fatal(1,"Cannot open scalar fixtures");
        for(int row=0; row<count; row++) begin
            if($fscanf(fd,"%h %h %h %h %h %h %h %h %d",
                       op,a,b,shift,expected_result,expected_exp,expected_error,expected_raw,products)!=9)
                $fatal(1,"Fixture row %0d missing or malformed",row);
            check_case(row,expected_result,expected_exp,expected_error,expected_raw,products);
        end
        $fclose(fd);
        for(int stage=0; stage<5; stage++) begin
            op=2; a=-64'sd607418155393411205; b=64'sd957162937462038433; shift=0; cmd_valid=1;
            @(negedge clk);cmd_valid=0;
            repeat(stage) @(negedge clk);
            if(state[0]!=MUL_STEP || state[1]!=(stage==0 ? MUL_STEP : 5'(int'(MUL_ROWS)+stage-1)))
                $fatal(1,"Reset missed multiplier stage %0d",stage);
            reset=1;
            @(negedge clk);reset=0;
            #1;
            if(cmd_ready!=2'b11 || result_valid!=0 || error!=0) $fatal(1,"Reset left a stale result");
            op=2; a=-64'sd65537; b=64'sd65537;
            check_case(count+stage,-64'sd4295098369,0,0,128'd4295098369,1);
        end
        $display("PASS scalar: %0d oracle rows, held responses, exact raw products, five state resets",count);
        $finish;
    end
endmodule
